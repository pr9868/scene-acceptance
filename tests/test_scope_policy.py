"""Approval binds evaluator requirements as well as a human brief."""
from copy import deepcopy
import json

import pytest

from scene_acceptance.model import ContractError
from scene_acceptance.preparation import prepare_scene, load_preparation
from scene_acceptance.prepared_run import evaluate_prepared
from scene_acceptance.scope import approve_scope, bind_preparation, evaluation_policy
from test_evaluation_modes import bundle


@pytest.mark.parametrize('change', ['removed_check', 'required_flag', 'pack_version', 'pack_code'])
def test_policy_migration_invalidates_approval_and_requires_new_review(tmp_path, bundle, monkeypatch, change):
    original = tmp_path / 'original'
    prepared = prepare_scene(bundle_root=bundle, candidate='scene.usda', out=original)
    approval = tmp_path / 'old-approval.json'
    approve_scope(preparation=original, out=approval,
                  expected_scope_sha256=prepared['scope_sha256'], reviewer='Caller', reason='Reviewed policy')
    policy = deepcopy(evaluation_policy())
    if change == 'removed_check':
        policy['baseline']['checks'].pop()
    elif change == 'required_flag':
        policy['baseline']['checks'][0]['required'] = False
    elif change == 'pack_version':
        policy['packs']['openusd']['version'] = '99.0.0'
    else:
        policy['packs']['openusd']['implementation_sha256'] = '0' * 64
    monkeypatch.setattr('scene_acceptance.scope.evaluation_policy', lambda brief=None: deepcopy(policy))

    with pytest.raises(ContractError, match='Evaluation policy changed'):
        load_preparation(original)
    with pytest.raises(ContractError, match='Evaluation policy changed'):
        bind_preparation(preparation=original, bundle_root=bundle, candidate='scene.usda',
                         out=tmp_path/'ordinary', expected_scope_sha256=prepared['scope_sha256'])
    rebound = tmp_path / 'migrated'
    migrated = bind_preparation(preparation=original, bundle_root=bundle, candidate='scene.usda',
                               out=rebound, expected_scope_sha256=prepared['scope_sha256'],
                               migrate_runtime=True, reviewer='Caller', reason='Review upgraded evaluator')
    assert migrated['scope_sha256'] != prepared['scope_sha256']
    assert migrated['binding']['evaluation_policy_changed']
    assert not migrated['binding']['scope_unchanged']
    assert migrated['binding']['requires_scope_approval']
    assert migrated['binding']['policy_changes']['previous_sha256'] != migrated['binding']['policy_changes']['current_sha256']
    assert load_preparation(rebound)[1] == migrated
    with pytest.raises(ContractError, match='another scope'):
        evaluate_prepared(preparation=rebound, out=tmp_path/'stale-review', approval=approval)
    unapproved = evaluate_prepared(preparation=rebound, out=tmp_path/'unapproved')
    assert unapproved['script_verdict'] == 'ACCEPT_FOR_USE'
    assert unapproved['decision'] == 'NEEDS_REVIEW'
    assert any(f['id'] == 'scope.evaluation-policy-review' and f['next_action'] == 'review_specification'
               for f in unapproved['findings'])
    fresh = tmp_path / 'new-approval.json'
    approve_scope(preparation=rebound, out=fresh,
                  expected_scope_sha256=migrated['scope_sha256'], reviewer='Caller', reason='Reviewed policy changes')
    accepted = evaluate_prepared(preparation=rebound, out=tmp_path/'approved', approval=fresh)
    assert accepted['exit_code'] == 0


def test_scope_retains_general_policy_and_pack_identities(tmp_path, bundle):
    prepared = prepare_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'prepared')
    scope = json.loads((tmp_path/'prepared/scope.json').read_text())
    assert scope['evaluation_policy'] == evaluation_policy()
    assert scope['evaluation_policy']['baseline']['checks']
    assert all('implementation_sha256' in pack for pack in scope['evaluation_policy']['packs'].values())
    rebound = bind_preparation(preparation=tmp_path/'prepared', bundle_root=bundle, candidate='scene.usda',
                               out=tmp_path/'rebound', expected_scope_sha256=prepared['scope_sha256'])
    assert rebound['scope_sha256'] == prepared['scope_sha256']
    assert not rebound['binding']['requires_scope_approval']


def test_repair_after_migration_keeps_new_approval_requirement(tmp_path, bundle, monkeypatch):
    prepared = prepare_scene(bundle_root=bundle, candidate='scene.usda', out=tmp_path/'original')
    policy = deepcopy(evaluation_policy())
    policy['baseline']['checks'][0]['required'] = False
    monkeypatch.setattr('scene_acceptance.scope.evaluation_policy', lambda brief=None: deepcopy(policy))
    migrated = bind_preparation(preparation=tmp_path/'original', bundle_root=bundle, candidate='scene.usda',
                               out=tmp_path/'migrated', expected_scope_sha256=prepared['scope_sha256'],
                               migrate_runtime=True, reviewer='Caller', reason='Intentional policy change')
    repaired = bind_preparation(preparation=tmp_path/'migrated', bundle_root=bundle, candidate='scene.usda',
                               out=tmp_path/'repaired', expected_scope_sha256=migrated['scope_sha256'])
    assert repaired['scope_sha256'] == migrated['scope_sha256']
    assert repaired['binding']['requires_scope_approval']
    result = evaluate_prepared(preparation=tmp_path/'repaired', out=tmp_path/'run')
    assert result['decision'] == 'NEEDS_REVIEW'
