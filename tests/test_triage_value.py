"""Scorer controls only; synthetic labels and model outputs are not study evidence."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest
from scene_acceptance.model import ContractError, sha, strict_json
from scene_acceptance.triage import run_triage
from test_review import save
from test_triage import case, kwargs

SPEC = importlib.util.spec_from_file_location('triage_score', Path(__file__).resolve().parents[1] / 'evaluation/triage-value-v1/score.py')
SCORER = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(SCORER)


def packet(case, tmp_path):
    base = run_triage(**kwargs(case, tmp_path))
    labels = strict_json(SCORER.ROOT / 'labels.template.json')
    labels.update(reviewer='Synthetic scorer test only', labeled_before_model_outputs=True)
    observations = dict(cases=[], protocol_sha256=sha(SCORER.ROOT / 'protocol.json'))
    for index, label in enumerate(labels['labels']):
        label.update(label='matters' if index < 5 else 'routine', reason='Synthetic scorer control')
        runs = []
        for repeat in (1, 2, 3):
            result = deepcopy(base)
            result['items'][0]['model_recommendation']['recommendation'] = 'human_review_needed' if index < 5 else 'routine_handling'
            path = tmp_path / f'{index}-{repeat}.json'; save(path, result)
            runs.append(dict(repeat=repeat, result=path.name, item_id='material-binding'))
        observations['cases'].append(dict(id=label['id'], runs=runs, baseline_human_minutes=None, harness_human_minutes=None))
    lp = tmp_path / 'labels.json'; save(lp, labels)
    observations['labels_sha256'] = sha(lp)
    op = tmp_path / 'observations.json'; save(op, observations)
    return lp, op


def test_scorer_separates_model_miss_from_mandatory_policy(case, tmp_path):
    lp, op = packet(case, tmp_path)
    result = SCORER.score(lp, op)
    assert result['preregistered_bar_passed'] and result['counts']['runs'] == 30
    assert result['human_minutes_saved_on_paired_items'] is None
    path = tmp_path / '0-1.json'; record = strict_json(path)
    record['items'][0]['model_recommendation']['recommendation'] = 'routine_handling'
    record['items'][0]['policy_outcome'] = 'human_review_needed'
    save(path, record)
    result = SCORER.score(lp, op)
    assert not result['preregistered_bar_passed']
    assert result['counts']['important_misses'] == 1 and result['counts']['variable_items'] == 1


def test_scorer_rejects_missing_labels_and_reused_output(case, tmp_path):
    lp, op = packet(case, tmp_path)
    labels = strict_json(lp); labels['labels'][0]['label'] = None; save(lp, labels)
    observations = strict_json(op); observations['labels_sha256'] = sha(lp); save(op, observations)
    with pytest.raises(ContractError, match='human label'):
        SCORER.score(lp, op)
    labels['labels'][0]['label'] = 'matters'; save(lp, labels)
    observations['labels_sha256'] = sha(lp)
    observations['cases'][0]['runs'][1]['result'] = observations['cases'][0]['runs'][0]['result']
    save(op, observations)
    with pytest.raises(ContractError, match='distinct'):
        SCORER.score(lp, op)
