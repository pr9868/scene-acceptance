"""Executable identity is checked, not merely printed in a simulation receipt."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from scene_acceptance.followups import simulation, worker
from scene_acceptance.model import sha
from test_article_checks import real_result


@pytest.mark.parametrize('field', list(simulation.CODE_FILES))
@pytest.mark.parametrize('fault', ['missing_result', 'stale_result', 'stale_job', 'changed_parent'])
def test_result_rejects_missing_or_changed_code_identity(real_result, monkeypatch, field, fault):
    original, original_job = real_result
    result, job = deepcopy(original), deepcopy(original_job)
    if fault == 'missing_result':
        result.pop(field)
    elif fault == 'stale_result':
        result[field] = '0' * 64
    elif fault == 'stale_job':
        job[field] = '0' * 64
    else:
        current = simulation.expected_code_identity()
        current[field] = '0' * 64
        monkeypatch.setattr(simulation, 'expected_code_identity', lambda: current)
    with pytest.raises(ValueError, match='Worker code identity'):
        simulation.validate_result(result, job, 'correct-job')


@pytest.mark.parametrize('field', list(simulation.CODE_FILES))
def test_worker_refuses_stale_code_before_simulating(tmp_path, monkeypatch, field):
    scene = Path(worker.__file__).with_name('incline-profile.usda')
    job = {'input_sha256': sha(scene), 'dt_s': .001, 'duration_s': .01, **worker.code_identity()}
    job[field] = '0' * 64
    path = tmp_path/'job.json'
    path.write_text(json.dumps(job))
    monkeypatch.setattr(sys, 'argv', ['worker', str(scene), str(path)])
    monkeypatch.setattr(worker, 'simulate', lambda *args: pytest.fail('Stale code reached simulation'))
    with pytest.raises(RuntimeError, match='identity differs'):
        worker.main()


def test_worker_rechecks_installed_code_after_simulation(tmp_path, monkeypatch):
    scene = Path(worker.__file__).with_name('incline-profile.usda')
    identity = worker.code_identity()
    job = {'input_sha256': sha(scene), 'dt_s': .001, 'duration_s': .01, **identity}
    path = tmp_path/'job.json'
    path.write_text(json.dumps(job))
    monkeypatch.setattr(sys, 'argv', ['worker', str(scene), str(path)])

    def replace_after_simulation(*args):
        monkeypatch.setattr(worker, 'code_identity', lambda: {**identity, 'worker_sha256': '0' * 64})
        return {}

    monkeypatch.setattr(worker, 'simulate', replace_after_simulation)
    with pytest.raises(RuntimeError, match='identity differs'):
        worker.main()
