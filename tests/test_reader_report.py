"""Reader-facing categories must retain provenance, warning and coverage boundaries."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import pytest
from pxr import UsdGeom
from scene_acceptance.reader_report import build_overview, render_overview
from scene_acceptance.report import write_report
from scene_acceptance.review import assess
from scene_acceptance.review.__main__ import write_report as write_review
from scene_acceptance.model import sha
from scene_acceptance.cli import main
from test_reporting import make_stage, mesh, run as baseline_run, pointer
from test_consolidation import prepare, run, review_plan, save


def test_generic_scene_inventory_and_matrix_do_not_invent_human_specs(tmp_path):
    b,s=make_stage(tmp_path);mesh(s,'/World/Good');mesh(s,'/World/Bad',3,True);s.GetRootLayer().Save()
    result=baseline_run(b); overview=build_overview(result)
    assert overview['human_specifications']==0
    assert overview['specifications']==[]
    assert overview['matrix'][0]['total']==27
    assert overview['matrix'][0]['warning']>0 and overview['matrix'][0]['fail']>0
    assert overview['matrix'][0]['not_applicable']>0
    assert sum(x['total'] for x in overview['matrix'])==27
    assert all(sum(x[k] for k in ('pass','warning','fail','unknown','error','not_applicable'))==x['total'] for x in overview['matrix'])
    assert overview['scene']['candidate']=='scene.usda'
    assert overview['scene']['root_sha256']==sha(b/'scene.usda')
    assert overview['scene']['inventory']['meshes']==2
    assert {x['path'] for x in overview['scene']['structure']['hierarchy']}=={'/World','/World/Good','/World/Bad'}
    assert not overview['scene']['structure']['clock_authored']


@pytest.mark.parametrize('origin,group',[('human','human'),('application','configured'),('agent','configured'),('preset','configured'),('unrecorded','unrecorded')])
def test_explicit_source_is_recorded_without_inference(tmp_path,origin,group):
    b,c=prepare(tmp_path,'original-panel-png')
    c['report_context']={'scene_name':'Named panel'}
    c['checks'][1]['specification_source']={'provided_by':origin,'reference':'Constructed reporting control; not actual user input'}
    save(b/'contract.json',c)
    r=run(b,'panel-png');assert r['verdict']=='ACCEPT_FOR_USE',r
    overview=build_overview(r)
    assert overview['scene']['name']=='Named panel'
    assert next(x for x in overview['checks'] if x['id']==c['checks'][1]['id'])['basis']==group
    assert overview['human_specifications']==int(origin=='human')
    for s in overview['specifications']: assert 'complete specification not mapped' in s['coverage']


def test_preset_and_unrecorded_targets_are_not_human(tmp_path):
    b,c=prepare(tmp_path,'original-panel-png');overview=build_overview(run(b,'panel-png'))
    assert overview['human_specifications']==0
    assert any(x['basis']=='configured' for x in overview['checks'])
    assert any(x['basis']=='unrecorded' for x in overview['checks'])
    assert all(a['human_input']=='No human source recorded' for a in overview['areas'])


def test_general_rule_explicitly_linked_to_unrecorded_spec_is_not_general_only():
    r={'checks':[{'id':'format','status':'PASS','required':True}],
       'coverage':{'planned':[{'id':'format','pack':'openusd','check':'validators','parameters':{},'required':True,
          'specification_source':{'provided_by':'unrecorded','reference':'Declared link without author provenance'}}]}}
    overview=build_overview(r)
    assert overview['matrix'][0]['total']==0 and overview['matrix'][3]['pass']==1


def test_passing_samples_do_not_establish_whole_specification(tmp_path):
    b,c=prepare(tmp_path,'original-motion');o,p=review_plan(tmp_path,b,c)
    item=p['items'][0]
    item.update(specification_source={'provided_by':'human','reference':'Synthetic declared-human control; not an actual user brief'},
                areas=['motion'],coverage_declaration={'extent':'full','reason':'Deliberately overbroad declaration to challenge reporting'})
    missing=deepcopy(item);missing.update(id='unmapped-appearance',statement='Required appearance comparison',check_ids=[],areas=['appearance'],review_required=False)
    p['items'].append(missing);save(o/'plan.json',p)
    r=assess('plan.json',review_root=o,bundle_root=b,expected_plan_sha256=sha(o/'plan.json'))
    assert r['core_verdict']=='ACCEPT_FOR_USE' and r['assessment_verdict']=='NEEDS_REVIEW'
    overview=build_overview(r['core_report'],r)
    motion=overview['specifications'][0];assert motion['status']=='UNKNOWN'
    assert motion['completed_count']==motion['mapped_count']==1
    assert motion['coverage']=='Partial automation; separate review required'
    assert overview['specifications'][1]['coverage']=='No automated coverage'
    assert overview['human_specifications']==2
    out=tmp_path/'report';write_review(r,out)
    assert (out/'report.html').read_text().count('Results at a glance')==1
    assert json.loads((out/'overview.json').read_text())==overview
    for row in csv.DictReader((out/'specifications.csv').open()):
        data=json.loads((out/row['evidence_file']).read_text());assert pointer(data,row['evidence_pointer']) is not None


def test_partial_mapping_and_unreviewed_extent_remain_distinct(tmp_path):
    b,c=prepare(tmp_path,'original-panel-png');r=run(b,'panel-png')
    base={'id':'s','statement':'Selected panel property','check_ids':['brief.panel.dimensions'],'required':True,
          'layer':'explicit','review_required':False,'status':'PASS','observations':[]}
    for extent,expected in [('partial','Partial mapping declared by caller'),('unreviewed','Mapped checks ran; coverage extent unreviewed')]:
        item=base | {'coverage_declaration':{'extent':extent,'reason':'Test scope'}}
        x=build_overview(r,{'items':[item]})['specifications'][0]
        assert x['coverage']==expected


def test_admission_failure_keeps_scene_identity_and_unknown_counts(tmp_path):
    b=tmp_path/'bundle';b.mkdir();out=tmp_path/'report'
    code=main(['--profile','usd-delivery-baseline','--candidate','missing.usda','--bundle-root',str(b),'--out',str(out)])
    assert code in (3,4)
    overview=json.loads((out/'overview.json').read_text())
    assert overview['scene']['candidate']=='missing.usda' and overview['scene']['inventory'] is None
    assert overview['matrix'][0]['unknown']==27
    assert overview['matrix'][0]['pass']==0


def test_legacy_and_unknown_providers_remain_unclassified():
    old={'checks':[{'id':'some-rule','status':'PASS','required':True}], 'coverage':{}}
    overview=build_overview(old)
    assert overview['matrix'][-1]['pass']==1 and overview['matrix'][0]['total']==0
    assert overview['scene']['inventory'] is None
    assert 'Unavailable' in render_overview(overview)


def test_unknown_and_error_mapping_do_not_count_as_assessed():
    r={'checks':[{'id':'probe','status':'ERROR','required':True}],
       'coverage':{'planned':[{'id':'probe','pack':'custom.pack','check':'probe','parameters':{},'required':True}]}}
    item={'id':'need','statement':'Need this evidence','layer':'explicit','required':True,'review_required':False,
          'check_ids':['probe'],'status':'ERROR','observations':[],
          'specification_source':{'provided_by':'human','reference':'Synthetic test'}}
    overview=build_overview(r,{'items':[item]})
    assert overview['matrix'][1]['error']==1 and overview['specifications'][0]['completed_count']==0
    assert overview['specifications'][0]['coverage']=='Automated evidence incomplete'


def test_untrusted_context_is_escaped_and_schema_is_closed(tmp_path):
    b,c=prepare(tmp_path,'original-panel-png');c['report_context']={'scene_name':'<script>bad()</script>'}
    c['checks'][1]['specification_source']={'provided_by':'human','reference':'=bad()'};save(b/'contract.json',c)
    r=run(b,'panel-png');out=tmp_path/'report';write_report(r,out)
    assert '<script>bad()</script>' not in (out/'report.html').read_text()
    assert '&lt;script&gt;' in (out/'report.html').read_text()
    assert "'=bad()" in (out/'specifications.csv').read_text()
    c['checks'][1]['specification_source']['provided_by']='verified-human'
    save(b/'contract.json',c);assert run(b,'panel-png')['verdict']=='EVALUATION_ERROR'
