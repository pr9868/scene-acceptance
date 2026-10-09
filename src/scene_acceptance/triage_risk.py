"""Qualitative review-risk routing with overridable default definitions."""

from typing import Any

RISK_LEVELS = ["low", "medium", "high"]
DEFAULT_REVIEW_RISK_RUBRIC = {
    "low": "Limited, reversible impact; a brief owner check can settle the choice.",
    "medium": "Could invalidate the intended use or require substantial rework; review the basis before relying on it.",
    "high": "Could have serious consequences for physical operation or a consequential decision; require qualified domain review.",
}


def risk_rubric(policy: dict[str, Any]) -> tuple[dict[str, str], str]:
    """Return the active definitions and source without modifying caller policy."""
    if "review_risk_rubric" in policy:
        return dict(policy["review_risk_rubric"]), "owner"
    return dict(DEFAULT_REVIEW_RISK_RUBRIC), "built_in"


def review_risk(
    policy: dict[str, Any],
    rule: dict[str, Any],
    opinion: dict[str, Any] | None,
    outcome: str,
) -> tuple[str | None, str, str | None]:
    """Keep risk beneath pending human review; never change its release gate."""
    if outcome != "human_review_needed":
        return None, "not_applicable", None
    floor = rule.get("minimum_review_risk")
    suggested = None
    if opinion and opinion["recommendation"] == "human_review_needed":
        suggested = opinion.get("review_risk")
    if floor and (
        suggested is None or RISK_LEVELS.index(floor) >= RISK_LEVELS.index(suggested)
    ):
        return (
            floor,
            "owner_minimum",
            f"Owner requires at least {floor} review risk: {rule['reason']}",
        )
    if suggested:
        return suggested, "model", opinion["risk_reason"]
    return None, "unrated", "No supported model level or owner minimum is available."


def review_risk_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count only items still in the human-review queue, including ungraded ones."""
    counts = dict.fromkeys([*RISK_LEVELS, "unrated"], 0)
    for row in rows:
        if row["policy_outcome"] == "human_review_needed":
            counts[row["review_risk"] or "unrated"] += 1
    return counts
