"""Preset exclusions are disclosed; explicit unsupported requirements still block."""
from copy import deepcopy
import json
import pytest

from pxr import Usd, UsdGeom

from scene_acceptance.evaluation import evaluate_scene
from scene_acceptance.preparation import prepare_scene
from scene_acceptance.review_context import GENERAL_RUBRIC, applicable_rubric, judge_coverage_drift
from test_evaluation_modes import bundle, config, views


def test_static_textured_default_can_accept_without_inventing_physics_coverage(tmp_path, bundle):
    result = evaluate_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'run',
                            mode='both', judge_config=config(tmp_path), views=views(tmp_path,bundle,textured=True))
    assert result['decision'] == 'ACCEPT_FOR_USE'
    assert result['judge']['counts'] == {'consistent': 3}
    assert {r['area'] for r in result['judge']['unassessed_areas']} == {'physics', 'motion'}
    assert {r['id'] for r in result['judge']['requirements']} == {'review.layout', 'review.readability', 'review.material-use'}
    html = (tmp_path/'run/report.html').read_text()
    assert 'These areas were not assessed and are not passes' in html


def test_authored_animation_selects_motion_even_without_supplied_frames(tmp_path, bundle):
    stage = Usd.Stage.Open(str(bundle/'scene.usda'))
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(24)
    stage.SetTimeCodesPerSecond(24)
    op = UsdGeom.XformOp(stage.GetPrimAtPath('/World').GetAttribute('xformOp:translate'))
    op.Set((0,0,0), 0)
    op.Set((1,0,0), 24)
    stage.GetRootLayer().Save()
    result = evaluate_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'run',
                            mode='both', judge_config=config(tmp_path), views=views(tmp_path,bundle,textured=True))
    assert result['decision'] == 'NEEDS_REVIEW'
    motion = next(r for r in result['judge']['findings'] if r['requirement_id'] == 'review.motion')
    assert motion['assessment'] == 'unknown'
    assert {r['area'] for r in result['judge']['unassessed_areas']} == {'physics'}


def test_custom_physics_criterion_is_not_removed(tmp_path, bundle):
    rubric = deepcopy(GENERAL_RUBRIC)
    rubric['criteria'] = [r for r in rubric['criteria'] if r['id'] == 'physics']
    path = tmp_path/'rubric.json'
    path.write_text(json.dumps(rubric))
    result = evaluate_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'run',
                            mode='both', judge_config=config(tmp_path), rubric=path)
    assert result['decision'] == 'NEEDS_REVIEW'
    assert result['judge']['counts'] == {'unknown': 1}
    assert result['judge']['findings'][0]['requirement_id'] == 'review.physics'


def test_brief_required_physics_stays_unknown_under_automatic_rubric(tmp_path, bundle):
    path = bundle/'briefs/size.json'
    brief = json.loads(path.read_text())
    requirement = deepcopy(brief['requirements'][0])
    requirement.update(id='physical-use', statement='Verify physical behavior for the task', check_ids=[],
                       areas=['physics'], required=True, review_required=True, evaluation_route='visual')
    brief['requirements'].append(requirement)
    path.write_text(json.dumps(brief))
    result = evaluate_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'run',
                            mode='both', brief='briefs/size.json', judge_config=config(tmp_path),
                            views=views(tmp_path,bundle,textured=True))
    assert result['decision'] == 'NEEDS_REVIEW'
    physics = next(r for r in result['judge']['findings'] if r['requirement_id'] == 'brief.physical-use')
    assert physics['assessment'] == 'unknown'
    assert 'physics' not in {r['area'] for r in result['judge']['unassessed_areas']}


def test_default_selection_uses_inventory_and_preserves_prepared_scope(tmp_path, bundle):
    bare = applicable_rubric({'materials': 0, 'shaders': 0, 'time_sampled_attributes': 0})
    assert [r['id'] for r in bare['criteria']] == ['layout', 'readability']
    assert {r['area'] for r in bare['unassessed_areas']} == {'materials', 'motion', 'physics'}
    plan = prepare_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'prepared')
    rubric = json.loads((tmp_path/'prepared/rubric.json').read_text())
    scope = json.loads((tmp_path/'prepared/scope.json').read_text())
    assert rubric['version'] == '2.0.0'
    assert [r['id'] for r in rubric['criteria']] == ['layout', 'readability', 'material-use']
    assert scope['rubric'] == rubric
    assert scope['scope_sha256'] == plan['scope_sha256']


def test_named_profiles_disclose_their_excluded_areas(tmp_path, bundle):
    for profile, expected in [('static-visual', {'physics', 'motion'}),
                              ('animated-visual', {'physics'})]:
        prepare_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/profile,
                      review_profile=profile)
        rubric = json.loads((tmp_path/profile/'rubric.json').read_text())
        assert rubric['version'] == '1.1.0'
        assert {row['area'] for row in rubric['unassessed_areas']} == expected
        scope = json.loads((tmp_path/profile/'scope.json').read_text())
        assert scope['rubric']['unassessed_areas'] == rubric['unassessed_areas']


def test_rebound_candidate_does_not_reselect_frozen_review_scope(tmp_path, bundle):
    from scene_acceptance.scope import bind_preparation
    from scene_acceptance.review_context import context_for
    prepared = prepare_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'original')
    original_rubric = json.loads((tmp_path/'original/rubric.json').read_text())
    stage = Usd.Stage.Open(str(bundle/'scene.usda'))
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(24)
    stage.SetTimeCodesPerSecond(24)
    op = UsdGeom.XformOp(stage.GetPrimAtPath('/World').GetAttribute('xformOp:translate'))
    op.Set((0,0,0), 0)
    op.Set((1,0,0), 24)
    stage.GetRootLayer().Save()
    rebound = bind_preparation(preparation=tmp_path/'original', bundle_root=bundle, candidate='scene.usda',
                               out=tmp_path/'rebound', expected_scope_sha256=prepared['scope_sha256'])
    assert rebound['scope_sha256'] == prepared['scope_sha256']
    drift = rebound['binding']['judge_coverage_drift']
    assert drift['status'] == 'needs_review'
    assert drift['missing_requirement_ids'] == ['review.motion']
    assert drift['newly_applicable_areas'] == ['motion']
    assert 'Judge coverage after repair' in (tmp_path/'rebound/report.html').read_text()
    assert json.loads((tmp_path/'rebound/rubric.json').read_text()) == original_rubric
    context = context_for(bundle, 'scene.usda', tmp_path/'context', rubric=tmp_path/'rebound/rubric.json')
    assert context['scene']['inventory']['time_sampled_attributes'] > 0
    assert 'review.motion' not in {r['id'] for r in context['requirements']}
    reason = next(r['reason'] for r in context['unassessed_areas'] if r['area'] == 'motion')
    assert 'when this scope was selected' in reason and 'retained on rebind' in reason


def _animate(bundle):
    stage = Usd.Stage.Open(str(bundle/'scene.usda'))
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(24)
    stage.SetTimeCodesPerSecond(24)
    attr = stage.GetPrimAtPath('/World').GetAttribute('xformOp:translate')
    attr.Set((0, 0, 0), 0)
    attr.Set((1, 0, 0), 24)
    stage.GetRootLayer().Save()


def _overview_evidence(tmp_path, preparation, plan):
    """Supply all original static captures to isolate the changed-scope gate."""
    from PIL import Image
    from scene_acceptance.model import sha
    folder = tmp_path/'captures'
    folder.mkdir()
    image = folder/'overview.png'
    Image.new('RGB', (640, 480), 'white').save(image)
    manifest = dict(schema_version='1.0', scene_sha256=plan['scene_sha256'], up_axis='Z', meters_per_unit=1,
        views=[dict(id='overview', path='overview.png', sha256=sha(image), view_roles=['overview'],
                    camera_id='front', camera='Synthetic front view', projection='orthographic', time_seconds=0,
                    method='Synthetic control', producer='pytest', capabilities=['geometry', 'surface_materials'],
                    limitations=['Transport control, not a real render'], covered_prims=[])])
    captures = json.loads((preparation/'capture-plan.json').read_text())['requests']
    receipt = dict(schema_version='1.0', plan_sha256=plan['plan_sha256'], scene_sha256=plan['scene_sha256'],
        requests=[dict(request_id=c['id'], status='supplied', view_ids=['overview'], reason='Control') for c in captures])
    (folder/'views.json').write_text(json.dumps(manifest))
    (folder/'receipt.json').write_text(json.dumps(receipt))
    return dict(views=folder/'views.json', receipt=folder/'receipt.json')


@pytest.mark.parametrize('feature,requirement', [('motion', 'review.motion'), ('materials', 'review.material-use')])
def test_new_applicable_feature_is_not_silently_accepted_by_frozen_judge(tmp_path, bundle, feature, requirement):
    from scene_acceptance.scope import approve_scope, bind_preparation
    from scene_acceptance.prepared_run import evaluate_prepared
    saved_scene = (bundle/'scene.usda').read_bytes()
    if feature == 'materials':
        stage = Usd.Stage.Open(str(bundle/'scene.usda'))
        stage.RemovePrim('/World/Looks')
        stage.GetRootLayer().Save()
        del stage
    capabilities = tmp_path/'capabilities.json'
    capabilities.write_text(json.dumps(dict(schema_version='1.0', capabilities=['geometry', 'surface_materials'],
        max_images=12, max_width=640, max_height=480, limitations=['Test fixture only'])))
    prepared = prepare_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'original',
                              capture_capabilities=capabilities)
    approval = tmp_path/'approval.json'
    approve_scope(preparation=tmp_path/'original', out=approval, expected_scope_sha256=prepared['scope_sha256'],
                  reviewer='Test caller', reason='Original scope reviewed')
    if feature == 'motion':
        _animate(bundle)
    else:
        (bundle/'scene.usda').write_bytes(saved_scene)
    rebound = bind_preparation(preparation=tmp_path/'original', bundle_root=bundle, candidate='scene.usda',
                               out=tmp_path/'rebound', expected_scope_sha256=prepared['scope_sha256'])
    assert rebound['scope_sha256'] == prepared['scope_sha256']
    assert rebound['binding']['judge_coverage_drift']['missing_requirement_ids'] == [requirement]
    assert not rebound['readiness']['ready_for_capture']
    assert rebound['exit_code'] == 3 and rebound['next_action'] == 'revise_preparation'
    assert any(b['kind'] == 'judge_scope' and b['id'] == requirement for b in rebound['readiness']['blockers'])
    evidence = _overview_evidence(tmp_path, tmp_path/'rebound', rebound)
    result = evaluate_prepared(preparation=tmp_path/'rebound', out=tmp_path/'run', mode='both',
                               judge_config=config(tmp_path), approval=approval, **evidence)
    assert result['script_verdict'] == 'ACCEPT_FOR_USE'
    assert result['judge_counts'] == {'consistent': 3 if feature == 'motion' else 2}
    assert result['capture_counts'] == {'supplied': 3 if feature == 'motion' else 2}
    assert result['decision'] == 'NEEDS_REVIEW' and result['exit_code'] == 3
    assert result['judge_coverage_drift']['missing_requirement_ids'] == [requirement]
    finding = next(f for f in result['findings'] if f['id'] == 'scope.judge-coverage-drift')
    assert finding['next_action'] == 'review_specification'
    fresh = prepare_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'fresh')
    assert fresh['scope_sha256'] != prepared['scope_sha256']
    fresh_captures = json.loads((tmp_path/'fresh/capture-plan.json').read_text())['requests']
    assert requirement in {rid for capture in fresh_captures for rid in capture['requirement_ids']}


def test_drift_survives_multiple_rebinds_but_clears_if_feature_removed(tmp_path, bundle):
    from scene_acceptance.scope import bind_preparation
    from scene_acceptance.prepared_run import evaluate_prepared
    original_scene = (bundle/'scene.usda').read_bytes()
    prepared = prepare_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'original')
    _animate(bundle)
    first = bind_preparation(preparation=tmp_path/'original', bundle_root=bundle, candidate='scene.usda',
                             out=tmp_path/'first', expected_scope_sha256=prepared['scope_sha256'])
    second = bind_preparation(preparation=tmp_path/'first', bundle_root=bundle, candidate='scene.usda',
                              out=tmp_path/'second', expected_scope_sha256=prepared['scope_sha256'])
    assert second['binding']['judge_coverage_drift'] == first['binding']['judge_coverage_drift']
    assert not second['binding']['judge_coverage_drift']['prepared_applicability']['motion']
    checks = evaluate_prepared(preparation=tmp_path/'second', out=tmp_path/'checks', mode='checks')
    assert checks['exit_code'] == 0
    assert checks['judge_coverage_drift']['status'] == 'needs_review'
    assert any(f['id'] == 'scope.judge-coverage-drift' for f in checks['findings'])
    assert 'Checks-only' in (tmp_path/'checks/report.html').read_text()
    (bundle/'scene.usda').write_bytes(original_scene)
    removed = bind_preparation(preparation=tmp_path/'second', bundle_root=bundle, candidate='scene.usda',
                               out=tmp_path/'removed', expected_scope_sha256=prepared['scope_sha256'])
    assert removed['binding']['judge_coverage_drift']['status'] == 'unchanged'
    assert removed['binding']['judge_coverage_drift']['missing_requirement_ids'] == []


def test_custom_existing_motion_question_does_not_need_default_id():
    rubric = deepcopy(GENERAL_RUBRIC)
    rubric['criteria'] = [dict(r, id='custom-motion') for r in rubric['criteria'] if r['id'] == 'motion']
    drift = judge_coverage_drift({'time_sampled_attributes': 0}, {'time_sampled_attributes': 1}, rubric)
    assert drift['newly_applicable_areas'] == ['motion']
    assert drift['status'] == 'unchanged'
    assert drift['missing_requirement_ids'] == []


def test_original_deliberate_custom_exclusion_is_not_new_drift():
    rubric = deepcopy(GENERAL_RUBRIC)
    rubric['criteria'] = []
    inventory = {'time_sampled_attributes': 1, 'materials': 1}
    drift = judge_coverage_drift(inventory, inventory, rubric)
    assert drift['status'] == 'unchanged'
    assert not drift['newly_applicable_areas']
