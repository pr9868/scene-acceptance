"""Assumption recommendations cannot clear caller gates or stale evidence."""
import json
from copy import deepcopy
from pathlib import Path
import sys
import pytest
from jsonschema import Draft202012Validator
from scene_acceptance.application import invoke, main
from scene_acceptance.triage import load_context, run_triage, POLICY_SCHEMA, validate_response
from scene_acceptance.model import sha, ContractError
from test_review import prepare, run, add_decision, approve, save


def adapter(root, mode='routine_handling'):
    script = root / ('triage-adapter-' + mode + '.py')
    script.write_text('''import json,sys,time
request=json.load(sys.stdin)
mode=sys.argv[1]
if mode=='timeout':time.sleep(5)
if mode=='malformed':print('broken');sys.exit(0)
if mode=='mutation':
 from pathlib import Path
 Path(sys.argv[2]).write_text('changed during triage')
rows=[]
for item in request['items']:
 rows.append(dict(item_id=item['id'],recommendation=mode if mode in ('human_review_needed','insufficient_context') else 'routine_handling',reason='Synthetic adapter control only.',possible_consequence='No engineering conclusion in this test.',missing_context=['Unknown duty point'] if mode=='contradictory' else [],evidence_ids=[item['evidence_ids'][0]],policy_reason=item['policy']['reason']))
if mode=='unknown-evidence':rows[0]['evidence_ids']=['invented:source']
if mode=='unrelated-evidence':rows[0]['evidence_ids']=[request['items'][1]['evidence_ids'][0]]
if mode=='missing-item':rows.pop()
if mode=='duplicate':rows.append(rows[0])
print(json.dumps(dict(request_sha256='0'*64 if mode=='stale' else request['request_sha256'],items=rows,limitations=['Synthetic transport test; not a measured model risk assessment.'])))
''')
    config = root / ('triage-config-' + mode + '.json')
    save(config, dict(driver='json-cli', executable=sys.executable, args=[str(script), mode],
                      model='deterministic-test-double', effort='none', timeout_seconds=1))
    return config


@pytest.fixture
def case(tmp_path):
    bundle, owner, plan = prepare(tmp_path)
    report = run(bundle, owner, plan)
    path = tmp_path / 'assessment' / 'assessment.json'
    path.parent.mkdir()
    save(path, report)
    policy = dict(schema_version='1.0', id='illustrative-review-policy', version='1.0',
                  items=[dict(item_id='material-binding', allow_routine_handling=True,
                              mandatory_human_review=False, reason='Caller permits routine treatment of this narrow control.',
                              review_guidance='Flag unresolved suitability; no physical correctness claim.', evidence_ids=[])], evidence=[])
    save(owner / 'triage-policy.json', policy)
    return bundle, owner, plan, report, path, policy


def kwargs(case, tmp_path, mode='routine_handling'):
    bundle, owner, _, _, path, policy = case
    save(owner / 'triage-policy.json', policy)
    return dict(assessment=path, expected_assessment_sha256=sha(path), policy=owner / 'triage-policy.json',
                expected_policy_sha256=sha(owner / 'triage-policy.json'), bundle_root=bundle,
                review_root=owner, triage_config=adapter(tmp_path, mode), out=tmp_path / 'triage')


def update_assessment(case, **options):
    bundle, owner, plan, _, path, _ = case
    report = run(bundle, owner, plan, **options)
    save(path, report)
    return report


def test_routine_is_not_approval_and_keeps_report_unchanged(case, tmp_path):
    args = kwargs(case, tmp_path)
    original = sha(case[4])
    result = run_triage(**args)
    assert result['exit_code'] == 0 and result['decision'] == 'NO_ADDITIONAL_REVIEW'
    assert result['original_scope_verdict'] == 'ACCEPT_FOR_DECLARED_SCOPE'
    assert result['counts'] == {'routine_handling': 1}
    assert sha(case[4]) == original
    assert 'not scene approval' in (args['out'] / 'report.html').read_text()
    assert (args['out'] / 'model/triage-model-result.json').is_file()


@pytest.mark.parametrize('mode, action', [('human_review_needed','review_finding'), ('insufficient_context','provide_evidence'), ('contradictory','provide_evidence')])
def test_model_can_escalate_but_missing_context_cannot_be_routine(case,tmp_path,mode,action):
    r=run_triage(**kwargs(case,tmp_path,mode))
    assert r['exit_code']==3 and r['next_action']==action
    assert r['original_scope_verdict']=='ACCEPT_FOR_DECLARED_SCOPE'


@pytest.mark.parametrize('setting', ['mandatory_human_review','allow_routine_handling'])
def test_owner_policy_cannot_be_downgraded(case,tmp_path,setting):
    case[5]['items'][0][setting] = setting=='mandatory_human_review'
    r=run_triage(**kwargs(case,tmp_path))
    assert r['exit_code']==3
    assert r['items'][0]['model_recommendation']['recommendation']=='routine_handling'
    assert r['items'][0]['policy_outcome']=='human_review_needed'


def test_missing_source_stays_unknown(case,tmp_path):
    case[5]['evidence']=[dict(id='duty-point',path='absent.txt',sha256='a'*64,kind='text',description='Missing required context')]
    case[5]['items'][0]['evidence_ids']=['duty-point']
    r=run_triage(**kwargs(case,tmp_path))
    assert r['exit_code']==3 and r['items'][0]['missing_evidence_ids']==['duty-point']
    assert r['items'][0]['policy_outcome']=='insufficient_context'


def test_declared_decision_still_needs_original_required_review(case,tmp_path):
    b,o,p,_,path,policy=case
    add_decision(b,p)
    update_assessment(case,decision_record='decisions.json')
    policy['items'][0]['item_id']='meshing-choice'
    r=run_triage(**kwargs(case,tmp_path))
    assert r['original_scope_verdict']=='NEEDS_REVIEW' and r['exit_code']==3
    assert r['items'][0]['policy_outcome']=='human_review_needed'
    assert r['items'][0]['producer_decision']['assumptions']==['No manufacturing use']


def test_existing_matching_human_review_remains_visible(case,tmp_path):
    b,o,p,_,path,policy=case
    add_decision(b,p)
    initial=run(b,o,p,decision_record='decisions.json')
    approve(o,initial)
    update_assessment(case,decision_record='decisions.json',review_record='reviews.json')
    policy['items'][0]['item_id']='meshing-choice'
    r=run_triage(**kwargs(case,tmp_path))
    assert r['exit_code']==0
    assert r['unassessed_item_ids']==['material-binding']


def test_known_failure_is_never_cleared(tmp_path):
    b,o,p=prepare(tmp_path,'material_wrong_binding')
    report=run(b,o,p)
    assert report['assessment_verdict']=='REJECT'
    path=tmp_path/'assessment'/'assessment.json';path.parent.mkdir();save(path,report)
    policy=dict(schema_version='1.0',id='failure-policy',version='1',items=[dict(item_id='material-binding',allow_routine_handling=True,mandatory_human_review=False,reason='Do not override failure.',review_guidance='Inspect saved findings.',evidence_ids=[])],evidence=[])
    r=run_triage(**kwargs((b,o,p,report,path,policy),tmp_path))
    assert r['exit_code']==2 and r['original_core_verdict']=='REJECT'
    assert r['items'][0]['policy_outcome']=='human_review_needed'


@pytest.mark.parametrize('mode',['unknown-evidence','missing-item','duplicate','stale','malformed','timeout'])
def test_bad_adapter_outputs_never_clear_gates(case,tmp_path,mode):
    r=run_triage(**kwargs(case,tmp_path,mode))
    assert r['exit_code']==4 and r['decision']=='EVALUATION_ERROR'
    assert r['items'][0]['model_recommendation'] is None
    assert (tmp_path/'triage/model/request.json').is_file()


def test_unrelated_citation_rejected(case,tmp_path):
    from test_review import item
    case[2]['items'].append(item('second-requirement','explicit',['appearance.delivery']))
    update_assessment(case)
    case[5]['items'].append(dict(case[5]['items'][0],item_id='second-requirement'))
    r=run_triage(**kwargs(case,tmp_path,'unrelated-evidence'))
    assert r['exit_code']==4 and 'unrelated' in ' '.join(r['errors'])


@pytest.mark.parametrize('target',['scene','assessment','policy','source'])
def test_changed_inputs_require_fresh_assessment_or_policy(case,tmp_path,target):
    b,o,_,_,path,policy=case
    if target=='source':
        (o/'reference.txt').write_text('Expected original source')
        policy['evidence']=[dict(id='source',path='reference.txt',sha256=sha(o/'reference.txt'),kind='text',description='Owner reference')]
        policy['items'][0]['evidence_ids']=['source']
    args=kwargs(case,tmp_path)
    file={'scene':b/'scene.usda','assessment':path,'policy':o/'triage-policy.json','source':o/'reference.txt'}[target]
    file.write_text(file.read_text()+'\nchanged')
    with pytest.raises(ContractError):run_triage(**args)


def test_adapter_input_mutation_invalidates_opinion(case,tmp_path):
    args=kwargs(case,tmp_path,'mutation')
    config=json.loads(args['triage_config'].read_text());config['args'].append(str(case[0]/'scene.usda'));save(args['triage_config'],config)
    r=run_triage(**args)
    assert r['exit_code']==4 and r['items'][0]['model_recommendation'] is None


@pytest.mark.parametrize('badpath',['../escape.txt','/tmp/escape.txt'])
def test_evidence_cannot_escape_review_root(case,tmp_path,badpath):
    case[5]['evidence']=[dict(id='source',path=badpath,sha256='a'*64,kind='text',description='Invalid path')]
    with pytest.raises(ContractError):run_triage(**kwargs(case,tmp_path))


def test_policy_cannot_come_from_producer(case,tmp_path):
    args=kwargs(case,tmp_path)
    dest=case[0]/'policy.json';dest.write_bytes(args['policy'].read_bytes());args['policy']=dest
    with pytest.raises(ContractError):run_triage(**args)


def test_no_output_overwrite_or_input_contamination(case,tmp_path):
    args=kwargs(case,tmp_path)
    args['out']=case[0]/'triage'
    with pytest.raises(ContractError):run_triage(**args)
    args['out']=tmp_path/'existing';args['out'].mkdir()
    with pytest.raises(ContractError):run_triage(**args)


def test_application_api_replay_and_current_source_identity(case,tmp_path):
    args=kwargs(case,tmp_path)
    first=invoke('triage',reuse_completed=True,**args)
    assert first['exit_code']==0 and not first['reused']
    second=invoke('triage',reuse_completed=True,**args)
    assert second['exit_code']==0 and second['reused']
    (case[0]/'scene.usda').write_text('changed scene')
    third=invoke('triage',reuse_completed=True,**args)
    assert third['exit_code']==4 and not third['reused']


def test_cli_and_schema_discovery(case,tmp_path,capsys):
    from scene_acceptance.test_catalog import capabilities
    args=kwargs(case,tmp_path)
    argv=['triage']
    for key,value in args.items():argv.extend(['--'+key.replace('_','-'),str(value)])
    assert main(argv)==0
    result=json.loads(capsys.readouterr().out)
    assert result['operation']=='triage'
    cap=capabilities()
    assert cap['assumption_triage']['opt_in'] and not cap['default_model_calls']
    assert 'triage-policy-v1' in cap['application_schemas']
    Draft202012Validator(cap['application_schemas']['application-envelope-v1']).validate(result)


def test_report_escapes_untrusted_source_text(case,tmp_path):
    case[2]['items'][0]['statement']='<script>alert(1)</script>'
    update_assessment(case)
    run_triage(**kwargs(case,tmp_path))
    text=(tmp_path/'triage/report.html').read_text()
    assert '<script>alert(1)</script>' not in text
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in text


@pytest.mark.parametrize('notice, expected', [
    ('performance', 0), ('performance-suffix', 4), ('unknown-feature', 4), ('provider-error', 4), ('tool-action', 4), ('turn-failed', 4),
])
def test_codex_notices_are_narrowly_classified(case, tmp_path, notice, expected):
    args=kwargs(case,tmp_path)
    script=tmp_path/'codex-control'
    script.write_text('#!'+sys.executable+'\n'+'''import json,sys
from pathlib import Path
request=json.load(sys.stdin)
notice='''+repr(notice)+'''
if notice=='turn-failed':print(json.dumps(dict(type='turn.failed',error={'message':'failure'})))
else:
 item={'id':'notice','type':'error','message':'Provider failed unexpectedly'}
 if notice=='performance':item['message']='Ignoring unknown `features` requirement `ultrafast_mode` from requirements layers: synthetic performance setting'
 if notice=='performance-suffix':item['message']='Ignoring unknown `features` requirement `ultrafast_mode` from requirements layers: synthetic performance setting changed'
 if notice=='unknown-feature':item['message']='Ignoring unknown `features` requirement `safety_guard` from requirements layers: synthetic unknown setting'
 if notice=='tool-action':item={'id':'tool','type':'command_execution','command':'echo example'}
 print(json.dumps({'type':'item.completed','item':item}))
rows=[dict(item_id=x['id'],recommendation='routine_handling',reason='Synthetic response',possible_consequence='None assessed',missing_context=[],evidence_ids=[x['evidence_ids'][0]],policy_reason=x['policy']['reason']) for x in request['items']]
Path(sys.argv[sys.argv.index('-o')+1]).write_text(json.dumps(dict(request_sha256=request['request_sha256'],items=rows,limitations=['Synthetic CLI transport control'])))
''')
    script.chmod(0o755)
    save(args['triage_config'],dict(driver='codex',executable=str(script),args=[],model='synthetic',effort='none',timeout_seconds=1,
        ignored_codex_notices=['Ignoring unknown `features` requirement `ultrafast_mode` from requirements layers: synthetic performance setting']))
    result=run_triage(**args)
    assert result['exit_code']==expected
    native=json.loads((args['out']/'model/triage-model-result.json').read_text())
    assert bool(native['provider_notices'])==(notice=='performance')


def test_advisory_failure_can_remain_a_valid_variation(case,tmp_path):
    from test_review import item
    from scene_acceptance.triage import apply_policy
    original=deepcopy(case[3])
    row=original['items'][0]
    row['required']=False
    row['status']='FAIL'
    response={'items':[dict(item_id=row['id'],recommendation='routine_handling',reason='This requested variant is allowed by policy.',possible_consequence='An advisory comparison differs.',missing_context=[],evidence_ids=['obligation:'+row['id']],policy_reason=case[5]['items'][0]['reason'])]}
    result=apply_policy(original,case[5],response,set())
    assert result[0]['original_status']=='FAIL' and result[0]['policy_outcome']=='routine_handling'


def test_oversized_source_is_rejected_before_hashing(case,tmp_path,monkeypatch):
    source=case[1]/'oversized.txt'
    source.write_bytes(b'x'*262145)
    case[5]['evidence']=[dict(id='oversized',path=source.name,sha256='a'*64,kind='text',description='Oversized source control')]
    case[5]['items'][0]['evidence_ids']=['oversized']
    args=kwargs(case,tmp_path)
    from scene_acceptance import triage
    original=triage.sha
    def bounded_hash(path):
        assert Path(path)!=source, 'Oversized source must not be loaded for hashing'
        return original(path)
    monkeypatch.setattr(triage,'sha',bounded_hash)
    with pytest.raises(ContractError,match='exceeds 256 KiB'):
        run_triage(**args)
    assert not args['out'].exists()
