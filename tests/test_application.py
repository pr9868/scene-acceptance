"""Adopter workflow controls. Synthetic adapters test transport, not model quality."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from copy import deepcopy
import pytest
from jsonschema import Draft202012Validator
from scene_acceptance.application import invoke,main
from scene_acceptance.application_schemas import SCHEMAS
from scene_acceptance.execution import RunControl
from scene_acceptance.preparation import prepare_scene,load_preparation,allowed_catalog
from scene_acceptance.scope import approve_scope,bind_preparation
from scene_acceptance.prepared_run import evaluate_prepared,validate_prepared_evidence,validate_receipt
from scene_acceptance.review_context import save,GENERAL_RUBRIC
from scene_acceptance.model import ContractError,sha,digest_json
from test_preparation import setup,evidence,bundle
from test_evaluation_modes import config,views


def assert_dead(pid):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        try:os.kill(pid,0)
        except ProcessLookupError:return
        time.sleep(.05)
    pytest.fail('Owned adapter process still exists: '+str(pid))

def valid(schema,value):Draft202012Validator(SCHEMAS[schema]).validate(value)

def scripted_scope(tmp_path,bundle):
    kw=setup(tmp_path,bundle)
    adapter=tmp_path/'interpreter.py'
    adapter.write_text(adapter.read_text().replace("print(json.dumps(dict(request_sha256=", "items=items[:1]\nprint(json.dumps(dict(request_sha256="))
    return kw,prepare_scene(**kw)

def approval(tmp_path,kw,plan,status='approved'):
    out=tmp_path/'approval.json'
    approve_scope(preparation=kw['out'],out=out,expected_scope_sha256=plan['scope_sha256'],reviewer='Caller test',reason='Reviewed source requirements against proposed checks',status=status)
    return out

def resize(bundle,size=.30):
    from pxr import Usd,UsdGeom
    stage=Usd.Stage.Open(str(bundle/'scene.usda'));mesh=UsdGeom.Mesh(stage.GetPrimAtPath('/World/Panel'))
    pts=mesh.GetPointsAttr().Get();lo=min(v[0] for v in pts);hi=max(v[0] for v in pts)
    from pxr import Gf
    pts=[Gf.Vec3f((v[0]-lo)*size/(hi-lo),v[1],v[2]) for v in pts]
    mesh.GetPointsAttr().Set(pts);mesh.GetExtentAttr().Set(UsdGeom.PointBased.ComputeExtent(pts));stage.GetRootLayer().Save()

def test_approval_rebind_and_comparison_leave_desired_targets_fixed(tmp_path,bundle,monkeypatch):
    kw,p=scripted_scope(tmp_path,bundle);a=approval(tmp_path,kw,p)
    rejected=evaluate_prepared(preparation=kw['out'],out=tmp_path/'old',approval=a)
    assert rejected['exit_code']==2 and rejected['mapping_review']=='reviewed'
    resize(bundle)
    monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**k:pytest.fail('Rebind invoked model'))
    bound=bind_preparation(preparation=kw['out'],bundle_root=bundle,candidate='scene.usda',out=tmp_path/'rebound',expected_scope_sha256=p['scope_sha256'])
    assert bound['scope_sha256']==p['scope_sha256'] and bound['scene_sha256']!=p['scene_sha256']
    r=evaluate_prepared(preparation=tmp_path/'rebound',out=tmp_path/'new',approval=a,previous_run=tmp_path/'old')
    assert r['exit_code']==0 and r['scope_verdict']=='ACCEPT_FOR_DECLARED_SCOPE'
    assert r['comparison']['same_scope']
    assert any(x['id']=='check:spec.panel' and x['change']=='improved_in_stated_scope' for x in r['comparison']['changes'])
    valid('prepared-result-v1',r);valid('preparation-plan-v1',bound)
    assert json.loads((kw['out']/p['bundle']/p['brief']).read_text())['mapping_review']['status']=='pending'
    with pytest.raises(ContractError):bind_preparation(preparation=kw['out'],bundle_root=bundle,candidate='scene.usda',out=tmp_path/'bad',expected_scope_sha256='0'*64)

@pytest.mark.parametrize('status,code',[('rejected',3),('needs_review',3)])
def test_nonapproval_cannot_clear_mapping(tmp_path,bundle,status,code):
    resize(bundle);kw,p=scripted_scope(tmp_path,bundle);a=approval(tmp_path,kw,p,status)
    r=evaluate_prepared(preparation=kw['out'],out=tmp_path/'run',approval=a)
    assert r['exit_code']==code

def test_wrong_scope_approval_rejected(tmp_path,bundle):
    kw,p=scripted_scope(tmp_path,bundle);a=approval(tmp_path,kw,p)
    data=json.loads(a.read_text());data['scope_sha256']='0'*64;save(a,data)
    r=invoke('evaluate',preparation=kw['out'],out=tmp_path/'run',approval=a)
    assert r['exit_code']==4 and r['errors'][0]['code']=='ContractError'

def test_distinct_viewpoints_cannot_share_one_image(tmp_path,bundle):
    kw,p=setup(tmp_path,bundle),None;p=prepare_scene(**kw);ev=evidence(tmp_path,p)
    captures=json.loads((kw['out']/'capture-plan.json').read_text())
    front=captures['requests'][0];back=deepcopy(front);back.update(id='rear-view',view_role='rear')
    captures['requests'].append(back)
    manifest=json.loads(ev['views'].read_text());manifest['views'][0]['view_roles']=['front','rear']
    receipt=json.loads(ev['receipt'].read_text());r=deepcopy(receipt['requests'][0]);r['request_id']='rear-view';receipt['requests'].append(r)
    rows,policy=validate_receipt(p,captures,manifest,receipt,ev['views'].parent)
    assert all(r['status']=='missing' for r in rows) and not policy['brief.label']['ready']
    assert all('reused across distinct' in r['gaps'][0] for r in rows)

@pytest.mark.parametrize('fault',['missing-receipt','missing-file','bad-scene','wrong-role','wrong-camera','wrong-projection'])
def test_evidence_preflight_and_both_preserve_structural_failures(tmp_path,bundle,fault,monkeypatch):
    kw=setup(tmp_path,bundle)
    if fault in ('wrong-camera','wrong-projection'):
        adapter=tmp_path/'interpreter.py'
        adapter.write_text(adapter.read_text().replace("camera_id=None,projection=None","camera_id='required',projection='perspective'"))
    p=prepare_scene(**kw);ev=evidence(tmp_path,p)
    data=json.loads(ev['views'].read_text())
    if fault=='bad-scene':data['scene_sha256']='0'*64
    if fault=='wrong-role':data['views'][0]['view_roles']=['rear']
    if fault=='wrong-camera':data['views'][0]['projection']='perspective'
    if fault=='wrong-projection':data['views'][0]['camera_id']='required'
    save(ev['views'],data)
    if fault=='missing-receipt':ev.pop('receipt')
    if fault=='missing-file':ev['receipt']=tmp_path/'absent.json'
    monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**k:pytest.fail('Invalid evidence reached model'))
    pre=validate_prepared_evidence(preparation=kw['out'],out=tmp_path/'preflight',**ev)
    valid('evidence-result-v1',pre)
    assert pre['model_calls']==0 and pre['exit_code'] in (3,4)
    r=evaluate_prepared(preparation=kw['out'],out=tmp_path/'run',mode='both',judge_config=config(tmp_path),**ev)
    assert r['script_verdict']=='REJECT'
    assert r['exit_code']==(4 if fault in ('missing-receipt','missing-file','bad-scene') else 2)

def test_no_evidence_means_zero_model_calls(tmp_path,bundle,monkeypatch):
    from scene_acceptance.evaluation import evaluate_scene
    monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**k:pytest.fail('Unanswerable review invoked model'))
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='both',judge_config=config(tmp_path))
    assert not r['judge']['model_invoked'] and r['judge']['counts']=={'unknown':3}

def test_replay_identical_only_and_reports_are_immutable(tmp_path,bundle,monkeypatch):
    args=dict(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'prepared')
    first=invoke('prepare',reuse_completed=True,**args);valid('application-envelope-v1',first)
    assert first['exit_code']==0,first['errors']
    monkeypatch.setattr('scene_acceptance.preparation.prepare_scene',lambda **k:pytest.fail('Cache executed preparation'))
    second=invoke('prepare',reuse_completed=True,**args)
    assert second['reused'] and second['data']==first['data']
    (bundle/'scene.usda').write_text((bundle/'scene.usda').read_text()+'\n# revision')
    changed=invoke('prepare',reuse_completed=True,**args)
    assert changed['exit_code']==4 and not changed['reused']

def test_replay_refuses_modified_output(tmp_path,bundle):
    args=dict(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'prepared')
    assert invoke('prepare',reuse_completed=True,**args)['exit_code']==0
    (tmp_path/'prepared/report.html').write_text('changed')
    r=invoke('prepare',reuse_completed=True,**args)
    assert r['exit_code']==4 and 'modified' in r['errors'][0]['message']

def test_rejected_scene_is_completed_and_reusable(tmp_path,bundle):
    kw,p=scripted_scope(tmp_path,bundle)
    args=dict(preparation=kw['out'],out=tmp_path/'run',reuse_completed=True)
    r=invoke('evaluate',**args);assert r['status']=='completed' and r['exit_code']==2
    assert invoke('evaluate',**args)['reused']

@pytest.mark.parametrize('args',[[],['evaluate'],['evaluate','--preparation','missing','--out','missing-output'],['doctor','--unknown']])
def test_cli_errors_are_json_envelopes(args,capsys):
    assert main(args)==4
    result=json.loads(capsys.readouterr().out);valid('application-envelope-v1',result)
    assert result['errors']

def test_progress_and_pre_cancel(tmp_path,bundle):
    events=[];cancel=tmp_path/'cancel';cancel.touch()
    r=invoke('prepare',control=RunControl(cancel_file=str(cancel),progress=events.append),bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out')
    assert r['status']=='cancelled' and not (tmp_path/'out').exists()
    r=invoke('prepare',control=RunControl(progress=events.append),bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out')
    assert r['exit_code']==0 and events[0]['phase']=='prepare.started' and events[-1]['phase']=='prepare.completed'

def test_deadline_kills_adapter_and_descendants(tmp_path,bundle):
    kw=setup(tmp_path,bundle);child=tmp_path/'child.pid';leader=tmp_path/'leader.pid'
    (tmp_path/'interpreter.py').write_text(f"import subprocess,time,os\nfrom pathlib import Path\nPath({str(leader)!r}).write_text(str(os.getpid()))\np=subprocess.Popen(['{sys.executable}','-c','import time;time.sleep(30)'])\nPath({str(child)!r}).write_text(str(p.pid))\ntime.sleep(30)\n")
    # Deadline includes preparation; allow USD admission before it expires.
    r=invoke('prepare',control=RunControl(deadline_seconds=2),**kw)
    assert r['status']=='timed_out' and r['exit_code']==4
    for path in (leader,child):
        assert path.exists()
        pid=int(path.read_text())
        # Reparented killed children can briefly remain zombies; they must not run.
        assert_dead(pid)

def test_sigterm_is_a_structured_cancellation_and_cleans_group(tmp_path,bundle):
    kw=setup(tmp_path,bundle);pidfile=tmp_path/'pids.json'
    (tmp_path/'interpreter.py').write_text(f"import subprocess,time,os,json\nfrom pathlib import Path\np=subprocess.Popen([{sys.executable!r},'-c','import time;time.sleep(30)'])\nPath({str(pidfile)!r}).write_text(json.dumps([os.getpid(),p.pid]))\ntime.sleep(30)\n")
    runner=tmp_path/'runner.py'
    runner.write_text("import json\nfrom scene_acceptance.application import invoke\nprint(json.dumps(invoke('prepare',**"+repr({k:str(v) for k,v in kw.items()})+")))")
    proc=subprocess.Popen([sys.executable,str(runner)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+10
        while not pidfile.exists() and time.monotonic()<deadline:time.sleep(.05)
        assert pidfile.exists()
        proc.send_signal(signal.SIGTERM);stdout,stderr=proc.communicate(timeout=10)
        result=json.loads(stdout);assert result['status']=='cancelled',result
        for pid in json.loads(pidfile.read_text()):
            assert_dead(pid)
    finally:
        if proc.poll() is None:proc.kill();proc.wait()

@pytest.mark.parametrize('key,value',[('max_model_calls',0),('max_request_bytes',1),('max_output_bytes',1),('modalities',['text'])])
def test_model_budgets_and_modality_preserve_script(tmp_path,bundle,key,value):
    cp=config(tmp_path);c=json.loads(cp.read_text());c[key]=value;save(cp,c)
    r=invoke('check',bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='both',judge_config=cp,views=views(tmp_path,bundle))
    assert r['exit_code']==4 and r['data']['script']['artifact_verdict']=='ACCEPT_FOR_USE'

def test_doctor_and_named_profiles_no_model(tmp_path,bundle,monkeypatch):
    monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**k:pytest.fail('Discovery invoked model'))
    r=invoke('doctor',bundle_root=bundle,candidate='scene.usda')
    assert r['data']['baseline_ready'] and r['data']['scene']['admitted']
    assert len(r['data']['automatic_mapping_types'])>5
    for name,n in [('general',3),('static-visual',3),('animated-visual',4)]:
        p=prepare_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/name,review_profile=name)
        assert len(json.loads((tmp_path/name/'rubric.json').read_text())['criteria'])==n
        valid('preparation-plan-v1',p)

def test_origin_and_interpreter_author_remain_distinct(tmp_path,bundle):
    kw=setup(tmp_path,bundle);raw=json.loads((bundle/'raw.json').read_text())
    raw['source_origin']=dict(provided_by='human',reference='Caller-provided brief v1');save(bundle/'raw.json',raw)
    p=prepare_scene(**kw);brief=json.loads((kw['out']/p['bundle']/p['brief']).read_text())
    assert brief['checks'][0]['specification_source']['provided_by']=='human'
    assert brief['requirements'][0]['mapping_author']['kind']=='llm-interpreter'

def test_environment_migration_is_explicit_and_preserves_scope(tmp_path,bundle,monkeypatch):
    from scene_acceptance.environment import environment_identity
    p=prepare_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'old')
    env=environment_identity();env['python']='different'
    monkeypatch.setattr('scene_acceptance.environment.environment_identity',lambda:env)
    with pytest.raises(ContractError,match='environment changed'):load_preparation(tmp_path/'old')
    with pytest.raises(ContractError,match='reviewer'):bind_preparation(preparation=tmp_path/'old',bundle_root=bundle,candidate='scene.usda',out=tmp_path/'new',expected_scope_sha256=p['scope_sha256'],migrate_runtime=True)
    bound=bind_preparation(preparation=tmp_path/'old',bundle_root=bundle,candidate='scene.usda',out=tmp_path/'new',expected_scope_sha256=p['scope_sha256'],migrate_runtime=True,reviewer='Caller',reason='Reviewed dependency migration')
    assert bound['scope_sha256']==p['scope_sha256'] and bound['binding']['runtime_migration']
    assert load_preparation(tmp_path/'new')[1]==bound

def test_dependency_budget_propagates_prepare_bind_and_run(tmp_path):
    from pxr import Usd,Sdf,UsdGeom
    bundle=tmp_path/'layers';bundle.mkdir()
    stage=Usd.Stage.CreateNew(str(bundle/'scene.usda'));UsdGeom.SetStageMetersPerUnit(stage,1);UsdGeom.SetStageUpAxis(stage,'Z')
    world=UsdGeom.Xform.Define(stage,'/World').GetPrim();stage.SetDefaultPrim(world)
    for i in range(65):Sdf.Layer.CreateNew(str(bundle/f'l{i}.usda')).Save()
    stage.GetRootLayer().subLayerPaths=[f'l{i}.usda' for i in range(65)];stage.GetRootLayer().Save()
    with pytest.raises(Exception):prepare_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'small')
    p=prepare_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'large',max_dependency_files=128)
    assert load_preparation(tmp_path/'large')[1]['max_dependency_files']==128
    r=evaluate_prepared(preparation=tmp_path/'large',out=tmp_path/'run')
    assert r['execution_status']=='completed' and not r['errors']
    b=bind_preparation(preparation=tmp_path/'large',bundle_root=bundle,candidate='scene.usda',out=tmp_path/'bound',expected_scope_sha256=p['scope_sha256'])
    assert b['max_dependency_files']==128

def test_all_public_schemas_match_packaged_files():
    from scene_acceptance.model import schema
    for name,definition in SCHEMAS.items():assert schema(name)==definition

@pytest.mark.parametrize('type_id,parameters',[
 ('motion.timing.clock',dict(duration_s=2,tolerance_s=.001,time_codes_per_second=24)),
 ('motion.timing.positions',dict(path='/World/Panel',tolerance_m=.001,samples=[dict(elapsed_s=0,world_origin_m=[0,0,0])])),
 ('motion.connection.distance',dict(a=dict(path='/World/Panel',local_point=[0,0,0]),b=dict(path='/World/Panel',local_point=[0,0,0]),interval_s=[0,0],segments=1,schedule='uniform',max_gap_m=.001)),
 ('materials.delivery',dict(bindings={'/World/Panel':'/World/Looks/Label'},purpose='allPurpose',render_context='',surface_shader_id='UsdPreviewSurface')),
 ('textures.decode.image',dict(asset_attribute='/World/Looks/Label/Texture.inputs:file',max_pixels=65536,max_bytes=1048576))])
def test_new_bounded_mapping_types_execute_registered_checks(tmp_path,bundle,type_id,parameters):
    kw=setup(tmp_path,bundle);adapter=tmp_path/'interpreter.py'
    text=adapter.read_text().replace("print(json.dumps(dict(request_sha256=",f"items=items[:1]\nchecks[0].update(type_id={type_id!r},parameters_json={json.dumps(parameters)!r})\nprint(json.dumps(dict(request_sha256=")
    adapter.write_text(text);p=prepare_scene(**kw)
    r=evaluate_prepared(preparation=kw['out'],out=tmp_path/'run')
    check=next(c for c in r['findings'] if c['id']=='check:spec.panel')
    assert check['status'] in ('PASS','FAIL','UNKNOWN') and r['execution_status']=='completed'
    assert check['parameters']==parameters

def test_caller_outcome_review_is_snapshot_bound_and_separate_from_scope_approval(tmp_path,bundle):
    resize(bundle);kw=setup(tmp_path,bundle);p=prepare_scene(**kw);a=approval(tmp_path,kw,p)
    first=evaluate_prepared(preparation=kw['out'],out=tmp_path/'first',approval=a)
    assert first['scope_verdict']=='NEEDS_REVIEW' and first['script_verdict']=='ACCEPT_FOR_USE'
    assessment=json.loads((tmp_path/'first/evaluation/script/report/assessment.json').read_text())
    (tmp_path/'review-note.txt').write_text('Synthetic caller outcome-review control, not a real visual judgment.')
    review=dict(schema_version='1.0',snapshot_sha256=assessment['snapshot_sha256'],reviews=[
        dict(item_id='label',status='approved',reviewer='Test caller',reason='Synthetic review transport test',
             evidence=[dict(path='review-note.txt',sha256=sha(tmp_path/'review-note.txt'))])])
    save(tmp_path/'review.json',review)
    r=evaluate_prepared(preparation=kw['out'],out=tmp_path/'second',approval=a,review_record=tmp_path/'review.json')
    assert r['scope_verdict']=='ACCEPT_FOR_DECLARED_SCOPE',r
    review['snapshot_sha256']='0'*64;save(tmp_path/'stale.json',review)
    stale=evaluate_prepared(preparation=kw['out'],out=tmp_path/'third',approval=a,review_record=tmp_path/'stale.json')
    assert stale['scope_verdict']=='NEEDS_REVIEW'


def test_provider_schema_adapter_keeps_local_uniqueness_validation():
    from scene_acceptance.judge import provider_schema
    from scene_acceptance.preparation import INTERPRETATION_SCHEMA
    full=INTERPRETATION_SCHEMA['properties']['requirements']['items']['properties']['source_ids']
    remote=provider_schema(INTERPRETATION_SCHEMA)['properties']['requirements']['items']['properties']['source_ids']
    assert full['uniqueItems'] and 'uniqueItems' not in remote
    assert list(Draft202012Validator(full).iter_errors(['brief:0','brief:0']))


def test_interpreter_schema_exposes_required_spec_prefix():
    from scene_acceptance.preparation import INTERPRETATION_SCHEMA
    check=INTERPRETATION_SCHEMA['properties']['requirements']['items']['properties']['checks']['items']
    good=dict(id='spec.panel-size',type_id='brief.measurements.bounds',parameters_json='{}')
    assert not list(Draft202012Validator(check).iter_errors(good))
    assert list(Draft202012Validator(check).iter_errors(dict(good,id='panel-size')))


def test_distinct_view_ids_with_identical_bytes_do_not_cover_two_views(tmp_path, bundle):
    kw = setup(tmp_path, bundle)
    plan = prepare_scene(**kw)
    ev = evidence(tmp_path, plan)
    captures = json.loads((kw['out'] / 'capture-plan.json').read_text())
    rear = deepcopy(captures['requests'][0]); rear.update(id='rear-view', view_role='rear')
    captures['requests'].append(rear)
    manifest = json.loads(ev['views'].read_text())
    view = deepcopy(manifest['views'][0]); view.update(id='rear', path='rear.png', view_roles=['rear'], camera_id='rear')
    (ev['views'].parent / 'rear.png').write_bytes((ev['views'].parent / manifest['views'][0]['path']).read_bytes())
    manifest['views'].append(view)
    receipt = json.loads(ev['receipt'].read_text())
    receipt['requests'].append(dict(request_id='rear-view', status='supplied', view_ids=['rear'], reason='Aliased image control'))
    rows, policy = validate_receipt(plan, captures, manifest, receipt, ev['views'].parent)
    assert not policy['brief.label']['ready']
    assert all(r['status'] == 'missing' for r in rows)


def test_report_diff_distinguishes_regression_unknown_and_scope_change(tmp_path):
    from scene_acceptance.findings import compare_runs
    previous = dict(scope_sha256='a'*64, findings=[dict(id='binding', status='PASS'), dict(id='view', status='supplied')])
    path = tmp_path / 'previous.json'; save(path, previous)
    current = dict(scope_sha256='a'*64, findings=[dict(id='binding', status='FAIL'), dict(id='view', status='missing')])
    changes = compare_runs(path, current)['changes']
    assert [r['change'] for r in changes] == ['regressed_in_stated_scope', 'newly_unresolved_in_stated_scope']
    current['scope_sha256'] = 'b'*64
    assert all(r['change'] == 'changed' for r in compare_runs(path, current)['changes'])
