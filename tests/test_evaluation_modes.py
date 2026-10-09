"""Mode isolation, evidence provenance and advisory/measurement separation."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest
from scene_acceptance.cli import main
from scene_acceptance.evaluation import evaluate_scene
from scene_acceptance.model import ContractError, sha
from scene_acceptance.profiles import discover_artifact
from scene_acceptance.review_context import GENERAL_RUBRIC
from test_briefs import prepare


@pytest.fixture
def bundle(tmp_path):
    return prepare.prepare(tmp_path/'samples')/'panel'


def config(tmp_path, behavior='normal'):
    adapter=tmp_path/f'adapter-{behavior}.py'
    adapter.write_text('''import json,sys,time
r=json.load(sys.stdin)
behavior=sys.argv[1]
if behavior=='timeout': time.sleep(5)
if behavior=='malformed': print('bad json');sys.exit(0)
items=[]
for x in r['requirements']:
 c=r['evidence_coverage'][x['id']]; ids=c['suitable_evidence_ids']
 assessment=('concern' if behavior=='concern' else 'consistent') if ids else 'unknown'
 if behavior=='unsupported': assessment='consistent';ids=['scene:inventory']
 items.append(dict(requirement_id=x['id'],assessment=assessment,explanation='Deterministic software control only.',evidence_ids=ids[:1]))
if behavior=='unknown-id': items[0]['evidence_ids']=['invented']
if behavior=='missing': items.pop()
print(json.dumps(dict(request_sha256='0'*64 if behavior=='stale' else r['request_sha256'],items=items,limitations=['Test double, not model-quality validation.'])))
''')
    p=tmp_path/f'config-{behavior}.json'
    p.write_text(json.dumps(dict(driver='json-cli',executable=sys.executable,args=[str(adapter),behavior],model='test-double',effort='none',timeout_seconds=1)))
    return p


def views(tmp_path,bundle,*,textured=False,frames=1):
    from PIL import Image
    folder=tmp_path/'views';folder.mkdir()
    artifact=discover_artifact(bundle,'scene.usda')
    # This fixture is deliberately only an image/provenance transport control.
    p=folder/'frame.png';Image.new('RGB',(16,16),'white').save(p)
    data=dict(schema_version='1.0',scene_sha256=artifact.artifact_set_sha256,up_axis='Z',meters_per_unit=1,
        views=[dict(id=f'frame{i}',path='frame.png',sha256=sha(p),camera_id='front',camera='Test camera',projection='orthographic',
            time_seconds=0,method='synthetic software-control image',producer='test',
            capabilities=['geometry']+(['surface_materials'] if textured else []),limitations=['No real render or visual correctness claimed.'],covered_prims=[]) for i in range(frames)])
    path=folder/'views.json';path.write_text(json.dumps(data));return path


@pytest.mark.parametrize('mode',['checks','judge','both'])
@pytest.mark.parametrize('brief',[None,'briefs/image-b.json'])
def test_six_modes_preserve_measurements_and_sources(bundle,tmp_path,mode,brief,monkeypatch):
    before={str(p):sha(p) for p in bundle.rglob('*') if p.is_file()}
    kwargs={}
    if mode!='checks':kwargs['judge_config']=config(tmp_path)
    if mode=='checks':
        monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**k:pytest.fail('Checks invoked a model'))
    if mode=='judge':
        monkeypatch.setattr('scene_acceptance.evaluation.scripted',lambda *a,**k:pytest.fail('Judge ran content checks'))
    out=tmp_path/'out'
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=out,mode=mode,brief=brief,**kwargs)
    assert not r['errors'],r['errors']
    assert r['execution_status']=='completed'
    assert r['script']['artifact_verdict']==(None if mode=='judge' else 'REJECT' if brief else 'ACCEPT_FOR_USE')
    assert r['exit_code']==(2 if mode!='judge' and brief else 0 if mode=='checks' else 3)
    assert r['judge']['status']==('not_requested' if mode=='checks' else 'completed')
    assert {str(p):sha(p) for p in bundle.rglob('*') if p.is_file()}==before
    if mode!='checks':
        request=json.loads((out/('judge/request.json' if r['judge']['model_invoked'] else 'evidence/review-request.json')).read_text())
        assert request['script_verdict'] is None
        assert not any(x['id'].startswith('check:') for x in request['evidence'])
    for rel,h in json.loads((out/'manifest.json').read_text())['files'].items():assert sha(out/rel)==h


def test_legacy_and_unified_script_parity(bundle,tmp_path,capsys):
    legacy=tmp_path/'legacy';unified=tmp_path/'unified'
    base=['--bundle-root',str(bundle),'--candidate','scene.usda']
    assert main(base+['--out',str(legacy)])==0
    old=json.loads(capsys.readouterr().out);assert set(old)=={'verdict','complete','report'}
    assert main(base+['--out',str(unified),'--mode','checks'])==0
    new=json.loads(capsys.readouterr().out);assert new['schema_version']=='1.0'
    a=json.loads((legacy/'result.json').read_text());b=json.loads((unified/'script/result.json').read_text())
    assert [(x['id'],x['status'],x['reason']) for x in a['checks']]==[(x['id'],x['status'],x['reason']) for x in b['checks']]


def test_scene_only_judge_with_view_and_custom_rubric(bundle,tmp_path):
    manifest=views(tmp_path,bundle)
    rubric=deepcopy(GENERAL_RUBRIC);rubric['criteria']=rubric['criteria'][:2]
    rp=tmp_path/'rubric.json';rp.write_text(json.dumps(rubric))
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='judge',
                     judge_config=config(tmp_path),views=manifest,rubric=rp)
    assert not r['errors'],r['errors']
    assert r['judge']['counts']=={'consistent':2}
    assert r['script']['checks']==[] and r['script']['artifact_verdict'] is None and r['exit_code']==3


def test_schematic_views_do_not_support_material_or_motion_opinions(bundle,tmp_path):
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='both',judge_config=config(tmp_path),views=views(tmp_path,bundle,frames=3))
    assert not r['errors'],r['errors']
    items={x['requirement_id']:x for x in r['judge']['findings']}
    assert items['review.layout']['assessment']=='consistent'
    assert items['review.material-use']['assessment']=='unknown'
    assert 'review.motion' not in items  # This fixture has no authored motion.
    assert 'review.physics' not in items
    assert {r['area'] for r in r['judge']['unassessed_areas']} == {'motion', 'physics'}


def test_unsupported_opinion_is_retained_but_not_accepted(bundle,tmp_path):
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='both',judge_config=config(tmp_path,'unsupported'),views=views(tmp_path,bundle))
    assert not r['errors'],r['errors']
    assert all(x['model_assessment']=='consistent' and x['assessment']=='unknown' for x in r['judge']['findings'])
    assert r['exit_code']==3 and r['script']['artifact_verdict']=='ACCEPT_FOR_USE'


def test_script_aware_disagreement_does_not_clear_rejection(bundle,tmp_path):
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='both',
        brief='briefs/image-b.json',judge_config=config(tmp_path),judge_exposure='script-aware')
    assert not r['errors'],r['errors']
    assert r['script']['artifact_verdict']=='REJECT' and r['exit_code']==2
    req=json.loads((tmp_path/'out/judge/request.json').read_text())
    assert req['script_verdict']=='REJECT' and any(e['id'].startswith('check:') for e in req['evidence'])
    assert any(x['assessment']=='consistent' and x['requirement_id'].startswith('brief.') for x in r['judge']['findings'])


@pytest.mark.parametrize('behavior',['timeout','malformed','stale','unknown-id','missing'])
def test_judge_failure_preserves_completed_script_report(bundle,tmp_path,behavior):
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='both',judge_config=config(tmp_path,behavior),views=views(tmp_path,bundle))
    assert r['execution_status']=='partial' and r['exit_code']==4
    assert r['script']['artifact_verdict']=='ACCEPT_FOR_USE' and r['judge']['status']=='error'
    assert (tmp_path/'out/script/result.json').is_file() and (tmp_path/'out/judge/stdout.log').is_file()


@pytest.mark.parametrize('fault',['scene','pixels','axis','escape','time','prim'])
def test_invalid_view_evidence_prevents_model_invocation(bundle,tmp_path,fault,monkeypatch):
    path=views(tmp_path,bundle);data=json.loads(path.read_text())
    if fault=='scene':data['scene_sha256']='0'*64
    if fault=='pixels':data['views'][0]['sha256']='0'*64
    if fault=='axis':data['up_axis']='Y'
    if fault=='escape':data['views'][0]['path']='../../outside.png'
    if fault=='time':data['views'][0]['time_seconds']=100000
    if fault=='prim':data['views'][0]['covered_prims']=['/Absent']
    path.write_text(json.dumps(data))
    monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**k:pytest.fail('Invalid evidence reached the model'))
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='judge',judge_config=config(tmp_path),views=path)
    assert r['execution_status']=='failed' and r['exit_code']==4 and r['errors']


def test_changed_source_after_checks_prevents_review(bundle,tmp_path,monkeypatch):
    from scene_acceptance.evaluation import scripted as real
    def mutate(*a,**kw):
        result=real(*a,**kw);(bundle/'scene.usda').write_text((bundle/'scene.usda').read_text()+'\n# changed\n');return result
    monkeypatch.setattr('scene_acceptance.evaluation.scripted',mutate)
    monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**k:pytest.fail('Changed evidence reached the model'))
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='both',judge_config=config(tmp_path))
    assert r['exit_code']==4 and r['execution_status']=='partial' and r['source_unchanged'] is False


def test_missing_model_config_never_silently_falls_back(bundle,tmp_path):
    with pytest.raises(ContractError):evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='both')
    assert not (tmp_path/'out').exists()


def test_capabilities_and_catalog_do_not_call_a_model(capsys,monkeypatch):
    monkeypatch.setattr('scene_acceptance.judge.run_request',lambda *a,**k:pytest.fail('Discovery invoked a model'))
    assert main(['--capabilities'])==0
    assert json.loads(capsys.readouterr().out)['modes']==['checks','judge','both']
    assert main(['--list-tests'])==0
    c=json.loads(capsys.readouterr().out)
    assert len(c['baseline'])==27 and len(c['advisory_rubric']['criteria'])==5
    checks={row['id'] for row in c['configurable_checks']}
    assert {'geometry.clearance.sweep','behavior.state.agreement','motion.continuous.connection'} <= checks
    assert not any(row['pack'] in ('brief.four-job','physics.incline-worker') for row in c['configurable_checks'])
    assert {row['pack'] for row in c['example_checks']} == {'brief.four-job','physics.incline-worker'}


def test_catalog_matches_current_pack_declarations():
    from scene_acceptance.packs import default_registry
    from scene_acceptance.test_catalog import test_catalog
    catalog={c['id']:c for c in test_catalog()['configurable_checks']}
    actual={p['id']+'.'+name:c for p in default_registry().catalog() for name,c in p['checks'].items()}
    assert set(catalog)==set(actual)
    for key,c in actual.items():
        for field in ('description','coverage','limitations','parameters'):assert catalog[key][field]==c[field]


@pytest.mark.parametrize('behavior,expected',[('normal',0),('concern',3)])
def test_combined_custom_scope_accepts_or_escalates_without_changing_script(bundle,tmp_path,behavior,expected):
    rp=tmp_path/'rubric.json';r=deepcopy(GENERAL_RUBRIC);r['criteria']=r['criteria'][:2];rp.write_text(json.dumps(r))
    result=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='both',
        judge_config=config(tmp_path,behavior),views=views(tmp_path,bundle),rubric=rp)
    assert not result['errors'],result['errors']
    assert result['script']['artifact_verdict']=='ACCEPT_FOR_USE' and result['exit_code']==expected


def test_real_distinct_frame_times_enable_bounded_motion_review(bundle,tmp_path):
    from pxr import Usd, UsdGeom
    stage=Usd.Stage.Open(str(bundle/'scene.usda'));stage.SetStartTimeCode(0);stage.SetEndTimeCode(48);stage.SetTimeCodesPerSecond(24)
    op = UsdGeom.XformOp(stage.GetPrimAtPath('/World').GetAttribute('xformOp:translate'))
    op.Set((0,0,0),0);op.Set((1,0,0),48);stage.GetRootLayer().Save()
    path=views(tmp_path,bundle,frames=3);data=json.loads(path.read_text())
    for i,v in enumerate(data['views']):v['time_seconds']=i
    path.write_text(json.dumps(data))
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='judge',judge_config=config(tmp_path),views=path)
    assert not r['errors'],r['errors']
    motion=next(x for x in r['judge']['findings'] if x['requirement_id']=='review.motion')
    assert motion['assessment']=='consistent' and len(motion['evidence_coverage']['suitable_evidence_ids'])==3
    # Same pixels at distinct declared timestamps are caller evidence, not proof of a real animation.


def test_library_and_cli_refuse_silent_ignored_options(bundle,tmp_path):
    with pytest.raises(ContractError):evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='checks',judge_config=config(tmp_path))
    with pytest.raises(SystemExit):main(['--capabilities','--baseline','anything'])
    with pytest.raises(SystemExit):main(['--bundle-root',str(bundle),'--out',str(tmp_path/'out'),'--candidate','scene.usda','--mode','judge','--profile','usd-delivery-baseline'])


def test_normal_resolution_views_do_not_use_tiny_reference_decoder(bundle,tmp_path):
    from PIL import Image
    path=views(tmp_path,bundle);data=json.loads(path.read_text());image=path.parent/'frame.png'
    Image.new('RGB',(960,600),'white').save(image)
    data['views'][0]['sha256']=sha(image);path.write_text(json.dumps(data))
    r=evaluate_scene(bundle_root=bundle,candidate='scene.usda',out=tmp_path/'out',mode='judge',judge_config=config(tmp_path),views=path)
    assert not r['errors'],r['errors']
    assert r['judge']['status']=='completed' and r['judge']['counts']['consistent']==2
    from scene_acceptance.brief_measurements import read_image
    from scene_acceptance.model import MissingEvidence
    with pytest.raises(MissingEvidence):read_image(image) # Exact-pixel comparison retains its original budget.


def test_view_decoder_retains_a_pixel_budget(tmp_path):
    from PIL import Image
    from scene_acceptance.review_context import read_view_image
    p=tmp_path/'too-large.png';Image.new('RGB',(4001,4000),'white').save(p)
    with pytest.raises(ContractError,match='16 million'):read_view_image(p)
