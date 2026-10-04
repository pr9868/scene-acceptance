"""Meaningful brief/measurement controls; no paid model calls in software tests."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import pytest
from pxr import Usd, UsdGeom
from scene_acceptance.artifact import EvidenceBundle, UsdArtifact
from scene_acceptance.brief_measurements import bounds, children, axis_gap, image_pixels, world_bounds, metadata
from scene_acceptance.briefs import evaluate_brief, load_brief
from scene_acceptance.cli import main
from scene_acceptance.model import BoundaryError, ContractError, MissingEvidence, sha
from scene_acceptance.pack_engine import Context

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('study_prepare',ROOT/'evaluation/brief-study-v1/prepare.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)

@pytest.fixture
def samples(tmp_path): return prepare.prepare(tmp_path/'samples')

def test_brief_variations_same_scene_and_hashed_sources(samples,tmp_path):
    root=samples/'panel'; original=sha(root/'scene.usda'); rows=[]
    for mode in ('size','image-a','image-b','conflict'):
        result=evaluate_brief(f'briefs/{mode}.json','scene.usda',bundle_root=root,out=tmp_path/mode)
        rows.append((result['core_verdict'],result['assessment_verdict']))
        assert sha(root/'scene.usda')==original
        saved=json.loads((tmp_path/mode/'report/brief-context.json').read_text())
        assert saved['provenance'].startswith('Synthetic')
        assert all(sha(tmp_path/mode/'report'/f['report_path'])==f['sha256'] for f in saved['files'])
    assert rows==[('ACCEPT_FOR_USE','ACCEPT_FOR_DECLARED_SCOPE'),('ACCEPT_FOR_USE','ACCEPT_FOR_DECLARED_SCOPE'),
                  ('REJECT','REJECT'),('ACCEPT_FOR_USE','NEEDS_REVIEW')]
    r=json.loads((tmp_path/'image-b/report/core-result.json').read_text())
    image=next(x for x in r['checks'] if x['id']=='spec.panel-image')
    assert image['evidence']['observations']['assessment']['items'][0]['differing_pixels']==65536

def test_brief_pending_mapping_and_unmapped_scope(samples,tmp_path):
    root=samples/'panel';p=root/'briefs/size.json';data=json.loads(p.read_text())
    data['mapping_review']['status']='pending';p.write_text(json.dumps(data))
    r=evaluate_brief('briefs/size.json','scene.usda',bundle_root=root,out=tmp_path/'pending')
    assert r['core_verdict']=='ACCEPT_FOR_USE' and r['assessment_verdict']=='NEEDS_REVIEW'

def test_manifest_tamper_escape_and_missing_files(samples,tmp_path):
    root=samples/'panel';p=root/'briefs/size.json'
    with pytest.raises(ContractError): load_brief(root,'briefs/size.json','0'*64)
    data=json.loads(p.read_text());data['files'][0]['path']='../../elsewhere'
    p.write_text(json.dumps(data))
    with pytest.raises(BoundaryError): load_brief(root,'briefs/size.json')
    data['files'][0]['path']='briefs/absent.md';p.write_text(json.dumps(data))
    with pytest.raises(BoundaryError): load_brief(root,'briefs/size.json')

def make_context(tmp_path):
    root=tmp_path/'bundle';root.mkdir();stage=Usd.Stage.CreateNew(str(root/'scene.usda'))
    world=UsdGeom.Xform.Define(stage,'/World');stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageMetersPerUnit(stage,.01);UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    a=UsdGeom.Cube.Define(stage,'/World/A');a.CreateSizeAttr(2)
    a.AddTranslateOp().Set((100,0,0));a.AddScaleOp().Set((50,10,10))
    a.CreateExtentAttr([(-999,-999,-999),(999,999,999)])
    b=UsdGeom.Cube.Define(stage,'/World/B');b.CreateSizeAttr(2);b.AddTranslateOp().Set((250,0,0));b.AddScaleOp().Set((10,10,10))
    stage.GetRootLayer().Save();bundle=EvidenceBundle(root,[])
    return Context(bundle,UsdArtifact(bundle,'scene.usda'),None,())

def test_bounds_units_transforms_and_untrusted_extents(tmp_path):
    ctx=make_context(tmp_path)
    p=dict(path='/World/A',time_code=0,size_m=[1,.2,.2],center_m=[1,0,0],tolerance_m=1e-9)
    assert bounds(ctx,p).status=='PASS'
    assert bounds(ctx,p|{'size_m':[2,.2,.2]}).status=='FAIL'
    assert bounds(ctx,p|{'path':'/World/Missing'}).status=='FAIL'
    with pytest.raises(MissingEvidence): world_bounds(ctx.artifact.stage,'/World',0)

def test_count_and_gap_do_not_invent_asset_passes(tmp_path):
    ctx=make_context(tmp_path)
    assert children(ctx,dict(parent='/World',type='Cube',count=2)).status=='PASS'
    assert children(ctx,dict(parent='/World',type='Cube',count=3)).status=='FAIL'
    p=dict(a='/World/A',b='/World/B',axis='x',time_code=0,minimum_m=.9,tolerance_m=1e-9)
    r=axis_gap(ctx,p);assert r.status=='PASS'
    assert r.evidence['assessment']['candidate_count']==1
    assert axis_gap(ctx,p|{'minimum_m':1}).status=='FAIL'


def test_explicit_metadata_targets_do_not_accept_usd_fallbacks(tmp_path):
    ctx=make_context(tmp_path)
    assert metadata(ctx,dict(values={'upAxis':'Z','metersPerUnit':.01},tolerance=1e-9)).status=='PASS'
    assert metadata(ctx,dict(values={'upAxis':'Y','metersPerUnit':1},tolerance=1e-9)).status=='FAIL'
    result=metadata(ctx,dict(values={'startTimeCode':0,'endTimeCode':0},tolerance=1e-9))
    assert result.status=='FAIL' and all(not x['authored'] for x in result.evidence['assessment']['items'])

def test_brief_cli_accept_reject_and_admission_failure(samples,tmp_path):
    root=samples/'panel'
    for mode,expected in [('size',0),('image-b',2),('conflict',3)]:
        assert main(['--brief',f'briefs/{mode}.json','--candidate','scene.usda','--bundle-root',str(root),'--out',str(tmp_path/('cli-'+mode))])==expected
    r=evaluate_brief('briefs/size.json','absent.usda',bundle_root=root,out=tmp_path/'absent')
    assert r['assessment_verdict'] in ('NEEDS_REVIEW','EVALUATION_ERROR')
    overview=json.loads((tmp_path/'absent/report/overview.json').read_text())
    assert overview['matrix'][0]['pass']==0

def test_cli_without_brief_runs_same_checks_as_explicit_baseline(samples,tmp_path):
    root=samples/'panel';reports=[]
    for mode,flags in [('direct',[]),('explicit',['--profile','usd-delivery-baseline'])]:
        out=tmp_path/mode
        assert main([*flags,'--candidate','scene.usda','--bundle-root',str(root),'--out',str(out)])==0
        reports.append(json.loads((out/'result.json').read_text()))
    a,b=reports
    assert a['identity']['candidate']==b['identity']['candidate']
    # The input-admission result is separate from the 27 selected baseline checks.
    assert len(a['coverage']['audit']['rows'])==len(b['coverage']['audit']['rows'])==27
    assert [(c['id'],c['status'],c['reason']) for c in a['checks']]==[(c['id'],c['status'],c['reason']) for c in b['checks']]
    assert 'no brief or contract supplied' in a['coverage']['profile_selection']
    assert not (tmp_path/'direct/brief-context.json').exists()

@pytest.mark.parametrize('flag,value',[('--claims','claims.json'),('--expected-brief-sha256','0'*64),
                                      ('--brief',''),('--contract',''),('--review-plan','')])
def test_implicit_baseline_does_not_silently_ignore_specification_arguments(samples,tmp_path,flag,value):
    out=tmp_path/'invalid'
    with pytest.raises(SystemExit) as exc:
        main(['--candidate','scene.usda','--bundle-root',str(samples/'panel'),'--out',str(out),flag,value])
    assert exc.value.code==4 and not out.exists()

def test_reference_must_be_declared_and_pixel_budget(samples):
    root=samples/'panel';bundle=EvidenceBundle(root,['textures/label.png']);artifact=UsdArtifact(bundle,'scene.usda')
    ctx=Context(bundle,artifact,None,())
    with pytest.raises(ContractError):
        image_pixels(ctx,dict(asset_attribute='/World/Looks/Label/Texture.inputs:file',reference_image='briefs/reference-a.png',max_channel_error=0))
