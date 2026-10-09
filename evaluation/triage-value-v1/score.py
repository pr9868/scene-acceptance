"""Score retained triage recommendations against labels fixed before model runs."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator
from scene_acceptance.accounting import read_invocation
from scene_acceptance.model import ContractError, digest_json, sha, strict_json
from scene_acceptance.triage import result_schema

ROOT = Path(__file__).resolve().parent


def score(labels_path, observations_path):
    labels_path, observations_path = Path(labels_path), Path(observations_path)
    labels, observations = strict_json(labels_path), strict_json(observations_path)
    cases = strict_json(ROOT / "cases.json")["cases"]
    protocol = strict_json(ROOT / "protocol.json")
    if labels.get("cases_sha256") != sha(ROOT / "cases.json"):
        raise ContractError("Labels do not match the frozen case cards")
    if (
        not labels.get("reviewer")
        or labels.get("labeled_before_model_outputs") is not True
    ):
        raise ContractError(
            "A named reviewer must label cases before seeing model outputs"
        )
    if observations.get("labels_sha256") != sha(labels_path) or observations.get(
        "protocol_sha256"
    ) != sha(ROOT / "protocol.json"):
        raise ContractError("Observations do not match the frozen labels and protocol")
    expected = {c["id"] for c in cases}
    truth = {r["id"]: r for r in labels["labels"]}
    observed = {r["id"]: r for r in observations["cases"]}
    if (
        len(truth) != len(labels["labels"])
        or len(observed) != len(observations["cases"])
        or set(truth) != expected
        or set(observed) != expected
    ):
        raise ContractError("Case coverage must match exactly without duplicates")
    if any(
        r["label"] not in ("matters", "routine") or not r.get("reason")
        for r in truth.values()
    ):
        raise ContractError("Every case needs a matters/routine human label and reason")
    if {r["label"] for r in truth.values()} != {"matters", "routine"}:
        raise ContractError("Both label classes are required for this pilot")
    counts = Counter()
    details = []
    seen = set()
    run_ids = set()
    differences = []
    for id in sorted(expected):
        case = observed[id]
        if (
            len(case["runs"]) != protocol["repeats"]
            or any(type(r["repeat"]) is not int for r in case["runs"])
            or {r["repeat"] for r in case["runs"]} != {1, 2, 3}
        ):
            raise ContractError("Exactly three fresh repeats per item are required")
        recommendations = []
        policy_outcomes = []
        repeat_identity = None
        for run in sorted(case["runs"], key=lambda r: r["repeat"]):
            path = (observations_path.parent / run["result"]).resolve()
            if (
                not path.is_relative_to(observations_path.parent.resolve())
                or path in seen
                or not path.is_file()
                or path.stat().st_size > 8388608
            ):
                raise ContractError(
                    "Results must be distinct bounded files inside the observations directory"
                )
            seen.add(path)
            result = strict_json(path)
            Draft202012Validator(result_schema(result.get("schema_version"))).validate(
                result
            )
            receipt_name = run.get("invocation")
            if not isinstance(receipt_name, str) or not receipt_name:
                raise ContractError("Each repeat needs its original invocation receipt")
            receipt_path = (observations_path.parent / receipt_name).resolve()
            if (
                not receipt_path.is_relative_to(observations_path.parent.resolve())
                or receipt_path.parent != path.parent
            ):
                raise ContractError(
                    "Invocation receipt must accompany its result inside the observations directory"
                )
            receipt = read_invocation(receipt_path)
            envelope = receipt["envelope"]
            if (
                envelope["operation"] != "triage"
                or envelope["reused"]
                or result.get("parent_triage_sha256")
            ):
                raise ContractError(
                    "Only original triage executions count as fresh repeats"
                )
            if envelope["run_id"] in run_ids:
                raise ContractError(
                    "A copied invocation cannot count as a fresh repeat"
                )
            run_ids.add(envelope["run_id"])
            if receipt["files"].get(path.name) != sha(path) or digest_json(
                envelope["data"]
            ) != digest_json(result):
                raise ContractError(
                    "Triage result does not match its retained invocation receipt"
                )
            identity = (run["item_id"],) + tuple(
                result[key]
                for key in (
                    "assessment_sha256",
                    "policy_sha256",
                    "snapshot_sha256",
                    "runtime_sha256",
                    "request_sha256",
                    "model_requested",
                )
            )
            if repeat_identity is not None and identity != repeat_identity:
                raise ContractError(
                    "Repeats must use the same assessment, item, policy, evidence, model and runtime"
                )
            repeat_identity = identity
            selected = [r for r in result["items"] if r["item_id"] == run["item_id"]]
            if len(selected) != 1:
                raise ContractError(
                    "Result does not contain the selected item exactly once"
                )
            row = selected[0]
            opinion = row["model_recommendation"]
            recommendation = (
                opinion["recommendation"]
                if result["execution_status"] == "completed" and opinion
                else "provider_error"
            )
            recommendations.append(recommendation)
            policy_outcomes.append(row["policy_outcome"])
            counts["runs"] += 1
            counts[recommendation] += 1
            counts[truth[id]["label"] + "_runs"] += 1
            if truth[id]["label"] == "matters" and recommendation == "routine_handling":
                counts["important_misses"] += 1
            if truth[id]["label"] == "routine" and recommendation != "routine_handling":
                counts["routine_escalations"] += 1
        if truth[id]["label"] == "matters" and "routine_handling" in recommendations:
            counts["important_items_missed"] += 1
        if len(set(recommendations)) > 1:
            counts["variable_items"] += 1
        baseline, harness = case.get("baseline_human_minutes"), case.get(
            "harness_human_minutes"
        )
        for value in (baseline, harness):
            if value is not None and (
                type(value) not in (int, float) or not math.isfinite(value) or value < 0
            ):
                raise ContractError("Reviewer time must be nonnegative minutes or null")
        if baseline is not None and harness is not None:
            differences.append(baseline - harness)
        details.append(
            dict(
                id=id,
                label=truth[id]["label"],
                raw_model_recommendations=recommendations,
                policy_outcomes=policy_outcomes,
                baseline_human_minutes=baseline,
                harness_human_minutes=harness,
            )
        )
    rate = counts["routine_escalations"] / counts["routine_runs"]
    passed = (
        counts["important_misses"] <= protocol["max_important_routine_recommendations"]
        and rate < protocol["routine_escalation_rate_strictly_below"]
        and not counts["provider_error"]
    )
    return dict(
        schema_version="1.0",
        pilot_items=len(cases),
        counts={
            k: counts[k]
            for k in (
                "runs",
                "matters_runs",
                "routine_runs",
                "important_items_missed",
                "important_misses",
                "routine_escalations",
                "insufficient_context",
                "provider_error",
                "variable_items",
            )
        },
        routine_escalation_rate=rate,
        preregistered_bar_passed=passed,
        items=details,
        paired_time_items=len(differences),
        human_minutes_saved_on_paired_items=sum(differences) if differences else None,
        labels_sha256=sha(labels_path),
        protocol_sha256=sha(ROOT / "protocol.json"),
        limitation="Selected pilot cases only. Label timing and independence are reviewer declarations. "
        "Original receipt IDs and hashes reject copied runs but do not authenticate execution. "
        "Policy-enforced escalation is not model-quality credit. Missing time is not zero effort.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("labels", "observations", "out"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    result = score(args.labels, args.observations)
    with Path(args.out).open("x") as output:
        json.dump(result, output, indent=2)
