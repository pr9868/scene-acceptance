"""Bounded repair of preparation proposals, without changing their obligations."""

from copy import deepcopy
import json
from .model import ContractError
from .preflight import checks as preflight_checks, capture_budget, preparation_readiness


def capture_feasibility(captures, caps, reference_count):
    budget = min(caps["max_images"], 12 - reference_count)
    for capture in captures:
        gaps = []
        if set(capture["capabilities"]) - set(caps["capabilities"]):
            gaps.append("Caller lacks requested capture capability")
        if (
            capture["min_width"] > caps["max_width"]
            or capture["min_height"] > caps["max_height"]
        ):
            gaps.append("Requested resolution exceeds caller capability")
        if (
            capture["evidence_kind"] == "motion_frames"
            and len(capture["times_seconds"]) < 3
        ):
            gaps.append("Scene has no positive authored motion interval")
        if len(capture["times_seconds"]) > budget:
            gaps.append("This request exceeds the declared image budget")
        capture["feasibility_gaps"] = gaps
    return budget, capture_budget(captures, budget)


def preview(interpretation, request, artifact, general_captures, reference_count):
    catalog = {c["id"]: c for c in request["allowed_checks"]}
    captures = deepcopy(general_captures)
    checks = []
    for r in interpretation["requirements"]:
        for c in r["checks"]:
            kind = catalog[c["type_id"]]
            checks.append(
                dict(
                    id=c["id"],
                    pack=kind["pack"],
                    check=kind["check"],
                    parameters=json.loads(c["parameters_json"]),
                )
            )
        if r["visual"]:
            captures.extend(
                dict(
                    c,
                    requirement_ids=["brief." + r["id"]],
                    evidence_kind=r["visual"]["evidence_kind"],
                )
                for c in r["visual"]["captures"]
            )
    prerequisites = preflight_checks(artifact, checks)
    _, budget = capture_feasibility(
        captures, request["capture_capabilities"], reference_count
    )
    return dict(
        prerequisites=prerequisites,
        capture_budget=budget,
        captures=captures,
        readiness=preparation_readiness(
            prerequisites, captures, interpretation["requirements"]
        ),
    )


def validate_revision(previous, proposed):
    """Keep policy fixed. Schema/source validation is performed separately."""
    old = {r["id"]: r for r in previous["requirements"]}
    new = {r["id"]: r for r in proposed["requirements"]}
    if old.keys() != new.keys():
        raise ContractError("Plan revision must retain every requirement ID")
    for rid, before in old.items():
        after = new[rid]
        for key in ("id", "statement", "source_ids", "quotes", "route", "area"):
            if before[key] != after[key]:
                raise ContractError(f"Plan revision changed requirement {rid}: {key}")
        checks = {c["id"]: c for c in before["checks"]}
        revised = {c["id"]: c for c in after["checks"]}
        if checks.keys() != revised.keys():
            raise ContractError(f"Plan revision changed checks for {rid}")
        for cid, check in checks.items():
            changed = revised[cid]
            if check["type_id"] != changed["type_id"]:
                raise ContractError(f"Plan revision changed check type for {cid}")
            p, q = json.loads(check["parameters_json"]), json.loads(
                changed["parameters_json"]
            )
            if p == q:
                continue
            # An exact root replaces an incorrectly bound aggregate with all of
            # its geometric descendants. No subset, exclusion or tolerance edit.
            obstacles = p.pop("obstacles", None)
            selector = q.pop("selector", None)
            if not (
                obstacles
                and len(obstacles) == 1
                and selector == {"root": obstacles[0]}
                and p == q
            ):
                raise ContractError(
                    f"Plan revision changed check policy for {cid}; only an exact obstacle root may become a full subtree selector"
                )
        a, b = deepcopy(before["visual"]), deepcopy(after["visual"])
        if a is None or b is None:
            if a != b:
                raise ContractError(f"Plan revision changed visual route for {rid}")
            continue
        ca, cb = a.pop("captures"), b.pop("captures")
        if a != b or {c["id"] for c in ca} != {c["id"] for c in cb}:
            raise ContractError(f"Plan revision changed visual requirements for {rid}")
        updated = {c["id"]: c for c in cb}
        for capture in ca:
            other = updated[capture["id"]]
            for key in ("camera_id", "projection"):
                if capture.get(key) is not None and capture[key] != other.get(key):
                    raise ContractError(
                        f"Plan revision changed declared {key} for {capture['id']}"
                    )
            for c in (capture, other):
                # Fill unspecified camera metadata or propose sharing without
                # changing framing instructions or any declared camera choice.
                for key in (
                    "sharing_group",
                    "camera_id",
                    "projection",
                ):
                    c.pop(key, None)
            if capture != other:
                raise ContractError(f"Plan revision weakened capture {capture['id']}")
    return proposed
