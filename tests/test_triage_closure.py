"""Recorded human decisions close only current requests, never missing checks."""
from copy import deepcopy
import json

import pytest
from jsonschema import ValidationError

from scene_acceptance.application import invoke
from scene_acceptance.model import ContractError, sha
from scene_acceptance.triage import apply_policy, combined_outcome, run_triage, normalize_response, validate_response
from scene_acceptance.triage_review import resolve_triage
from test_triage import case, kwargs, update_assessment
from test_review import approve, save


def pending(case, tmp_path, mode='routine_handling'):
    case[5]['items'][0]['mandatory_human_review'] = True
    args = kwargs(case, tmp_path, mode)
    result = run_triage(**args)
    assert result['exit_code'] == 3
    approve(case[1], {'snapshot_sha256': result['review_context_sha256']}, {'material-binding': 'approved'})
    resolve = dict(triage_run=args['out'], expected_triage_sha256=sha(args['out'] / 'triage-result.json'),
                   review_record='reviews.json', out=tmp_path / 'resolved')
    return result, resolve


def test_mandatory_review_closes_without_model(case, tmp_path, monkeypatch):
    from scene_acceptance import judge
    before, args = pending(case, tmp_path)
    def no_model(*args, **kwargs):
        pytest.fail('Resolving a review must not call a model')
    monkeypatch.setattr(judge, 'run_request', no_model)
    result = resolve_triage(**args)
    assert result['exit_code'] == 0
    assert result['items'][0]['human_review']['status'] == 'approved'
    assert result['items'][0]['model_recommendation'] == before['items'][0]['model_recommendation']
    assert result['items'][0]['policy_rule']['mandatory_human_review'] is True
    assert 'Human decision' in (args['out'] / 'report.html').read_text()
    assert 'Model’s reading of the policy' in (args['out'] / 'report.html').read_text()


@pytest.mark.parametrize('status', ['rejected', 'needs_review', 'omitted'])
def test_unclosed_human_decision_remains_review(case, tmp_path, status):
    before, args = pending(case, tmp_path)
    path = case[1] / 'reviews.json'
    review = json.loads(path.read_text())
    if status == 'omitted':
        review['reviews'] = []
    else:
        review['reviews'][0]['status'] = status
    save(path, review)
    result = resolve_triage(**args)
    assert result['exit_code'] == 3 and result['next_action'] == 'review_finding'


@pytest.mark.parametrize('changed', ['scene', 'assessment', 'policy', 'evidence', 'snapshot', 'item', 'result', 'request'])
def test_changed_inputs_invalidate_approval(case, tmp_path, changed):
    _, args = pending(case, tmp_path)
    if changed in ('snapshot', 'item'):
        path = case[1] / 'reviews.json'
        review = json.loads(path.read_text())
        if changed == 'snapshot':
            review['snapshot_sha256'] = '0' * 64
        else:
            review['reviews'][0]['item_id'] = 'unrequested'
        save(path, review)
    else:
        path = {'scene': case[0] / 'scene.usda', 'assessment': case[4],
                'policy': case[1] / 'triage-policy.json', 'evidence': case[1] / 'control-review.txt',
                'result': args['triage_run'] / 'triage-result.json',
                'request': args['triage_run'] / 'model/request.json'}[changed]
        if changed == 'request':
            request = json.loads(path.read_text()); request['intended_use'] = 'Tampered'; save(path, request)
        else:
            path.write_text(path.read_text() + '\nchanged')
    with pytest.raises((ContractError, ValueError)):
        resolve_triage(**args)
    assert not args['out'].exists()


@pytest.mark.parametrize('status', ['UNKNOWN', 'ERROR', 'FAIL'])
def test_human_review_does_not_clear_original_problem(case, status):
    original = deepcopy(case[3])
    original['items'][0]['status'] = status
    rows = apply_policy(original, case[5], None, set(), {'material-binding': {'status': 'approved'}})
    assert rows[0]['policy_outcome'] != 'routine_handling'
    expected = 'review_finding' if status == 'FAIL' else 'provide_evidence'
    assert combined_outcome('NEEDS_REVIEW', rows, [])[2] == expected


def test_pending_scope_keeps_specific_evidence_action(case, tmp_path):
    case[2]['mapping_review']['status'] = 'pending'
    update_assessment(case)
    result = run_triage(**kwargs(case, tmp_path, 'insufficient_context'))
    assert result['next_action'] == 'provide_evidence'


def test_scope_gap_remains_after_triage_approval(case, tmp_path):
    case[2]['mapping_review']['status'] = 'pending'
    update_assessment(case)
    _, args = pending(case, tmp_path)
    result = resolve_triage(**args)
    assert result['exit_code'] == 3 and result['next_action'] == 'review_specification'


def test_non_utf8_is_contract_error(case, tmp_path):
    path = case[1] / 'reference.txt'; path.write_bytes(b'\xff\xfe')
    case[5]['evidence'] = [dict(id='source', path=path.name, sha256=sha(path), kind='text', description='Encoding control')]
    case[5]['items'][0]['evidence_ids'] = ['source']
    args = kwargs(case, tmp_path)
    with pytest.raises(ContractError, match='UTF-8'):
        run_triage(**args)
    result = invoke('triage', **args)
    assert result['exit_code'] == 4 and result['errors'][0]['code'] == 'ContractError'


def test_resolve_application_replay_is_verified(case, tmp_path):
    _, args = pending(case, tmp_path)
    first = invoke('resolve-triage', reuse_completed=True, **args)
    assert first['exit_code'] == 0, first
    second = invoke('resolve-triage', reuse_completed=True, **args)
    assert second['reused'] and second['exit_code'] == 0
    (case[1] / 'control-review.txt').write_text('Changed owner evidence')
    assert invoke('resolve-triage', reuse_completed=True, **args)['exit_code'] == 4


@pytest.mark.parametrize('version', [None, '1.0', '1.1'])
def test_response_version_compatibility(case, tmp_path, version):
    result = run_triage(**kwargs(case, tmp_path))
    request = json.loads((tmp_path / 'triage/model/request.json').read_text())
    row = deepcopy(result['items'][0]['model_recommendation'])
    response = dict(request_sha256=result['request_sha256'], items=[row], limitations=['Synthetic control'])
    if version != '1.1':
        row['policy_reason'] = row.pop('model_policy_paraphrase')
    if version:
        response['schema_version'] = version
    validate_response(response, request)
    normalized = normalize_response(response)
    assert normalized['schema_version'] == '1.1'
    assert 'policy_reason' not in normalized['items'][0]
    response['schema_version'] = '9.9'
    with pytest.raises(ValidationError):
        validate_response(response, request)


def test_notice_configuration_is_driver_specific(case, tmp_path):
    args = kwargs(case, tmp_path)
    config = json.loads(args['triage_config'].read_text())
    config['ignored_codex_notices'] = ['Exact controlled notice']
    save(args['triage_config'], config)
    with pytest.raises(ContractError, match='Codex'):
        run_triage(**args)
