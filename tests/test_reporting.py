"""Reporting must never turn absence, unsupported coverage or warnings into success."""
import csv
import json
from pathlib import Path
import pytest
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf
from scene_acceptance.pack_engine import evaluate_packs
from scene_acceptance.profiles import baseline_contract
from scene_acceptance.packs import default_registry
from scene_acceptance.report import write_report
from scene_acceptance.model import sha


def make_stage(tmp_path):
    root=tmp_path/'bundle';root.mkdir()
    stage=Usd.Stage.CreateNew(str(root/'scene.usda'))
    world=UsdGeom.Xform.Define(stage,'/World');stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageMetersPerUnit(stage,1);UsdGeom.SetStageUpAxis(stage,'Y')
    return root,stage


def mesh(stage,path,offset=0,bad=False):
    m=UsdGeom.Mesh.Define(stage,path)
    m.CreatePointsAttr([(offset,0,0),(offset+1,0,0),(offset+(2 if bad else 0),0 if bad else 1,0)])
    m.CreateFaceVertexCountsAttr([3]);m.CreateFaceVertexIndicesAttr([0,1,2])
    m.CreateSubdivisionSchemeAttr('none')
    if not bad: m.CreateNormalsAttr([(0,0,1)]*3)
    m.CreateExtentAttr([(offset,0,0),(offset+(2 if bad else 1),0 if bad else 1,0)])
    return m


def run(root,checks=None):
    contract,_=baseline_contract(root,'scene.usda')
    if checks:
        contract['checks']=[c for c in contract['checks'] if c['id'] in checks]
        contract['packs']={k:v for k,v in contract['packs'].items() if k in {c['pack'] for c in contract['checks']}}
    return evaluate_packs(None,'scene.usda',bundle_root=root,contract_data=contract)


def row(report,id): return next(x for x in report['coverage']['audit']['rows'] if x['id']==id)


def pointer(data,p):
    for key in p.strip('/').split('/'):
        key=key.replace('~1','/').replace('~0','~')
        data=data[int(key)] if isinstance(data,list) else data[key]
    return data


def test_mixed_findings_have_exact_subject_counts_and_provider_parity(tmp_path):
    root,s=make_stage(tmp_path);mesh(s,'/World/Good');mesh(s,'/World/Bad',3,True);s.GetRootLayer().Save()
    before=sha(root/'scene.usda');r=run(root)
    assert r['verdict']=='REJECT'
    assert row(r,'nv.03')['counts']['fail_count']==1
    assert row(r,'nv.03')['counts']['pass_count']==1
    assert row(r,'nv.05')['counts']['warning_count']==1
    assert row(r,'nv.05')['status']=='PASS_WITH_WARNINGS'
    assert row(r,'nv.02')['counts']['skipped_count']==1
    assert row(r,'nv.02')['status']=='PARTIAL_COVERAGE'
    import usd_validation_nvidia as nv
    registry=nv.CategoryRuleRegistry()
    # Compare the observed adapter with untouched direct upstream runs, including all issues.
    for check in r['checks']:
        obs=check.get('evidence',{}).get('observations',{})
        if check['id'].startswith('nv.'):
            cls=registry.find_rule(obs['executed'][0]); engine=nv.ValidationEngine(init_rules=False,variants=False);engine.enable_rule(cls)
            direct=[(i.severity.name,i.message,str(i.at) if i.at is not None else None) for i in engine.validate(s)]
            assert direct==[(i['severity'],i['message'],i['at']) for i in obs['issues']]
    assert sha(root/'scene.usda')==before
    dest=tmp_path/'report';write_report(r,dest)
    for name in ('subjects.csv','findings.csv','checks.csv'):
        for item in csv.DictReader((dest/name).open()): assert pointer(r,item['evidence_pointer']) is not None
    assert len(list(csv.DictReader((dest/'subjects.csv').open())))>0
    for name,digest in json.loads((dest/'manifest.json').read_text())['files'].items(): assert sha(dest/name)==digest


def test_no_meshes_are_not_counted_as_mesh_passes(tmp_path):
    root,s=make_stage(tmp_path);UsdGeom.Cube.Define(s,'/World/Cube');s.GetRootLayer().Save()
    r=run(root)
    assert r['coverage']['inventory']['meshes']==0
    for id in ('nv.00','nv.02','nv.03','nv.04','nv.05','audit.textures','audit.authored_motion'):
        assert row(r,id)['status']=='NO_APPLICABLE_SUBJECTS'
        assert row(r,id)['counts']['pass_count']==0
    domains={x['domain']:x['status'] for x in r['coverage']['audit']['domains']}
    assert domains['motion_requirements']=='NOT_SELECTED'
    assert domains['simulation']=='NOT_SELECTED'


def test_animation_sample_coverage_is_not_intent(tmp_path):
    root,s=make_stage(tmp_path)
    s.SetStartTimeCode(0);s.SetEndTimeCode(2);s.SetTimeCodesPerSecond(1)
    x=UsdGeom.Xform.Define(s,'/World/Moving');op=x.AddTranslateOp();op.Set((0,0,0),0);op.Set((1,0,0),2);s.GetRootLayer().Save()
    r=run(root,['audit.authored_motion'])
    assert row(r,'audit.authored_motion')['counts']['pass_count']==1
    obs=r['checks'][-1]['evidence']['observations']['assessment']['items'][0]
    assert obs['sample_time_codes']==[0,1,2] and obs['samples_checked']==3
    assert next(x for x in r['coverage']['audit']['domains'] if x['domain']=='motion_requirements')['status']=='NOT_SELECTED'


def test_motion_budget_and_missing_clock_are_unknown(tmp_path):
    root,s=make_stage(tmp_path);x=UsdGeom.Xform.Define(s,'/World/Moving');op=x.AddTranslateOp();op.Set((0,0,0),0);op.Set((1,0,0),2);s.GetRootLayer().Save()
    r=run(root,['audit.authored_motion']);assert r['verdict']=='INSUFFICIENT_EVIDENCE'
    s.SetStartTimeCode(0);s.SetEndTimeCode(2);s.SetTimeCodesPerSecond(1);s.GetRootLayer().Save()
    c,_=baseline_contract(root,'scene.usda');c['checks']=[c['checks'][-1]];c['packs']={'scene.audit':c['packs']['scene.audit']};c['checks'][0]['parameters']['max_total_samples']=1
    r=evaluate_packs(None,'scene.usda',bundle_root=root,contract_data=c)
    assert r['verdict']=='INSUFFICIENT_EVIDENCE'
    assert row(r,'audit.authored_motion')['counts']['assessed_count']==0


def test_discovered_textures_are_unique_and_unsupported_visible(tmp_path):
    from PIL import Image
    root,s=make_stage(tmp_path)
    for name,file in [('A','good.png'),('B','good.png'),('C','bad.jpg'),('D','sky.hdr')]:
        sh=UsdShade.Shader.Define(s,'/World/'+name);sh.CreateIdAttr('UsdUVTexture');sh.CreateInput('file',Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(file))
    Image.new('RGB',(2,2)).save(root/'good.png');(root/'bad.jpg').write_bytes(b'broken');(root/'sky.hdr').write_bytes(b'unsupported')
    s.GetRootLayer().Save();r=run(root,['audit.textures'])
    c=row(r,'audit.textures')['counts']
    assert c['candidate_count']==3 and c['pass_count']==c['fail_count']==c['unknown_count']==1
    assert r['verdict']=='REJECT'


def test_profile_discovery_refusal_is_not_zero_inventory(tmp_path):
    from scene_acceptance.cli import main
    root,s=make_stage(tmp_path);s.GetRootLayer().Save()
    (root/'scene.usda').write_text((root/'scene.usda').read_text().replace('defaultPrim = "World"','defaultPrim = "World"\n    subLayers = [@child.usda@]'))
    (root/'child.usda').write_text('#usda 1.0\n')
    out=tmp_path/'blocked'
    assert main(['--profile','usd-delivery-baseline','--candidate','scene.usda','--bundle-root',str(root),'--max-dependency-files','1','--out',str(out)])==3
    r=json.loads((out/'result.json').read_text())
    assert r['coverage']['inventory'] is None
    assert all(x['status']=='UNKNOWN' for x in r['checks'])
    assert all(x['counts'] is None for x in r['coverage']['audit']['rows'])


def test_html_and_csv_escape_untrusted_provider_text(tmp_path):
    root,s=make_stage(tmp_path);s.GetRootLayer().Save();r=run(root,['audit.files'])
    r['intended_use']='<script>alert(1)</script>'
    r['coverage']['audit']['rows'][0]['reason']='=HYPERLINK("bad")'
    dest=tmp_path/'report';write_report(r,dest)
    assert '<script>alert(1)</script>' not in (dest/'report.html').read_text()
    assert "'=HYPERLINK" in (dest/'checks.csv').read_text()


def test_unknown_denominator_is_not_inferred_from_no_issues(tmp_path):
    root,s=make_stage(tmp_path);s.GetRootLayer().Save();r=run(root,['usd.00'])
    assert row(r,'usd.00')['unit']=='stage-validator invocations'
    assert row(r,'usd.00')['counts']['pass_count']==1
    # An uninstrumented custom provider remains explicitly unmeasured.
    r['coverage']['planned'][0]['pack']='custom'
    from scene_acceptance.coverage import enrich
    enrich(r,r['coverage']['inventory'])
    assert row(r,'usd.00')['counts'] is None


def test_batch_failed_process_cannot_present_a_pass(tmp_path):
    from scene_acceptance.batch import write_index
    root,s=make_stage(tmp_path);s.GetRootLayer().Save();r=run(root,['audit.files'])
    out=tmp_path/'batch';out.mkdir();write_report(r,out/'completed-before-crash')
    (out/'partial').mkdir();(out/'partial/result.json').write_text('{')
    records=[{'id':'completed-before-crash','exit_code':4},{'id':'partial','exit_code':None,'error':'Deadline'}]
    write_index(out,records)
    assert all(r['verdict']=='EVALUATION_ERROR' for r in records)
    assert 'href="partial/report.html"' not in (out/'report.html').read_text()


def test_old_article_approval_names_use_bundled_implementation():
    registry=default_registry(('textures.decode','motion.connection','physics.incline-worker'))
    assert 'scene_acceptance/followups' in registry.get('textures.decode').source_files[0]


def test_article_report_shows_measured_gap_not_just_verdict(tmp_path):
    from scene_acceptance import evaluate
    root=Path(__file__).resolve().parents[1]/'evaluation/article-checks-v1/fixtures/motion-wrapped'
    r=evaluate('contract.json','scene.usda',bundle_root=root)
    out=tmp_path/'connection';write_report(r,out)
    text=(out/'report.html').read_text()
    assert 'Maximum sampled gap: 69.8668 mm' in text
    assert 'allowed:' in text and 'worst sample:' in text
