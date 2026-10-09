"""Close triage requests through the existing caller-owned review record format."""

from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from .model import ContractError, digest_json, sha, strict_json
from .review.schemas import REVIEW
from .review_context import save
from .triage_risk import review_risk_counts


def review_requests(result):
    """Identity excludes the future decision, avoiding self-invalidating approvals."""
    items = []
    for row in result["items"]:
        if row["policy_outcome"] == "routine_handling":
            continue
        items.append(
            {
                "item_id": row["item_id"],
                "statement": row["statement"],
                "item_sha256": digest_json(row),
                "reason": " ".join(row["policy_reasons"]),
            }
        )
        if result["schema_version"] in ("1.2", "1.3"):
            items[-1].update(
                review_risk=row["review_risk"],
                review_risk_basis=row["review_risk_basis"],
                review_risk_reason=row["review_risk_reason"],
            )
    request = {
        "schema_version": (
            "1.1" if result["schema_version"] in ("1.2", "1.3") else "1.0"
        ),
        "kind": "triage-review-requests",
        "assessment_sha256": result["assessment_sha256"],
        "policy_sha256": result["policy_sha256"],
        "triage_request_sha256": result["request_sha256"],
        "input_sha256": digest_json(result["input_hashes"]),
        "items": items,
    }
    request["snapshot_sha256"] = digest_json(request)
    return request


def resolve_triage(*, triage_run, expected_triage_sha256, review_record, out):
    """Consume human decisions with no model call and without changing original checks.

    The caller selects and pins the original triage result. Its request snapshot
    binds the policy, assessment, selected items and evidence. This reuses REVIEW;
    it does not authenticate reviewer identity or accept producer self-approval.
    """
    from .engine import implementation_digest
    from .triage import (
        RESULT_SCHEMA,
        _inside,
        _report,
        _unique,
        apply_policy,
        combined_outcome,
        load_context,
        unchanged,
    )

    source = Path(triage_run).resolve(strict=True)
    result_path = source / "triage-result.json"
    if (
        result_path.stat().st_size > 8388608
        or sha(result_path) != expected_triage_sha256
    ):
        raise ContractError("Triage result does not match its caller-pinned hash")
    previous = strict_json(result_path)
    Draft202012Validator(RESULT_SCHEMA).validate(previous)
    if previous.get("parent_triage_sha256"):
        raise ContractError(
            "Resolve the original triage request, not a previously resolved copy"
        )
    if previous["execution_status"] != "completed" or previous["errors"]:
        raise ContractError(
            "Resolve evaluation errors before recording triage decisions"
        )
    if previous["runtime_sha256"] != implementation_digest():
        raise ContractError("Triage implementation changed; rerun triage before review")
    if not previous.get("context") or not previous.get("review_context_sha256"):
        raise ContractError("This triage result predates review requests; rerun triage")

    request = review_requests(previous)
    if request["snapshot_sha256"] != previous["review_context_sha256"]:
        raise ContractError("Triage review request identity is invalid")
    original, policy, _, _, inputs, missing = load_context(
        **previous["context"],
        expected_assessment_sha256=previous["assessment_sha256"],
        expected_policy_sha256=previous["policy_sha256"],
    )
    # Includes model config and all other original inputs, not only the scene.
    unchanged(previous["input_hashes"])
    inputs.update(previous["input_hashes"])
    inputs[str(result_path)] = expected_triage_sha256
    owner = Path(previous["context"]["review_root"]).resolve(strict=True)
    path = _inside(owner, review_record)
    if not path.is_file() or path.stat().st_size > 1048576:
        raise ContractError("Human review must be a bounded file in the review root")
    inputs[str(path)] = sha(path)
    reviews = strict_json(path)
    Draft202012Validator(REVIEW).validate(reviews)
    if reviews["snapshot_sha256"] != request["snapshot_sha256"]:
        raise ContractError(
            "Human review is stale or belongs to another triage request"
        )
    decisions = _unique(reviews["reviews"], "item_id")
    requested = {item["item_id"] for item in request["items"]}
    if decisions.keys() - requested:
        raise ContractError("Human review cites an item outside this triage request")
    for decision in decisions.values():
        for item in decision["evidence"]:
            evidence = _inside(owner, item["path"])
            if not evidence.is_file() or evidence.stat().st_size > 8388608:
                raise ContractError("Human review evidence is missing or exceeds 8 MiB")
            observed = sha(evidence)
            if observed != item["sha256"]:
                raise ContractError("Human review evidence is stale")
            if str(evidence) in inputs and inputs[str(evidence)] != observed:
                raise ContractError("Human review evidence changed after assessment")
            inputs[str(evidence)] = observed

    output = Path(out).resolve()
    roots = [
        source,
        owner,
        Path(previous["context"]["bundle_root"]).resolve(),
        Path(previous["context"]["assessment"]).resolve().parent,
    ]
    if output.exists() or any(
        output.is_relative_to(root) or root.is_relative_to(output) for root in roots
    ):
        raise ContractError("Resolved output must be new and outside input roots")
    response = {
        "items": [
            row["model_recommendation"]
            for row in previous["items"]
            if row["model_recommendation"] is not None
        ]
    }
    rows = apply_policy(original, policy, response, missing, decisions)
    decision, code, action = combined_outcome(original["assessment_verdict"], rows, [])
    from collections import Counter

    result = deepcopy(previous)
    result.update(
        items=rows,
        counts=dict(Counter(row["policy_outcome"] for row in rows)),
        human_review_risk_counts=review_risk_counts(rows),
        decision=decision,
        exit_code=code,
        next_action=action,
        parent_triage_sha256=expected_triage_sha256,
        human_review_sha256=sha(path),
        input_hashes=inputs,
    )
    Draft202012Validator(RESULT_SCHEMA).validate(result)
    unchanged(inputs)
    model_request = strict_json(source / "model/request.json")
    supplied_hash = model_request.pop("request_sha256")
    if (
        supplied_hash != previous["request_sha256"]
        or digest_json(model_request) != supplied_hash
    ):
        raise ContractError("Original model request was modified")
    model_request["request_sha256"] = supplied_hash
    output.mkdir(parents=True)
    save(output / "triage-result.json", result)
    save(output / "assessment.json", original)
    save(output / "policy.json", policy)
    save(output / "review-requests.json", request)
    save(output / "human-review.json", reviews)
    (output / "model").mkdir()
    save(output / "model/request.json", model_request)
    _report(result, output)
    unchanged(inputs)
    save(
        output / "manifest.json",
        {
            "files": {
                str(p.relative_to(output)): sha(p)
                for p in sorted(output.rglob("*"))
                if p.is_file()
            }
        },
    )
    return result
