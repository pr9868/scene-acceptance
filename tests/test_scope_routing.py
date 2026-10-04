"""A scope decision routes the caller independently of measured scene failures."""
import json
import subprocess
import sys

import pytest

from scene_acceptance.application import invoke
from scene_acceptance.cli import main as legacy_main
from scene_acceptance.prepared_run import evaluate_prepared
from scene_acceptance.review_context import save
from test_application import approval, resize, scripted_scope, valid
from test_preparation import bundle


@pytest.mark.parametrize('status', ['approved', 'rejected', 'needs_review', None])
@pytest.mark.parametrize('scene_passes', [True, False])
def test_scope_and_scene_decisions_have_distinct_primary_routes(tmp_path, bundle, status, scene_passes):
    if scene_passes:
        resize(bundle)
    kw, plan = scripted_scope(tmp_path, bundle)
    record = approval(tmp_path, kw, plan, status) if status else None
    result = invoke('evaluate', preparation=kw['out'], out=tmp_path/'run', approval=record)
    report = result['data']
    valid('prepared-result-v1', report)
    measurement = next(row for row in report['findings'] if row['id'] == 'check:spec.panel')
    assert measurement['status'] == ('PASS' if scene_passes else 'FAIL')
    if status in ('rejected', 'needs_review'):
        assert result['exit_code'] == 3 and report['decision'] == 'NEEDS_REVIEW'
        assert report['next_action'] == 'review_specification'
        finding = report['findings'][0]
        assert finding['id'] == ('scope.approval-rejected' if status == 'rejected' else 'scope.approval-pending')
        assert finding['next_action'] == 'review_specification'
        assert finding['reason'] == 'Reviewed source requirements against proposed checks'
        assert finding['reviewer'] == 'Caller test'
        assert finding['scope_sha256'] == plan['scope_sha256']
        if not scene_passes:
            assert measurement['next_action'] == 'repair_scene'
    elif not scene_passes:
        assert result['exit_code'] == 2 and report['next_action'] == 'repair_scene'
    elif status == 'approved':
        assert result['exit_code'] == 0 and report['next_action'] == 'none'
    else:
        assert result['exit_code'] == 3 and report['next_action'] == 'review_specification'
    assert report == json.loads((tmp_path/'run/prepared-result.json').read_text())


def test_rejected_scope_does_not_hide_an_execution_error(tmp_path, bundle):
    resize(bundle)
    kw, plan = scripted_scope(tmp_path, bundle)
    record = approval(tmp_path, kw, plan, 'rejected')
    invalid = tmp_path/'invalid-review.json'
    save(invalid, {'invalid': 'A malformed outcome record is an execution error'})
    report = evaluate_prepared(preparation=kw['out'], out=tmp_path/'run', approval=record, review_record=invalid)
    assert report['decision'] == 'EVALUATION_ERROR' and report['exit_code'] == 4
    assert report['next_action'] == 'fix_environment'
    assert report['findings'][0]['id'] == 'scope.approval-rejected'
    assert report['errors']


@pytest.mark.parametrize('args', [[], ['--unknown'], ['--mode', 'invalid'], ['--capabilities', '--candidate', 'scene.usda']])
def test_legacy_usage_errors_are_not_scene_rejections(args):
    with pytest.raises(SystemExit) as error:
        legacy_main(args)
    assert error.value.code == 4


def test_legacy_cli_process_keeps_help_and_usage_distinct():
    for args, code in [(['--help'], 0), (['--unknown'], 4)]:
        result = subprocess.run([sys.executable, '-m', 'scene_acceptance.cli', *args], text=True, capture_output=True)
        assert result.returncode == code
