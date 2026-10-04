"""The replay verifier must not become permissive under python -O."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'reproduce.py'
SPEC = importlib.util.spec_from_file_location('replay_verifier', SCRIPT)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


@pytest.mark.parametrize('check', ['file', 'checker', 'skipped', 'reports', 'physics'])
def test_optimized_python_still_rejects_failed_integrity_checks(tmp_path, check):
    (tmp_path / 'source').write_text('modified')
    (tmp_path / 'pytest.xml').write_text('<testsuites><testsuite tests="1" skipped="1"/></testsuites>')
    expressions = {
        'file': "m.verify_files(root, {'files': {'source': '0' * 64}})",
        'checker': "m.verify_checker('changed', 'retained')",
        'skipped': "m.verify_pytest(root / 'pytest.xml')",
        'reports': "m.compare_saved_reports(root / 'missing', root / 'also-missing')",
        'physics': "m.compare_physics({'cases': {}}, {'cases': {}})",
    }
    code = f'''
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('replay_verifier', {str(SCRIPT)!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
root = Path({str(tmp_path)!r})
try:
    {expressions[check]}
except m.VerificationError as exc:
    print(str(exc))
else:
    raise SystemExit('Invalid replay was accepted under -O')
'''
    result = subprocess.run([sys.executable, '-O', '-c', code], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip()


def test_report_comparison_detects_a_missing_case_and_changed_check(tmp_path):
    current, retained = tmp_path / 'current', tmp_path / 'retained'
    report = {'verdict': 'ACCEPT_FOR_USE', 'checks': [{'id': 'x', 'status': 'PASS'}]}
    for root in (current, retained):
        (root / 'a').mkdir(parents=True)
        (root / 'a/result.json').write_text(json.dumps(report))
    assert replay.compare_saved_reports(current, retained) == {'a': True}
    changed = deepcopy(report)
    changed['checks'][0]['status'] = 'UNKNOWN'
    (current / 'a/result.json').write_text(json.dumps(changed))
    with pytest.raises(replay.VerificationError, match='status differs'):
        replay.compare_saved_reports(current, retained)
    (current / 'a/result.json').unlink()
    with pytest.raises(replay.VerificationError, match='set differs'):
        replay.compare_saved_reports(current, retained)


def test_physics_comparison_requires_finite_values_and_same_decisions():
    saved = {'cases': {'block': {'configuration': 'ACCEPT_FOR_USE', 'runs': [
        {'final_displacement_m': .001, 'dt_s': .001, 'behavior': 'PASS'}]}}}
    assert replay.compare_physics(saved, saved) == {'block:0': True}
    for key, value in [('final_displacement_m', float('nan')), ('behavior', 'FAIL'), ('dt_s', .002)]:
        changed = deepcopy(saved)
        changed['cases']['block']['runs'][0][key] = value
        with pytest.raises(replay.VerificationError, match='differs'):
            replay.compare_physics(changed, saved)
