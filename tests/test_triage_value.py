"""Scorer controls only; synthetic labels and model outputs are not study evidence."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest
from scene_acceptance.model import ContractError, sha, strict_json
from scene_acceptance.application import invoke
from test_review import save
from test_triage import case, kwargs

SPEC = importlib.util.spec_from_file_location(
    "triage_score",
    Path(__file__).resolve().parents[1] / "evaluation/triage-value-v1/score.py",
)
SCORER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCORER)


def packet(case, tmp_path):
    envelope = invoke("triage", **kwargs(case, tmp_path))
    base = envelope["data"]
    labels = strict_json(SCORER.ROOT / "labels.template.json")
    labels.update(
        reviewer="Synthetic scorer test only", labeled_before_model_outputs=True
    )
    observations = dict(cases=[], protocol_sha256=sha(SCORER.ROOT / "protocol.json"))
    for index, label in enumerate(labels["labels"]):
        label.update(
            label="matters" if index < 5 else "routine",
            reason="Synthetic scorer control",
        )
        runs = []
        for repeat in (1, 2, 3):
            result = deepcopy(base)
            result["items"][0]["model_recommendation"]["recommendation"] = (
                "human_review_needed" if index < 5 else "routine_handling"
            )
            folder = tmp_path / f"{index}-{repeat}"
            folder.mkdir()
            path = folder / "triage-result.json"
            save(path, result)
            record = deepcopy(envelope)
            record.update(data=result, run_id=f"synthetic-{index}-{repeat}")
            receipt = folder / "invocation.json"
            save(
                receipt,
                dict(input_sha256=None, envelope=record, files={path.name: sha(path)}),
            )
            runs.append(
                dict(
                    repeat=repeat,
                    result=str(path.relative_to(tmp_path)),
                    invocation=str(receipt.relative_to(tmp_path)),
                    item_id="material-binding",
                )
            )
        observations["cases"].append(
            dict(
                id=label["id"],
                runs=runs,
                baseline_human_minutes=None,
                harness_human_minutes=None,
            )
        )
    lp = tmp_path / "labels.json"
    save(lp, labels)
    observations["labels_sha256"] = sha(lp)
    op = tmp_path / "observations.json"
    save(op, observations)
    return lp, op


def revise_result(path, result):
    """Keep synthetic receipt fixtures internally consistent for scorer controls."""
    save(path, result)
    receipt_path = path.parent / "invocation.json"
    receipt = strict_json(receipt_path)
    receipt["envelope"]["data"] = result
    receipt["files"][path.name] = sha(path)
    save(receipt_path, receipt)


def test_scorer_separates_model_miss_from_mandatory_policy(case, tmp_path):
    lp, op = packet(case, tmp_path)
    result = SCORER.score(lp, op)
    assert result["preregistered_bar_passed"] and result["counts"]["runs"] == 30
    assert result["human_minutes_saved_on_paired_items"] is None
    path = tmp_path / "0-1/triage-result.json"
    record = strict_json(path)
    record["items"][0]["model_recommendation"]["recommendation"] = "routine_handling"
    record["items"][0]["policy_outcome"] = "human_review_needed"
    revise_result(path, record)
    result = SCORER.score(lp, op)
    assert not result["preregistered_bar_passed"]
    assert (
        result["counts"]["important_misses"] == 1
        and result["counts"]["variable_items"] == 1
    )


def test_scorer_rejects_missing_labels_and_reused_output(case, tmp_path):
    lp, op = packet(case, tmp_path)
    labels = strict_json(lp)
    labels["labels"][0]["label"] = None
    save(lp, labels)
    observations = strict_json(op)
    observations["labels_sha256"] = sha(lp)
    save(op, observations)
    with pytest.raises(ContractError, match="human label"):
        SCORER.score(lp, op)
    labels["labels"][0]["label"] = "matters"
    save(lp, labels)
    observations["labels_sha256"] = sha(lp)
    observations["cases"][0]["runs"][1]["result"] = observations["cases"][0]["runs"][0][
        "result"
    ]
    save(op, observations)
    with pytest.raises(ContractError, match="distinct"):
        SCORER.score(lp, op)


def test_copied_files_are_not_fresh_repeats(case, tmp_path):
    lp, op = packet(case, tmp_path)
    for filename in ("triage-result.json", "invocation.json"):
        (tmp_path / "0-2" / filename).write_bytes(
            (tmp_path / "0-1" / filename).read_bytes()
        )
    with pytest.raises(ContractError, match="copied invocation"):
        SCORER.score(lp, op)


@pytest.mark.parametrize(
    "fault, message",
    [
        ("missing-receipt", "original invocation"),
        ("changed-result", "retained invocation"),
        ("changed-scope", "same assessment"),
        ("replay", "original triage"),
        ("human-resolution", "original triage"),
        ("different-item", "same assessment"),
        ("boolean-repeat", "three fresh repeats"),
        ("missing-result", "distinct bounded files"),
    ],
)
def test_scoring_requires_bound_original_runs(case, tmp_path, fault, message):
    lp, op = packet(case, tmp_path)
    path = tmp_path / "0-2/triage-result.json"
    result = strict_json(path)
    if fault == "missing-receipt":
        observations = strict_json(op)
        observations["cases"][0]["runs"][1].pop("invocation")
        save(op, observations)
    elif fault == "changed-result":
        result["items"][0]["model_recommendation"][
            "recommendation"
        ] = "routine_handling"
        save(path, result)
    elif fault == "changed-scope":
        result["policy_sha256"] = "b" * 64
        revise_result(path, result)
    elif fault == "replay":
        receipt_path = path.parent / "invocation.json"
        receipt = strict_json(receipt_path)
        receipt["envelope"]["reused"] = True
        save(receipt_path, receipt)
    elif fault == "human-resolution":
        result["parent_triage_sha256"] = "a" * 64
        revise_result(path, result)
    else:
        observations = strict_json(op)
        run = observations["cases"][0]["runs"][1]
        if fault == "different-item":
            run["item_id"] = "another-item"
        elif fault == "boolean-repeat":
            observations["cases"][0]["runs"][0]["repeat"] = True
        else:
            run["result"] = "missing-result.json"
        save(op, observations)
    with pytest.raises(ContractError, match=message):
        SCORER.score(lp, op)
