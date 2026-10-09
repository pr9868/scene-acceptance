import json
from copy import deepcopy
import pytest
from scene_acceptance.accounting import read_cost_context, summarize
from scene_acceptance.application import invoke
from scene_acceptance.model import ContractError
from test_review import save
from test_triage import case, kwargs


def context(tmp_path):
    path = tmp_path / 'cost.json'
    save(path, dict(schema_version='1.0', delivery_id='demo', revision_id='v0', human_minutes=None,
                    compute_cost=None, currency=None, source='Caller record; costs not yet measured'))
    return path


def test_invocation_records_observed_time_and_preserves_unknown_cost(case, tmp_path):
    args = kwargs(case, tmp_path)
    result = invoke('triage', cost_context=context(tmp_path), reuse_completed=True, **args)
    assert result['exit_code'] == 0, result
    assert result['metrics']['elapsed_seconds'] > 0
    assert result['metrics']['caller_costs']['compute_cost'] is None
    assert len(result['metrics']['model_calls']) == 1
    receipt = args['out'] / 'invocation.json'
    total = summarize([receipt])['deliveries'][0]
    assert total['human_minutes'] is None and total['compute_cost'] is None
    reused = invoke('triage', cost_context=tmp_path / 'cost.json', reuse_completed=True, **args)
    assert reused['reused'] and reused['metrics'] == result['metrics']
    with pytest.raises(ContractError, match='Duplicate'):
        summarize([receipt, receipt])


def test_cost_totals_do_not_drop_missing_or_mix_currencies(tmp_path):
    base = dict(schema_version='1.0', delivery_id='demo', revision_id='v0', human_minutes=2,
                compute_cost=1, currency='USD', source='Synthetic ledger control')
    receipts = []
    for i in range(2):
        path = tmp_path / f'{i}.json'
        save(path, dict(envelope=dict(run_id=str(i), operation='check', exit_code=2 if i == 0 else 0,
                   metrics=dict(elapsed_seconds=3, caller_costs=base))))
        receipts.append(path)
    summary = summarize(receipts)['deliveries'][0]
    assert summary['compute_cost'] == 2 and summary['human_minutes'] == 4
    last = json.loads(receipts[-1].read_text())
    last['envelope']['metrics']['caller_costs']['currency'] = 'EUR'; save(receipts[-1], last)
    with pytest.raises(ContractError, match='Mixed'):
        summarize(receipts)



def test_copied_inputs_do_not_count_as_model_calls(tmp_path):
    from scene_acceptance.accounting import metrics
    copied = tmp_path / 'approved-inputs' / 'judge'
    copied.mkdir(parents=True)
    save(copied / 'judge-result.json', dict(role='judge', model_requested='copied source',
         elapsed_seconds=999, usage={'input_tokens': 999}, status='ADVISORY_REVIEW_COMPLETE'))
    assert metrics(1, tmp_path, None, 'evaluate')['model_calls'] == []
    original = tmp_path / 'model'; original.mkdir()
    save(original / 'triage-model-result.json', dict(role='triage', model_requested='real output control',
         elapsed_seconds=2, usage={'input_tokens': 5}, status='TRIAGE_COMPLETE'))
    assert len(metrics(3, tmp_path, None, 'triage')['model_calls']) == 1
    assert metrics(1, tmp_path, None, 'resolve-triage')['model_calls'] == []
