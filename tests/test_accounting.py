import json
from copy import deepcopy
import pytest
from scene_acceptance.accounting import read_cost_context, read_invocation, summarize
from scene_acceptance.application import invoke
from scene_acceptance.model import ContractError
from test_review import save
from test_triage import case, kwargs


def context(tmp_path):
    path = tmp_path / "cost.json"
    save(
        path,
        dict(
            schema_version="1.0",
            delivery_id="demo",
            revision_id="v0",
            human_minutes=None,
            compute_cost=None,
            currency=None,
            source="Caller record; costs not yet measured",
        ),
    )
    return path


def receipt(run_id, costs, *, elapsed=3):
    return dict(
        input_sha256=None,
        files={},
        envelope=dict(
            schema_version="1.0",
            run_id=run_id,
            operation="check",
            status="completed",
            exit_code=0,
            reused=False,
            data={},
            errors=[],
            events=[],
            metrics=dict(
                schema_version="1.0",
                elapsed_seconds=elapsed,
                model_calls=[],
                caller_costs=costs,
                limitation="Synthetic accounting control",
            ),
        ),
    )


def test_invocation_records_observed_time_and_preserves_unknown_cost(case, tmp_path):
    args = kwargs(case, tmp_path)
    result = invoke(
        "triage", cost_context=context(tmp_path), reuse_completed=True, **args
    )
    assert result["exit_code"] == 0, result
    assert result["metrics"]["elapsed_seconds"] > 0
    assert result["metrics"]["caller_costs"]["compute_cost"] is None
    assert len(result["metrics"]["model_calls"]) == 1
    receipt = args["out"] / "invocation.json"
    total = summarize([receipt])["deliveries"][0]
    assert total["human_minutes"] is None and total["compute_cost"] is None
    reused = invoke(
        "triage", cost_context=tmp_path / "cost.json", reuse_completed=True, **args
    )
    assert reused["reused"] and reused["metrics"] == result["metrics"]
    with pytest.raises(ContractError, match="Duplicate"):
        summarize([receipt, receipt])


def test_cost_totals_do_not_drop_missing_or_mix_currencies(tmp_path):
    base = dict(
        schema_version="1.0",
        delivery_id="demo",
        revision_id="v0",
        human_minutes=2,
        compute_cost=1,
        currency="USD",
        source="Synthetic ledger control",
    )
    receipts = []
    for i in range(2):
        path = tmp_path / f"{i}.json"
        record = receipt(str(i), base)
        record["envelope"]["exit_code"] = 2 if i == 0 else 0
        save(path, record)
        receipts.append(path)
    summary = summarize(receipts)["deliveries"][0]
    assert summary["compute_cost"] == 2 and summary["human_minutes"] == 4
    last = json.loads(receipts[-1].read_text())
    last["envelope"]["metrics"]["caller_costs"]["currency"] = "EUR"
    save(receipts[-1], last)
    with pytest.raises(ContractError, match="Mixed"):
        summarize(receipts)


@pytest.mark.parametrize(
    "fault",
    [
        "negative-time",
        "negative-cost",
        "missing-currency",
        "missing-envelope-field",
        "reused",
        "infinite-time",
    ],
)
def test_ledger_rejects_invalid_or_replayed_receipts(tmp_path, fault):
    costs = json.loads(context(tmp_path).read_text())
    record = receipt("one", costs)
    metrics = record["envelope"]["metrics"]
    if fault == "negative-time":
        metrics["elapsed_seconds"] = -1
    elif fault == "negative-cost":
        costs.update(compute_cost=-1, currency="USD")
    elif fault == "missing-currency":
        costs["compute_cost"] = 2
    elif fault == "missing-envelope-field":
        record["envelope"].pop("run_id")
    elif fault == "reused":
        record["envelope"]["reused"] = True
    else:
        metrics["elapsed_seconds"] = float("inf")
    path = tmp_path / "invocation.json"
    save(path, record)
    with pytest.raises(ContractError):
        summarize([path])


def test_ledger_keeps_missing_cost_and_rejects_overflow(tmp_path):
    costs = json.loads(context(tmp_path).read_text())
    paths = [tmp_path / "first.json", tmp_path / "second.json"]
    for index, path in enumerate(paths):
        save(path, receipt(str(index), costs))
    assert summarize(paths)["deliveries"][0]["human_minutes"] is None
    for index, path in enumerate(paths):
        save(path, receipt(str(index), costs, elapsed=1e308))
    with pytest.raises(ContractError, match="finite"):
        summarize(paths)


def test_receipt_reader_rejects_nonfile(tmp_path):
    with pytest.raises(ContractError, match="regular file"):
        read_invocation(tmp_path)


def test_copied_inputs_do_not_count_as_model_calls(tmp_path):
    from scene_acceptance.accounting import metrics

    copied = tmp_path / "approved-inputs" / "judge"
    copied.mkdir(parents=True)
    save(
        copied / "judge-result.json",
        dict(
            role="judge",
            model_requested="copied source",
            elapsed_seconds=999,
            usage={"input_tokens": 999},
            status="ADVISORY_REVIEW_COMPLETE",
        ),
    )
    assert metrics(1, tmp_path, None, "evaluate")["model_calls"] == []
    original = tmp_path / "model"
    original.mkdir()
    save(
        original / "triage-model-result.json",
        dict(
            role="triage",
            model_requested="real output control",
            elapsed_seconds=2,
            usage={"input_tokens": 5},
            status="TRIAGE_COMPLETE",
        ),
    )
    assert len(metrics(3, tmp_path, None, "triage")["model_calls"]) == 1
    assert metrics(1, tmp_path, None, "resolve-triage")["model_calls"] == []
