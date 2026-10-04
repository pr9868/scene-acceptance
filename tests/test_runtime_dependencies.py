"""Caller MDL receipts narrow an explicit gap without granting visual/physics proof."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
from jsonschema import ValidationError

from scene_acceptance.application import invoke, main
from scene_acceptance.model import ContractError, sha
from scene_acceptance.pack_engine import Context
from scene_acceptance.preparation import prepare_scene
from scene_acceptance.profiles import discover_artifact
from scene_acceptance.runtime_dependencies import RuntimeDependencies
from scene_acceptance.scene_audit import files
from scene_acceptance.scope import approve_scope, bind_preparation, load_scope
from test_mdl_support import mdl_scene, dependency_check, surface_check

ENVIRONMENT = 'a' * 64


def receipt_for(root, path):
    artifact = discover_artifact(root, 'scene.usda')
    now = datetime.now(timezone.utc)
    data = dict(schema_version='1.0', kind='renderer-mdl-dependency-attestation',
                scene_sha256=artifact.artifact_set_sha256, environment_sha256=ENVIRONMENT,
                renderer=dict(name='Synthetic renderer', version='1.2'),
                runtime=dict(name='Synthetic runtime', version='3.4'),
                provenance=dict(attested_by='Fixture caller', source='Synthetic resolver observation, no renderer executed',
                                observed_at_utc=(now-timedelta(minutes=1)).isoformat(),
                                expires_at_utc=(now+timedelta(hours=1)).isoformat()),
                dependencies=[dict(ref, resolved_identifier='synthetic://runtime/'+ref['identifier'],
                                   library_sha256='b'*64)
                              for target, refs in artifact.runtime_assets.items()
                              if artifact.assets[target] is None for ref in refs])
    path.write_text(json.dumps(data))
    return artifact, data


@pytest.fixture
def scene(tmp_path):
    root=tmp_path/'scene';root.mkdir();mdl_scene(root)
    receipt=tmp_path/'runtime.json';artifact,data=receipt_for(root,receipt)
    return root,receipt,artifact,data


def runtime(artifact, receipt):
    return RuntimeDependencies(artifact, policy='caller-attested', environment_sha256=ENVIRONMENT, evidence=receipt)


def context(artifact, receipt):
    return Context(artifact.bundle,artifact,None,(),runtime(artifact,receipt))


def options(root, receipt):
    return dict(bundle_root=root,candidate='scene.usda',runtime_dependency_policy='caller-attested',
                runtime_environment_sha256=ENVIRONMENT,runtime_dependency_evidence=receipt)


def test_receipt_accepts_only_availability_and_preserves_upstream_error(scene):
    root,receipt,artifact,data=scene;ctx=context(artifact,receipt)
    r=dependency_check(ctx)
    assert r.status == files(ctx,{}).status == surface_check(ctx).status == 'PASS'
    issue=r.evidence['issues'][0]
    assert issue['severity']=='Error' and issue['assessment']=='PASS'
    assert 'unresolvable external dependency' in issue['message']
    assert issue['runtime_dependency_evidence'][0]['receipt_sha256']==sha(receipt)
    row=surface_check(ctx).evidence['findings'][-1]
    assert row['observed'] is False and row['sha256'] is None
    assert row['runtime_dependency_evidence']['basis']=='caller_attestation'
    assert files(ctx,{'runtime_libraries':'require_local'}).status=='FAIL'
    assert not (root/'OmniPBR.mdl').exists()


@pytest.mark.parametrize('fault', ['scene','environment','identifier','attribute','layer','duplicate','missing-version',
                                  'expired','future','naive-time','empty','bad-hash','extra','oversize'])
def test_malformed_mismatched_and_stale_receipts_fail_closed(scene,fault):
    _,receipt,artifact,data=scene
    if fault=='scene':data['scene_sha256']='c'*64
    elif fault=='environment':data['environment_sha256']='c'*64
    elif fault in ('identifier','attribute','layer'):data['dependencies'][0][fault]='unrelated'
    elif fault=='duplicate':data['dependencies'].append(deepcopy(data['dependencies'][0]))
    elif fault=='missing-version':data['renderer'].pop('version')
    elif fault=='expired':data['provenance']['expires_at_utc']='2000-01-01T00:00:00Z'
    elif fault=='future':data['provenance']['observed_at_utc']='2999-01-01T00:00:00Z'
    elif fault=='naive-time':data['provenance']['observed_at_utc']='2000-01-01T00:00:00'
    elif fault=='empty':data['dependencies']=[]
    elif fault=='bad-hash':data['dependencies'][0]['library_sha256']='truthy'
    elif fault=='extra':data['trust_everything']=True
    elif fault=='oversize':data['provenance']['source']='x'*262144
    receipt.write_text(json.dumps(data))
    with pytest.raises((ValueError, ValidationError)):
        runtime(artifact,receipt)


def test_receipt_requires_both_opt_in_and_independent_environment_pin(scene):
    _,receipt,artifact,_=scene
    with pytest.raises(ContractError,match='explicit caller-attested'):
        RuntimeDependencies(artifact,evidence=receipt)
    with pytest.raises(ContractError,match='pinned runtime environment'):
        RuntimeDependencies(artifact,policy='caller-attested',evidence=receipt)
    missing=RuntimeDependencies(artifact,policy='caller-attested',environment_sha256=ENVIRONMENT)
    ctx=Context(artifact.bundle,artifact,None,(),missing)
    assert files(ctx,{}).status==dependency_check(ctx).status=='UNKNOWN'
    with pytest.raises(ContractError,match='regular file'):runtime(artifact,receipt.with_name('missing.json'))


def test_other_errors_and_missing_texture_are_never_suppressed(tmp_path):
    root=tmp_path/'scene';root.mkdir();mdl_scene(root,texture=True)
    receipt=tmp_path/'runtime.json';artifact,_=receipt_for(root,receipt)
    ctx=context(artifact,receipt)
    assert files(ctx,{}).status==dependency_check(ctx).status==surface_check(ctx).status=='FAIL'
    issues=dependency_check(ctx).evidence['issues']
    assert any(i.get('assessment')=='PASS' for i in issues)
    assert any(i['severity']=='Error' and not i.get('assessment') for i in issues)
    assert surface_check(ctx,'WrongSubidentifier').status=='FAIL'


def test_same_asset_used_as_texture_cannot_be_attested(scene):
    root,receipt,_,data=scene
    from pxr import Sdf,Usd,UsdShade
    stage=Usd.Stage.Open(str(root/'scene.usda'))
    shader=UsdShade.Shader(stage.GetPrimAtPath('/World/Material/Shader'))
    shader.CreateInput('diffuse_texture',Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath('OmniPBR.mdl'))
    stage.GetRootLayer().Save()
    artifact=discover_artifact(root,'scene.usda');data['scene_sha256']=artifact.artifact_set_sha256
    receipt.write_text(json.dumps(data))
    with pytest.raises(ContractError,match='matching unresolved authored MDL'):
        runtime(artifact,receipt)


@pytest.mark.parametrize('same_library',[False,True])
def test_partial_receipt_cannot_clear_uncovered_references(scene,same_library):
    root,receipt,_,_=scene
    from pxr import Sdf,Usd,UsdShade
    stage=Usd.Stage.Open(str(root/'scene.usda'))
    shader=UsdShade.Shader.Define(stage,'/World/SecondShader')
    shader.SetSourceAsset(Sdf.AssetPath('OmniPBR.mdl' if same_library else 'Second.mdl'),'mdl')
    shader.SetSourceAssetSubIdentifier('OmniPBR','mdl')
    stage.GetRootLayer().Save()
    artifact,data=receipt_for(root,receipt)
    assert len(data['dependencies'])==2
    data['dependencies']=data['dependencies'][:1];receipt.write_text(json.dumps(data))
    ctx=context(artifact,receipt)
    assert files(ctx,{}).status==dependency_check(ctx).status=='UNKNOWN'
    assert ctx.runtime_dependencies.report()['accepted_dependency_count']==(0 if same_library else 1)


def test_conflicting_library_identities_are_rejected(scene):
    root,receipt,_,_=scene
    from pxr import Sdf,Usd,UsdShade
    stage=Usd.Stage.Open(str(root/'scene.usda'))
    shader=UsdShade.Shader.Define(stage,'/World/SecondShader')
    shader.SetSourceAsset(Sdf.AssetPath('OmniPBR.mdl'),'mdl')
    shader.SetSourceAssetSubIdentifier('OmniPBR','mdl');stage.GetRootLayer().Save()
    artifact,data=receipt_for(root,receipt)
    data['dependencies'][1]['library_sha256']='c'*64;receipt.write_text(json.dumps(data))
    with pytest.raises(ContractError,match='Conflicting runtime identities'):runtime(artifact,receipt)


def test_tampering_after_admission_errors_instead_of_passing(scene):
    _,receipt,artifact,data=scene;ctx=context(artifact,receipt)
    data['provenance']['attested_by']='Changed caller';receipt.write_text(json.dumps(data))
    with pytest.raises(ContractError,match='changed during evaluation'):files(ctx,{})


def test_direct_application_records_receipt_and_explicit_policy(scene,tmp_path):
    root,receipt,_,data=scene
    unknown=invoke('check',bundle_root=root,candidate='scene.usda',out=tmp_path/'unknown')
    assert unknown['exit_code']==3
    accepted=invoke('check',**options(root,receipt),out=tmp_path/'accepted')
    assert accepted['exit_code']==0,accepted
    saved=accepted['data']['runtime_dependencies']
    assert saved['accepted_dependency_count']==1 and saved['receipt']==data
    assert 'caller attestation' in (tmp_path/'accepted/report.html').read_text()


def test_cli_direct_and_prepared_retain_evidence(scene,tmp_path,capsys):
    root,receipt,_,_=scene
    assert main(['check','--bundle-root',str(root),'--candidate','scene.usda','--out',str(tmp_path/'cli'),
                 '--runtime-dependency-policy','caller-attested','--runtime-environment-sha256',ENVIRONMENT,
                 '--runtime-dependency-evidence',str(receipt)])==0
    assert json.loads(capsys.readouterr().out)['data']['runtime_dependencies']['supplied']
    assert main(['prepare','--bundle-root',str(root),'--candidate','scene.usda','--out',str(tmp_path/'prepared'),
                 '--runtime-dependency-policy','caller-attested','--runtime-environment-sha256',ENVIRONMENT])==0
    plan=json.loads(capsys.readouterr().out)['data']
    assert main(['evaluate','--preparation',str(tmp_path/'prepared'),'--out',str(tmp_path/'pending'),
                 '--runtime-dependency-evidence',str(receipt)])==3
    pending=json.loads(capsys.readouterr().out)['data'];assert pending['next_action']=='review_specification'
    approved=tmp_path/'approval.json'
    approve_scope(preparation=tmp_path/'prepared',out=approved,expected_scope_sha256=plan['scope_sha256'],
                  reviewer='Fixture reviewer',reason='Accept caller attestation in this named runtime')
    assert main(['evaluate','--preparation',str(tmp_path/'prepared'),'--out',str(tmp_path/'approved'),
                 '--approval',str(approved),'--runtime-dependency-evidence',str(receipt)])==0
    capsys.readouterr()


def test_prepared_policy_and_runtime_changes_require_new_approval(scene,tmp_path):
    root,receipt,_,_=scene
    default=prepare_scene(bundle_root=root,candidate='scene.usda',out=tmp_path/'default')
    selected=prepare_scene(bundle_root=root,candidate='scene.usda',out=tmp_path/'selected',
                           runtime_dependency_policy='caller-attested',runtime_environment_sha256=ENVIRONMENT)
    other=prepare_scene(bundle_root=root,candidate='scene.usda',out=tmp_path/'other',
                        runtime_dependency_policy='caller-attested',runtime_environment_sha256='c'*64)
    assert len({p['scope_sha256'] for p in (default,selected,other)})==3
    result=invoke('evaluate',preparation=tmp_path/'default',out=tmp_path/'disallowed',runtime_dependency_evidence=receipt)
    assert result['exit_code']==4
    approved=tmp_path/'approval.json'
    approve_scope(preparation=tmp_path/'selected',out=approved,expected_scope_sha256=selected['scope_sha256'],
                  reviewer='Caller',reason='Approve bounded renderer context')
    mismatch=invoke('evaluate',preparation=tmp_path/'other',out=tmp_path/'mismatch',approval=approved,
                    runtime_dependency_evidence=receipt)
    assert mismatch['exit_code']==4


def test_rebind_preserves_target_runtime_but_needs_receipt_for_new_scene(scene,tmp_path):
    root,receipt,_,_=scene
    plan=prepare_scene(bundle_root=root,candidate='scene.usda',out=tmp_path/'prepared',
                       runtime_dependency_policy='caller-attested',runtime_environment_sha256=ENVIRONMENT)
    approval=tmp_path/'approval.json'
    approve_scope(preparation=tmp_path/'prepared',out=approval,expected_scope_sha256=plan['scope_sha256'],
                  reviewer='Caller',reason='Accept known runtime dependency receipt')
    from pxr import Usd,UsdGeom
    stage=Usd.Stage.Open(str(root/'scene.usda'))
    UsdGeom.Cube(stage.GetPrimAtPath('/World/Cube')).CreateSizeAttr(3)
    stage.GetRootLayer().Save()
    rebound=bind_preparation(preparation=tmp_path/'prepared',bundle_root=root,candidate='scene.usda',
                             out=tmp_path/'bound',expected_scope_sha256=plan['scope_sha256'])
    assert rebound['scope_sha256']==plan['scope_sha256']
    scope=load_scope(tmp_path/'bound',rebound)
    assert scope['evaluation_policy']['runtime_dependencies']['environment_sha256']==ENVIRONMENT
    stale=invoke('evaluate',preparation=tmp_path/'bound',out=tmp_path/'stale',approval=approval,
                 runtime_dependency_evidence=receipt)
    assert stale['exit_code']==4
    receipt_for(root,receipt)
    current=invoke('evaluate',preparation=tmp_path/'bound',out=tmp_path/'current',approval=approval,
                   runtime_dependency_evidence=receipt)
    assert current['exit_code']==0,current


def test_mapped_brief_and_runtime_evidence_reach_same_script_checks(scene,tmp_path):
    root,receipt,_,_=scene
    (root/'brief.txt').write_text('Deliver a Z-up scene for this example.\n')
    brief=dict(schema_version='1.0',id='mdl-brief',title='MDL example',intended_use='Synthetic delivery control',
        provenance='Synthetic test brief',files=[dict(path='brief.txt',role='text',caption='Caller brief')],
        mapping_review=dict(status='reviewed',reviewer='Fixture caller',reason='Reviewed explicit mapping'),
        checks=[],requirements=[dict(id='brief.units',layer='explicit',statement='Deliver authored stage metadata',
            basis='Caller brief',required=True,check_ids=['usd.0'],review_required=False,decision_id=None,
            inference_authorization=None)])
    # Select a baseline rule by its actual shipped identifier; no private test-pack pins.
    from scene_acceptance.profiles import baseline_contract
    contract,_=baseline_contract(root,'scene.usda')
    brief['requirements'][0]['check_ids']=[contract['checks'][0]['id']]
    (root/'brief.json').write_text(json.dumps(brief))
    result=invoke('check',**options(root,receipt),brief='brief.json',out=tmp_path/'mapped')
    assert result['exit_code']==0,result
    assert result['data']['script']['declared_scope_verdict']=='ACCEPT_FOR_DECLARED_SCOPE'
    assert result['data']['runtime_dependencies']['accepted_dependency_count']==1


def test_prepared_mapped_brief_receipt_survives_approval_and_input_snapshots(scene,tmp_path):
    from test_preparation import setup
    root,receipt,_,_=scene
    kwargs=setup(tmp_path,root)
    (root/'raw.txt').write_text('At time code 0, the cube must be 2 by 2 by 2 metres with 0.001 metre tolerance.')
    adapter=tmp_path/'interpreter.py'
    text=adapter.read_text().replace('/World/Panel','/World/Cube').replace('size_m=[.30,.16,0]','size_m=[2,2,2]')
    text=text.replace("print(json.dumps(dict(request_sha256=", "items=items[:1]\nprint(json.dumps(dict(request_sha256=")
    adapter.write_text(text)
    plan=prepare_scene(**kwargs,runtime_dependency_policy='caller-attested',runtime_environment_sha256=ENVIRONMENT)
    approval=tmp_path/'approval.json'
    approve_scope(preparation=kwargs['out'],out=approval,expected_scope_sha256=plan['scope_sha256'],
                  reviewer='Fixture caller',reason='Reviewed cube size and runtime dependency trust')
    result=invoke('evaluate',preparation=kwargs['out'],out=tmp_path/'mapped-prepared',approval=approval,
                  runtime_dependency_evidence=receipt)
    assert result['exit_code']==0,result
    assert result['data']['scope_verdict']=='ACCEPT_FOR_DECLARED_SCOPE'
    saved=json.loads((tmp_path/'mapped-prepared/evaluation/evaluation.json').read_text())
    assert saved['runtime_dependencies']['accepted_dependency_count']==1


def test_receipt_changed_after_scripts_prevents_success(scene,tmp_path,monkeypatch):
    import scene_acceptance.evaluation as evaluation
    root,receipt,_,data=scene;original=evaluation.scripted
    def changing(*args,**kwargs):
        result=original(*args,**kwargs)
        data['provenance']['source']='Modified after scripts';receipt.write_text(json.dumps(data))
        return result
    monkeypatch.setattr(evaluation,'scripted',changing)
    result=invoke('check',**options(root,receipt),out=tmp_path/'tampered')
    assert result['exit_code']==4 and result['data']['source_unchanged'] is False
    assert any('changed during evaluation' in x for x in result['data']['errors'])


def test_replay_rejects_changed_receipt_and_expiration(scene,tmp_path):
    root,receipt,_,data=scene
    kwargs=options(root,receipt)|dict(out=tmp_path/'run',reuse_completed=True)
    assert invoke('check',**kwargs)['exit_code']==0
    assert invoke('check',**kwargs)['reused']
    data['provenance']['source']='New caller observation';receipt.write_text(json.dumps(data))
    changed=invoke('check',**kwargs);assert changed['exit_code']==4 and not changed['reused']
    data['provenance']['expires_at_utc']='2000-01-01T00:00:00Z';receipt.write_text(json.dumps(data))
    expired=invoke('check',**kwargs);assert expired['exit_code']==4 and 'stale' in expired['errors'][0]['message']
