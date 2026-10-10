"""Saved attempts are discoverable without weakening evidence or replay checks."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from scene_acceptance import __version__
from scene_acceptance.application import invoke, main
from scene_acceptance.application_schemas import ENVELOPE_SCHEMA
from scene_acceptance.engine import VERSION
from scene_acceptance.execution import RunControl
from scene_acceptance.model import ContractError, sha
from scene_acceptance.run_storage import start_run
from test_preparation import bundle
from test_triage import case, kwargs


def test_default_runs_keep_separate_reports_and_scene_bytes(tmp_path, monkeypatch, bundle):
    monkeypatch.chdir(tmp_path)
    before = {str(p): sha(p) for p in bundle.rglob('*') if p.is_file()}
    first = invoke('check', bundle_root=bundle, candidate='scene.usda')
    report = Path(first['storage']['summary_report'])
    retained = report.read_bytes()
    second = invoke('check', bundle_root=bundle, candidate='scene.usda')
    for result in (first, second):
        assert result['status'] == 'completed'
        Draft202012Validator(ENVELOPE_SCHEMA).validate(result)
        record = json.loads(Path(result['storage']['record']).read_text())
        assert record['envelope'] == result
        output = Path(result['storage']['output_directory'])
        assert (output / 'invocation.json').is_file()
        assert (output / 'report.html').is_file()
        assert 'output/report.html' in Path(result['storage']['summary_report']).read_text()
    assert first['storage']['run_directory'] != second['storage']['run_directory']
    assert report.read_bytes() == retained
    assert before == {str(p): sha(p) for p in bundle.rglob('*') if p.is_file()}
    assert (tmp_path / 'scene-acceptance-runs/.gitignore').is_file()
    assert VERSION == __version__


def test_errors_before_component_output_still_have_report(tmp_path):
    result = invoke('triage', run_root=tmp_path / 'history')
    assert result['exit_code'] == 4
    path = Path(result['storage']['summary_report'])
    assert path.is_file() and 'Execution errors' in path.read_text()
    record = json.loads(Path(result['storage']['record']).read_text())
    assert record['status'] == 'failed' and record['completed_at']
    assert not Path(result['storage']['output_directory']).exists()


def test_cancelled_auto_run_is_retained(tmp_path, bundle):
    result = invoke('check', run_root=tmp_path / 'history',
                    control=RunControl(cancelled=True), bundle_root=bundle, candidate='scene.usda')
    assert result['status'] == 'cancelled'
    assert Path(result['storage']['record']).is_file()
    assert not Path(result['storage']['output_directory']).exists()


def test_explicit_output_and_verified_replay_stay_unchanged(tmp_path, bundle):
    output = tmp_path / 'explicit'
    args = dict(bundle_root=bundle, candidate='scene.usda', out=output, reuse_completed=True)
    first = invoke('prepare', **args)
    assert first['exit_code'] == 3 and 'storage' not in first
    saved = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    assert invoke('prepare', **args)['reused']
    assert saved == {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    conflict = invoke('prepare', run_root=tmp_path / 'history', **args)
    assert conflict['exit_code'] == 4 and not (tmp_path / 'history').exists()
    assert saved == {str(p): sha(p) for p in output.rglob('*') if p.is_file()}


def test_default_history_cannot_pollute_scene_bundle(tmp_path, bundle, monkeypatch):
    monkeypatch.chdir(bundle)
    result = invoke('check', bundle_root=bundle, candidate='scene.usda')
    assert result['exit_code'] == 4 and '--run-root' in result['errors'][0]['message']
    assert not (bundle / 'scene-acceptance-runs').exists()
    link = tmp_path / 'link'
    link.symlink_to(bundle, target_is_directory=True)
    with pytest.raises(ContractError, match='outside input'):
        start_run('check', {'bundle_root': str(bundle)}, link / 'history', 'test')


def test_history_cli_defaults_and_doctor_has_no_output_side_effect(tmp_path, bundle, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(['prepare', '--bundle-root', str(bundle), '--candidate', 'scene.usda']) == 3
    prepared = json.loads(capsys.readouterr().out)
    assert Path(prepared['storage']['summary_report']).exists()
    folders = set((tmp_path / 'scene-acceptance-runs').iterdir())
    result = invoke('doctor')
    assert 'storage' not in result
    assert set((tmp_path / 'scene-acceptance-runs').iterdir()) == folders


def test_parallel_reservations_do_not_overwrite_and_html_escapes(tmp_path):
    def reserve(i):
        return start_run('triage', {'candidate': '<script>bad()</script>'}, tmp_path, str(i))[0]
    with ThreadPoolExecutor(max_workers=4) as workers:
        folders = list(workers.map(reserve, range(12)))
    assert len(set(folders)) == 12
    for folder in folders:
        assert json.loads((folder / 'run.json').read_text())['status'] == 'running'
        page = (folder / 'index.html').read_text()
        assert '<script>' not in page and '&lt;script&gt;' in page


def test_reuse_needs_explicit_original_output(tmp_path, bundle):
    result = invoke('check', bundle_root=bundle, candidate='scene.usda',
                    run_root=tmp_path / 'history', reuse_completed=True)
    assert result['exit_code'] == 4
    assert 'original explicit --out' in result['errors'][0]['message']
    assert not (tmp_path / 'history').exists()


@pytest.mark.parametrize('mode,code', [('human_review_needed', 3), ('malformed', 4)])
def test_triage_history_retains_model_evidence_even_on_failure(case, tmp_path, mode, code):
    args = kwargs(case, tmp_path, mode)
    args.pop('out')
    result = invoke('triage', run_root=tmp_path / 'history', **args)
    assert result['exit_code'] == code
    output = Path(result['storage']['output_directory'])
    for name in ('report.html', 'triage-result.json', 'review-requests.json',
                 'assessment.json', 'policy.json', 'manifest.json',
                 'model/request.json', 'model/stdout.log', 'model/stderr.log'):
        assert (output / name).is_file(), name
    summary = Path(result['storage']['summary_report']).read_text()
    assert 'Human-review levels' in summary
    assert 'model-assisted routing' in summary.lower()
    assert json.loads(Path(result['storage']['record']).read_text())['envelope'] == result
