"""Risk buckets prioritize review without becoming approval or a safety claim."""

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator

from scene_acceptance.application import invoke
from scene_acceptance.application_schemas import SCHEMAS
from scene_acceptance.model import ContractError, sha, strict_json
from scene_acceptance.triage import apply_policy, combined_outcome, run_triage
from scene_acceptance.triage_review import resolve_triage
from scene_acceptance.triage_risk import DEFAULT_REVIEW_RISK_RUBRIC
from test_review import approve, save
from test_triage import case, kwargs

RUBRIC = {
    "low": "Limited, reversible consequence within this synthetic task.",
    "medium": "Could invalidate the intended use or require substantial rework.",
    "high": "Could have serious consequences if relied upon without specialist review.",
}


def configure(
    case, tmp_path, level="medium", recommendation="human_review_needed", missing=None
):
    """Use a deterministic adapter, never a real risk-assessment model."""
    policy = case[5]
    policy["schema_version"] = "1.1"
    policy.setdefault("review_risk_rubric", deepcopy(RUBRIC))
    args = kwargs(case, tmp_path)
    script = tmp_path / "risk_adapter.py"
    script.write_text("""import json,sys
request=json.load(sys.stdin)
control=json.loads(sys.argv[1])
rows=[]
for item in request['items']:
 rows.append(dict(item_id=item['id'],recommendation=control['recommendation'],
  reason='Synthetic transport control',possible_consequence='No real-world conclusion',
  missing_context=control['missing'],evidence_ids=[item['evidence_ids'][0]],
  model_policy_paraphrase=item['policy']['reason'],review_risk=control['level'],
  risk_reason='Synthetic rubric-based reason' if control['level'] is not None else None))
print(json.dumps(dict(schema_version='1.2',request_sha256=request['request_sha256'],
 items=rows,limitations=['Deterministic test adapter; no model-quality evidence'])))
""")
    save(
        args["triage_config"],
        dict(
            driver="json-cli",
            executable=sys.executable,
            args=[
                str(script),
                json.dumps(
                    dict(
                        level=level,
                        recommendation=recommendation,
                        missing=missing or [],
                    )
                ),
            ],
            model="deterministic-risk-test",
            effort="none",
            timeout_seconds=2,
        ),
    )
    return args


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_risk_levels_stay_under_review_and_reach_api_report_and_requests(
    case, tmp_path, level
):
    args = configure(case, tmp_path, level)
    envelope = invoke("triage", **args)
    result = envelope["data"]
    assert envelope["exit_code"] == 3 and result["next_action"] == "review_finding"
    assert result["items"][0]["policy_outcome"] == "human_review_needed"
    assert result["items"][0]["review_risk"] == level
    assert result["items"][0]["review_risk_basis"] == "model"
    assert result["human_review_risk_counts"][level] == 1
    assert sum(result["human_review_risk_counts"].values()) == 1
    request = strict_json(args["out"] / "review-requests.json")
    assert request["items"][0]["review_risk"] == level
    html = (args["out"] / "report.html").read_text()
    assert f"<li>{level.title()}: 1</li>" in html
    assert "Low still requires review" in html
    assert "Review-risk rubric" in html and "Owner override" in html
    assert result["review_risk_rubric"] == RUBRIC
    assert result["review_risk_rubric_source"] == "owner"
    request = strict_json(args["out"] / "model/request.json")
    assert request["review_risk_rubric"] == RUBRIC
    assert request["review_risk_rubric_source"] == "owner"


@pytest.mark.parametrize(
    "recommendation,level,expected",
    [
        ("human_review_needed", "low", "high"),
        ("human_review_needed", "medium", "high"),
        ("routine_handling", None, "high"),
    ],
)
def test_owner_minimum_cannot_be_downgraded(
    case, tmp_path, recommendation, level, expected
):
    case[5]["items"][0].update(mandatory_human_review=True, minimum_review_risk="high")
    result = run_triage(**configure(case, tmp_path, level, recommendation))
    row = result["items"][0]
    assert row["model_recommendation"]["review_risk"] == level
    assert (
        row["review_risk"] == expected and row["review_risk_basis"] == "owner_minimum"
    )
    assert result["exit_code"] == 3


def test_model_can_escalate_above_owner_minimum(case, tmp_path):
    case[5]["items"][0].update(mandatory_human_review=True, minimum_review_risk="low")
    result = run_triage(**configure(case, tmp_path, "high"))
    assert result["items"][0]["review_risk"] == "high"
    assert result["items"][0]["review_risk_basis"] == "model"


@pytest.mark.parametrize("recommendation", ["routine_handling", "insufficient_context"])
def test_other_outcomes_have_no_risk_subbucket(case, tmp_path, recommendation):
    result = run_triage(**configure(case, tmp_path, None, recommendation))
    assert result["items"][0]["review_risk"] is None
    assert result["items"][0]["review_risk_basis"] == "not_applicable"
    assert sum(result["human_review_risk_counts"].values()) == 0
    assert result["exit_code"] == (0 if recommendation == "routine_handling" else 3)


@pytest.mark.parametrize("recommendation", ["routine_handling", "insufficient_context"])
def test_model_cannot_attach_low_risk_to_nonreview_outcome(
    case, tmp_path, recommendation
):
    result = run_triage(**configure(case, tmp_path, "low", recommendation))
    assert result["exit_code"] == 4
    assert result["items"][0]["model_recommendation"] is None


def test_missing_context_is_unrated_not_low(case, tmp_path):
    result = run_triage(
        **configure(case, tmp_path, None, missing=["Unspecified intended use"])
    )
    assert result["exit_code"] == 3
    assert result["human_review_risk_counts"]["unrated"] == 1
    assert result["items"][0]["review_risk"] is None


def test_consequence_grade_can_coexist_with_a_missing_measurement(case, tmp_path):
    result = run_triage(
        **configure(
            case,
            tmp_path,
            "high",
            missing=["Physical parameter still needs measurement"],
        )
    )
    assert result["exit_code"] == 3
    assert result["human_review_risk_counts"]["high"] == 1
    assert result["items"][0]["model_recommendation"]["missing_context"]


def test_legacy_adapter_stays_unrated_with_new_rubric(case, tmp_path):
    case[5].update(schema_version="1.1", review_risk_rubric=deepcopy(RUBRIC))
    result = run_triage(**kwargs(case, tmp_path, "human_review_needed"))
    assert result["exit_code"] == 3
    assert result["human_review_risk_counts"]["unrated"] == 1
    assert result["items"][0]["model_recommendation"]["review_risk"] is None


def test_default_rubric_does_not_invent_a_grade_when_context_is_missing(case, tmp_path):
    args = configure(case, tmp_path, None, missing=["Intended duty is unknown"])
    case[5].pop("review_risk_rubric")
    save(args["policy"], case[5])
    args["expected_policy_sha256"] = sha(args["policy"])
    result = run_triage(**args)
    assert (
        result["exit_code"] == 3 and result["human_review_risk_counts"]["unrated"] == 1
    )


@pytest.mark.parametrize("level", ["low", "medium", "high"])
@pytest.mark.parametrize("policy_version", ["1.0", "1.1"])
def test_defaults_reach_model_api_and_report_without_rewriting_policy(
    case, tmp_path, level, policy_version
):
    args = configure(case, tmp_path, level)
    case[5].pop("review_risk_rubric")
    case[5]["schema_version"] = policy_version
    save(args["policy"], case[5])
    args["expected_policy_sha256"] = sha(args["policy"])
    original_bytes = args["policy"].read_bytes()
    envelope = invoke("triage", **args)
    result = envelope["data"]
    assert result["schema_version"] == "1.3"
    assert envelope["exit_code"] == 3
    assert result["review_risk_rubric_source"] == "built_in"
    assert result["review_risk_rubric"] == DEFAULT_REVIEW_RISK_RUBRIC
    assert result["human_review_risk_counts"][level] == 1
    assert result["items"][0]["review_risk"] == level
    assert args["policy"].read_bytes() == original_bytes
    assert strict_json(args["out"] / "policy.json") == case[5]
    request = strict_json(args["out"] / "model/request.json")
    assert request["policy"] == case[5]
    assert request["review_risk_rubric"] == DEFAULT_REVIEW_RISK_RUBRIC
    assert request["review_risk_rubric_source"] == "built_in"
    html = (args["out"] / "report.html").read_text()
    assert "Built-in defaults" in html
    assert DEFAULT_REVIEW_RISK_RUBRIC["high"] in html
    assert "Low still requires review" in html
    assert (
        strict_json(args["out"] / "review-requests.json")["items"][0]["review_risk"]
        == level
    )


@pytest.mark.parametrize(
    "recommendation,level", [("human_review_needed", "low"), ("routine_handling", None)]
)
def test_owner_minimum_works_with_default_definitions(
    case, tmp_path, recommendation, level
):
    args = configure(case, tmp_path, level, recommendation=recommendation)
    case[5].pop("review_risk_rubric")
    case[5]["items"][0].update(mandatory_human_review=True, minimum_review_risk="high")
    save(args["policy"], case[5])
    args["expected_policy_sha256"] = sha(args["policy"])
    result = run_triage(**args)
    assert result["exit_code"] == 3
    assert result["review_risk_rubric_source"] == "built_in"
    assert result["items"][0]["review_risk"] == "high"
    assert result["items"][0]["review_risk_basis"] == "owner_minimum"


def test_legacy_response_with_defaults_still_stays_unrated(case, tmp_path):
    result = run_triage(**kwargs(case, tmp_path, "human_review_needed"))
    assert result["exit_code"] == 3
    assert result["review_risk_rubric_source"] == "built_in"
    assert result["human_review_risk_counts"]["unrated"] == 1


@pytest.mark.parametrize(
    "invalid",
    [
        "unknown_level",
        "optional_review",
        "partial_rubric",
        "empty_definition",
        "null_rubric",
    ],
)
def test_bad_owner_policy_fails_before_model(case, tmp_path, invalid):
    args = configure(case, tmp_path)
    rule = case[5]["items"][0]
    rule.update(mandatory_human_review=True, minimum_review_risk="high")
    if invalid == "unknown_level":
        rule["minimum_review_risk"] = "critical"
    if invalid == "optional_review":
        rule["mandatory_human_review"] = False
    if invalid == "partial_rubric":
        case[5]["review_risk_rubric"].pop("high")
    if invalid == "empty_definition":
        case[5]["review_risk_rubric"]["high"] = " "
    if invalid == "null_rubric":
        case[5]["review_risk_rubric"] = None
    save(args["policy"], case[5])
    args["expected_policy_sha256"] = sha(args["policy"])
    result = invoke("triage", **args)
    assert result["exit_code"] == 4
    assert not (args["out"] / "model").exists()


@pytest.mark.parametrize("level", ["critical", 0, "LOW"])
def test_invalid_model_grade_is_a_contract_error(case, tmp_path, level):
    assert run_triage(**configure(case, tmp_path, level))["exit_code"] == 4


def test_complete_context_needs_a_reasoned_grade_in_new_response(case, tmp_path):
    assert run_triage(**configure(case, tmp_path, None))["exit_code"] == 4


@pytest.mark.parametrize("status", ["UNKNOWN", "ERROR"])
def test_model_grade_cannot_resolve_an_unknown_or_error_measurement(
    case, tmp_path, status
):
    args = configure(case, tmp_path, "high")
    original = deepcopy(case[3])
    original["items"][0]["status"] = status
    save(args["assessment"], original)
    args["expected_assessment_sha256"] = sha(args["assessment"])
    result = run_triage(**args)
    assert result["exit_code"] == 3 and result["next_action"] == "provide_evidence"
    assert result["items"][0]["model_recommendation"]["review_risk"] == "high"
    assert result["items"][0]["review_risk"] is None


def test_selected_missing_source_keeps_its_evidence_gate(case, tmp_path):
    case[5]["evidence"] = [
        dict(
            id="missing",
            path="absent.txt",
            sha256="0" * 64,
            kind="text",
            description="Required evidence",
        )
    ]
    case[5]["items"][0]["evidence_ids"] = ["missing"]
    result = run_triage(**configure(case, tmp_path, "high"))
    assert result["exit_code"] == 3 and result["next_action"] == "provide_evidence"
    assert result["items"][0]["model_recommendation"]["review_risk"] == "high"
    assert result["items"][0]["review_risk"] is None


def test_review_queue_counts_selected_items_by_applied_risk(case):
    from scene_acceptance.triage_risk import review_risk_counts

    assessment = deepcopy(case[3])
    policy = deepcopy(case[5])
    source, rule = deepcopy(assessment["items"][0]), deepcopy(policy["items"][0])
    assessment["items"], policy["items"] = [], []
    policy["review_risk_rubric"] = RUBRIC
    opinions = []
    for level in ["low", "medium", "high", None]:
        key = level or "no-grade"
        assessment["items"].append(dict(source, id=key))
        policy["items"].append(dict(rule, item_id=key))
        opinions.append(
            dict(
                item_id=key,
                recommendation="human_review_needed",
                review_risk=level,
                risk_reason="Test only",
                missing_context=[],
            )
        )
    rows = apply_policy(assessment, policy, {"items": opinions}, set())
    assert review_risk_counts(rows) == {"low": 1, "medium": 1, "high": 1, "unrated": 1}
    assert combined_outcome("ACCEPT_FOR_DECLARED_SCOPE", rows, []) == (
        "NEEDS_REVIEW",
        3,
        "review_finding",
    )


@pytest.mark.parametrize("with_override", [False, True])
@pytest.mark.parametrize("status", ["approved", "rejected"])
def test_human_resolution_preserves_model_grade_and_updates_queue(
    case, tmp_path, status, with_override
):
    case[5]["items"][0].update(mandatory_human_review=True, minimum_review_risk="high")
    args = configure(case, tmp_path, "low")
    if not with_override:
        case[5].pop("review_risk_rubric")
        save(args["policy"], case[5])
        args["expected_policy_sha256"] = sha(args["policy"])
    before = run_triage(**args)
    approve(
        case[1],
        {"snapshot_sha256": before["review_context_sha256"]},
        {"material-binding": status},
    )
    resolved = resolve_triage(
        triage_run=args["out"],
        expected_triage_sha256=sha(args["out"] / "triage-result.json"),
        review_record="reviews.json",
        out=tmp_path / "resolved",
    )
    assert (
        resolved["items"][0]["model_recommendation"]
        == before["items"][0]["model_recommendation"]
    )
    assert resolved["items"][0]["policy_rule"]["minimum_review_risk"] == "high"
    assert resolved["review_risk_rubric_source"] == (
        "owner" if with_override else "built_in"
    )
    assert resolved["exit_code"] == (0 if status == "approved" else 3)
    assert resolved["human_review_risk_counts"]["high"] == (
        0 if status == "approved" else 1
    )


@pytest.mark.parametrize("field", ["rubric", "minimum", "override_defaults"])
def test_changed_risk_policy_invalidates_human_decision(case, tmp_path, field):
    case[5]["items"][0].update(mandatory_human_review=True, minimum_review_risk="high")
    args = configure(case, tmp_path)
    if field == "override_defaults":
        case[5].pop("review_risk_rubric")
        save(args["policy"], case[5])
        args["expected_policy_sha256"] = sha(args["policy"])
    result = run_triage(**args)
    approve(
        case[1],
        {"snapshot_sha256": result["review_context_sha256"]},
        {"material-binding": "approved"},
    )
    if field == "override_defaults":
        case[5]["review_risk_rubric"] = deepcopy(RUBRIC)
    elif field == "rubric":
        case[5]["review_risk_rubric"]["high"] += " Changed."
    else:
        case[5]["items"][0]["minimum_review_risk"] = "medium"
    save(args["policy"], case[5])
    with pytest.raises(ContractError, match="hash"):
        resolve_triage(
            triage_run=args["out"],
            expected_triage_sha256=sha(args["out"] / "triage-result.json"),
            review_record="reviews.json",
            out=tmp_path / "resolved",
        )


def test_low_risk_never_clears_a_required_failure(case):
    assessment = deepcopy(case[3])
    assessment["items"][0]["status"] = "FAIL"
    policy = deepcopy(case[5])
    policy["review_risk_rubric"] = RUBRIC
    opinion = dict(
        item_id="material-binding",
        recommendation="human_review_needed",
        review_risk="low",
        risk_reason="Synthetic only",
        missing_context=[],
    )
    rows = apply_policy(
        assessment,
        policy,
        {"items": [opinion]},
        set(),
        {"material-binding": {"status": "approved"}},
    )
    assert rows[0]["policy_outcome"] == "human_review_needed"
    assert combined_outcome("REJECT", rows, [])[1] == 2


def test_legacy_schema_contracts_and_new_discovery_remain_available():
    root = Path(__file__).resolve().parents[1] / "src/scene_acceptance/schemas"
    for name in [
        "triage-policy-v1",
        "triage-response-v1",
        "triage-response-v1.1",
        "triage-result-v1",
        "triage-result-v1.1",
        "triage-policy-v1.1",
        "triage-response-v1.2",
        "triage-result-v1.2",
        "triage-result-v1.3",
    ]:
        assert strict_json(root / (name + ".schema.json")) == SCHEMAS[name]
        Draft202012Validator.check_schema(SCHEMAS[name])
