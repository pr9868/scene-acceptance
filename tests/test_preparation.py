"""Preparation/receipt controls. Synthetic adapters and images do not test model quality."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest
from PIL import Image
from scene_acceptance.model import ContractError, sha
from scene_acceptance.preparation import prepare_scene, load_preparation, validate_interpretation
from scene_acceptance.prepared_run import evaluate_prepared
from scene_acceptance.review_context import GENERAL_RUBRIC, save
from scene_acceptance.skill_package import export_skills, NAMES
from test_briefs import prepare
from test_evaluation_modes import config as judge_config


@pytest.fixture
def bundle(tmp_path):
    return prepare.prepare(tmp_path/'fixtures')/'panel'


def setup(tmp_path,bundle,behavior='normal'):
    text='At time code 0, the panel must be 0.30 by 0.16 by 0 metres with 0.001 metre tolerance. The label must be legible.'
    (bundle/'raw.txt').write_text(text)
    save(bundle/'raw.json',dict(schema_version='1.0',id='sample',title='Synthetic raw brief',intended_use='Illustration',
        provenance='Software test, not real model output',files=[dict(path='raw.txt',role='text',caption='Explicit test brief')]))
    adapter=tmp_path/'interpreter.py'
    adapter.write_text('''import json,sys
r=json.load(sys.stdin)
s=r['sources'][0]
b=sys.argv[1]
checks=[dict(id='spec.panel',type_id='brief.measurements.bounds',parameters_json=json.dumps(dict(path='/World/Panel',time_code=0,size_m=[.30,.16,0],tolerance_m=.001)))]
cap=dict(id='label-view',purpose='Inspect label',targets=['/World/Panel'],times_seconds=[0],camera_guidance='Front close-up',view_role='front',sharing_group=None,camera_id=None,projection=None,capabilities=['geometry','surface_materials'],min_width=64,min_height=64,limitations=['Visible face only'])
items=[dict(id='size',statement='Panel size',source_ids=[s['id']],quotes=[dict(source_id=s['id'],quote=s['text'])],route='script',reason='Explicit dimensions and tolerance',area='geometry',checks=checks,visual=None),
 dict(id='label',statement='Legible label',source_ids=[s['id']],quotes=[dict(source_id=s['id'],quote='The label must be legible.')],route='visual',reason='Appearance needs rendered evidence',area='textures',checks=[],visual=dict(statement='Is the visible label legible?',evidence_kind='textured_view',captures=[cap]))]
if b=='unknown-check':checks[0]['type_id']='arbitrary.execute'
if b=='bad-parameter':checks[0]['parameters_json']='{"command":"echo injected"}'
if b=='bad-quote':items[0]['quotes'][0]['quote']='Invented source claim'
if b=='missing-quote':items[0]['quotes']=[]
if b=='bad-source':items[0]['source_ids']=['invented']
if b=='bad-path':cap['targets']=['/DoesNotExist']
if b=='bad-time':cap['times_seconds']=[99999]
if b=='missing-check':items[0]['checks']=[]
if b=='duplicate':items.append(items[0])
if b=='no-fidelity':cap['capabilities']=['geometry']
if b=='unresolved':
 items[0].update(route='unresolved',checks=[],reason='Conflicting targets need clarification')
if b=='unsupported':
 items[0].update(route='unsupported',checks=[],reason='No supported validator for intended use')
print(json.dumps(dict(request_sha256='0'*64 if b=='stale' else r['request_sha256'],requirements=items,limitations=['Deterministic adapter; not an actual model review.'])))
''')
    cp=tmp_path/'interpreter-config.json'
    save(cp,dict(driver='json-cli',executable=sys.executable,args=[str(adapter),behavior],model='test-double',effort='none',timeout_seconds=3))
    rubric=deepcopy(GENERAL_RUBRIC);rubric['criteria']=[];rp=tmp_path/'rubric.json';save(rp,rubric)
    caps=tmp_path/'caps.json';save(caps,dict(schema_version='1.0',capabilities=['geometry','surface_materials'],max_images=12,max_width=1024,max_height=768,limitations=['Test fixture only']))
    return dict(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'prepared',raw_brief='raw.json',interpreter_config=cp,capture_capabilities=caps,rubric=rp)


def evidence(tmp_path,plan,*,fault=None):
    folder=tmp_path/'captures';folder.mkdir()
    im=folder/'view.png';Image.new('RGB',(64,64),'white').save(im)
    view=dict(id='front',path='view.png',sha256=sha(im),view_roles=['front'],camera_id='front',camera='Front close-up',projection='orthographic',time_seconds=0,
              method='Synthetic image transport fixture, not a render',producer='pytest',capabilities=['geometry','surface_materials'],limitations=['No actual visual evidence'],covered_prims=['/World/Panel'])
    receipt=dict(schema_version='1.0',plan_sha256=plan['plan_sha256'],scene_sha256=plan['scene_sha256'],requests=[dict(request_id='label-view',status='supplied',view_ids=['front'],reason='Software-control image')])
    if fault=='target':view['covered_prims']=[]
    if fault=='fidelity':view['capabilities']=['geometry']
    if fault=='resolution':Image.new('RGB',(16,16),'white').save(im);view['sha256']=sha(im)
    if fault=='plan':receipt['plan_sha256']='0'*64
    if fault=='unknown-id':receipt['requests'][0]['view_ids']=['missing']
    if fault=='duplicate':receipt['requests']*=2
    if fault=='missing':receipt['requests']=[]
    vp=folder/'views.json';save(vp,dict(schema_version='1.0',scene_sha256=plan['scene_sha256'],up_axis='Z',meters_per_unit=1,views=[view]))
    rp=folder/'receipt.json';save(rp,receipt)
    return dict(views=vp,receipt=rp)


def test_no_brief_preparation_and_check_run_never_calls_model(bundle,tmp_path,monkeypatch):
    monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**kw:pytest.fail('Unexpected model call'))
    p=prepare_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'prepared')
    assert p['brief'] is None and p['mapping_review']=='not_applicable'
    assert load_preparation(tmp_path/'prepared',p['plan_sha256'])[1]==p
    r=evaluate_prepared(preparation=tmp_path/'prepared',out=tmp_path/'run')
    assert r['exit_code']==0 and r['script_verdict']=='ACCEPT_FOR_USE'


def test_raw_interpreter_to_script_and_separate_judge(bundle,tmp_path):
    kwargs=setup(tmp_path,bundle);before={str(p):sha(p) for p in bundle.rglob('*') if p.is_file()}
    p=prepare_scene(**kwargs);ev=evidence(tmp_path,p)
    r=evaluate_prepared(preparation=kwargs['out'],out=tmp_path/'run',expected_plan_sha256=p['plan_sha256'],mode='both',judge_config=judge_config(tmp_path),**ev)
    assert r['exit_code']==2 and r['script_verdict']=='REJECT' # authored panel is .24m, requirement is .30m
    assert r['capture_counts']=={'supplied':1} and r['judge_counts']=={'consistent':1}
    request=json.loads((tmp_path/'run/evaluation/judge/request.json').read_text())
    assert [x['id'] for x in request['requirements']]==['brief.label'] # script-only size is not visually guessed
    assert request['script_verdict'] is None
    assert p['mapping_review']=='pending'
    assert {str(p):sha(p) for p in bundle.rglob('*') if p.is_file()}==before
    for name,h in json.loads((tmp_path/'run/manifest.json').read_text())['files'].items():assert sha(tmp_path/'run'/name)==h


@pytest.mark.parametrize('fault',['target','fidelity','resolution','missing'])
def test_insufficient_capture_demotes_even_positive_model_opinion(bundle,tmp_path,fault):
    kw=setup(tmp_path,bundle);p=prepare_scene(**kw);ev=evidence(tmp_path,p,fault=fault)
    r=evaluate_prepared(preparation=kw['out'],out=tmp_path/'run',mode='judge',judge_config=judge_config(tmp_path,'unsupported'),**ev)
    assert r['capture_counts']=={'missing':1} and r['judge_counts']=={'unknown':1} and r['exit_code']==3


def test_no_views_stays_unknown_and_check_only_still_rejects(bundle,tmp_path):
    kw=setup(tmp_path,bundle);prepare_scene(**kw)
    r=evaluate_prepared(preparation=kw['out'],out=tmp_path/'judge',mode='judge',judge_config=judge_config(tmp_path,'unsupported'))
    assert r['judge_counts']=={'unknown':1} and r['capture_counts']=={'missing':1}
    r=evaluate_prepared(preparation=kw['out'],out=tmp_path/'checks')
    assert r['exit_code']==2


@pytest.mark.parametrize('fault',['plan','unknown-id','duplicate'])
def test_invalid_receipt_rejected_before_judge(bundle,tmp_path,monkeypatch,fault):
    kw=setup(tmp_path,bundle);p=prepare_scene(**kw);ev=evidence(tmp_path,p,fault=fault)
    monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**kw:pytest.fail('Bad receipt reached model'))
    r=evaluate_prepared(preparation=kw['out'],out=tmp_path/'run',mode='both',judge_config=judge_config(tmp_path),**ev)
    assert r['exit_code']==4 and r['script_verdict']=='REJECT' and r['execution_status']=='partial'


@pytest.mark.parametrize('behavior',['unknown-check','bad-parameter','bad-quote','missing-quote','bad-source','bad-path','bad-time','missing-check','duplicate','no-fidelity','stale'])
def test_bad_interpretation_never_becomes_executable_plan(bundle,tmp_path,behavior):
    kw=setup(tmp_path,bundle,behavior)
    with pytest.raises(ContractError):prepare_scene(**kw)
    assert not (kw['out']/'plan.json').exists()
    assert json.loads((kw['out']/'interpreter/interpreter-result.json').read_text())['status']=='ERROR'


@pytest.mark.parametrize('route',['unresolved','unsupported'])
def test_unmapped_obligations_remain_visible(bundle,tmp_path,route):
    kw=setup(tmp_path,bundle,route);p=prepare_scene(**kw)
    r=evaluate_prepared(preparation=kw['out'],out=tmp_path/'run')
    assert p['routes'][route]==1 and r['exit_code']==3 and r['scope_verdict']=='NEEDS_REVIEW'


@pytest.mark.parametrize('fault',['brief','capture','scene','plan','hash'])
def test_plan_or_source_tamper_rejected(bundle,tmp_path,fault):
    kw=setup(tmp_path,bundle);p=prepare_scene(**kw)
    files={'brief':kw['out']/p['bundle']/p['brief'],'capture':kw['out']/'capture-plan.json',
           'scene':kw['out']/p['bundle']/p['candidate'],'plan':kw['out']/'plan.json'}
    if fault!='hash':files[fault].write_text(files[fault].read_text()+' ')
    # Plan digest is canonical JSON; formatting alone intentionally keeps its content identity.
    if fault=='plan':
        d=json.loads(files[fault].read_text());d['candidate']='missing.usda';save(files[fault],d)
    with pytest.raises(ContractError):load_preparation(kw['out'],'0'*64 if fault=='hash' else p['plan_sha256'])


def test_custom_rubric_and_capture_overrides_are_frozen(bundle,tmp_path):
    rubric=deepcopy(GENERAL_RUBRIC);rubric['criteria']=rubric['criteria'][:1]
    rp=tmp_path/'rubric.json';save(rp,rubric)
    first=prepare_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'first',rubric=rp)
    c=json.loads((tmp_path/'first/capture-plan.json').read_text())['requests'][0]
    for k in ('requirement_ids','evidence_kind','feasibility_gaps'):c.pop(k)
    c.update(targets=['/World/Panel'],min_width=1920,camera_guidance='Front label close-up')
    op=tmp_path/'overrides.json';save(op,dict(schema_version='1.0',id='label-closeup',version='2.0',requests=[c]))
    second=prepare_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'second',rubric=rp,capture_overrides=op)
    assert first['plan_sha256']!=second['plan_sha256']
    actual=json.loads((tmp_path/'second/capture-plan.json').read_text())['requests'][0]
    assert actual['targets']==['/World/Panel'] and actual['min_width']==1920 and actual['requirement_ids']==['review.layout']


def test_custom_override_cannot_remove_fidelity(bundle,tmp_path):
    rubric=deepcopy(GENERAL_RUBRIC);rubric['criteria']=[rubric['criteria'][2]]
    rp=tmp_path/'rubric.json';save(rp,rubric)
    prepare_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'first',rubric=rp)
    c=json.loads((tmp_path/'first/capture-plan.json').read_text())['requests'][0]
    for k in ('requirement_ids','evidence_kind','feasibility_gaps'):c.pop(k)
    c['capabilities']=['geometry'];op=tmp_path/'overrides.json';save(op,dict(schema_version='1.0',id='bad',version='1',requests=[c]))
    with pytest.raises(ContractError):prepare_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'second',rubric=rp,capture_overrides=op)


def test_skill_export_is_self_contained_and_does_not_overwrite(tmp_path):
    out=tmp_path/'skills';manifest=export_skills(out)
    for name in NAMES:
        assert (out/name/'SKILL.md').is_file()
        assert (out/name/'agents/openai.yaml').is_file()
    from scene_acceptance.review_context import load_rubric
    assert load_rubric(out/NAMES[1]/'references/rubric.json')['id']=='assembly-review'
    for p,h in manifest['files'].items():assert sha(out/p)==h
    with pytest.raises(ContractError):export_skills(out)


def test_reference_image_enters_interpreter_request_as_image(bundle,tmp_path):
    kw=setup(tmp_path,bundle)
    raw=json.loads((bundle/'raw.json').read_text());raw['files'].append(dict(path='briefs/reference-a.png',role='reference_image',caption='Synthetic texture reference'));save(bundle/'raw.json',raw)
    prepare_scene(**kw)
    req=json.loads((kw['out']/'interpreter/request.json').read_text())
    ref=req['sources'][1]
    assert ref['role']=='reference_image' and Path(ref['image_path']).is_file()
    assert sha(ref['image_path'])==ref['sha256']
    assert json.loads((kw['out']/'capture-plan.json').read_text())['image_budget_after_references']==11


def test_prepared_model_never_runs_during_checks(bundle,tmp_path,monkeypatch):
    kw=setup(tmp_path,bundle);prepare_scene(**kw)
    monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**kw:pytest.fail('Checks reinterpreted brief'))
    assert evaluate_prepared(preparation=kw['out'],out=tmp_path/'run')['exit_code']==2


@pytest.mark.parametrize('fault',['missing-time','camera','target','fidelity','none'])
def test_motion_receipt_needs_planned_times_same_camera_and_targets(tmp_path,fault):
    from scene_acceptance.prepared_run import validate_receipt
    p=tmp_path/'frame.png';Image.new('RGB',(64,64),'white').save(p)
    request=dict(id='motion',requirement_ids=['brief.motion'],purpose='Inspect connection at start/middle/end',targets=['/World/Arm'],
        times_seconds=[0,1,2],capabilities=['geometry'],min_width=64,min_height=64,evidence_kind='motion_frames',feasibility_gaps=[])
    views=[dict(id=str(i),path='frame.png',time_seconds=i,covered_prims=['/World/Arm'],capabilities=['geometry'],view_roles=['motion'],camera_id='fixed',camera='Front',projection='orthographic',method='Fixture') for i in range(3)]
    if fault=='missing-time':views[-1]['time_seconds']=1
    if fault=='camera':views[-1]['camera_id']='other'
    if fault=='target':views[-1]['covered_prims']=[]
    if fault=='fidelity':views[-1]['capabilities']=[]
    plan=dict(plan_sha256='a'*64,scene_sha256='b'*64)
    receipt=dict(schema_version='1.0',**plan,requests=[dict(request_id='motion',status='supplied',view_ids=['0','1','2'],reason='Control')])
    rows,policy=validate_receipt(plan,dict(requests=[request],image_budget_after_references=3),dict(views=views),receipt,tmp_path)
    assert policy['brief.motion']['ready']==(fault=='none')
    assert rows[0]['status']==('supplied' if fault=='none' else 'missing')


def test_extra_unqualified_view_is_not_suitable_evidence(bundle,tmp_path):
    kw=setup(tmp_path,bundle);p=prepare_scene(**kw);ev=evidence(tmp_path,p)
    v=json.loads(ev['views'].read_text());extra=deepcopy(v['views'][0]);extra.update(id='irrelevant',covered_prims=[]);v['views'].append(extra);save(ev['views'],v)
    receipt=json.loads(ev['receipt'].read_text());receipt['requests'][0]['view_ids'].append('irrelevant');save(ev['receipt'],receipt)
    r=evaluate_prepared(preparation=kw['out'],out=tmp_path/'run',mode='judge',judge_config=judge_config(tmp_path),**ev)
    assert r['capture_counts']=={'supplied':1}
    assert r['evidence_policy']['brief.label']['evidence_ids']==['view:front']


def test_preparation_source_paths_cannot_escape(bundle,tmp_path):
    kw=setup(tmp_path,bundle)
    raw=json.loads((bundle/'raw.json').read_text());raw['files'][0]['path']='../../outside.txt';save(bundle/'raw.json',raw)
    with pytest.raises(Exception):prepare_scene(**kw)
    assert not kw['out'].exists()


def test_cli_and_library_use_same_plan_without_reinterpretation(bundle,tmp_path,capsys):
    from scene_acceptance.preparation import main as prepare_cli
    from scene_acceptance.prepared_run import main as run_cli
    assert prepare_cli(['--bundle-root',str(bundle),'--candidate','scene.usda','--out',str(tmp_path/'prepared')])==3  # Plan saved; no capture capability declared
    response=json.loads(capsys.readouterr().out)
    assert run_cli(['--preparation',str(tmp_path/'prepared'),'--expected-plan-sha256',response['data']['plan_sha256'],'--out',str(tmp_path/'run')])==0
    assert json.loads(capsys.readouterr().out)['data']['script_verdict']=='ACCEPT_FOR_USE'
