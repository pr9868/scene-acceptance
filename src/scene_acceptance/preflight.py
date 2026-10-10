"""Deterministic prerequisite checks, never acceptance measurements or approval."""

from copy import deepcopy
from types import SimpleNamespace
from jsonschema import Draft202012Validator
from .model import ContractError, MissingEvidence


def geometry(ctx, parameters):
    from .geometry_access import read_geometry
    from .subjects import resolve

    paths = parameters.get("obstacles")
    if "selector" in parameters:
        selected = resolve(ctx.artifact.stage, parameters["selector"])
        paths = selected["paths"] + selected["missing"] + selected["unavailable"]
    if paths is None:
        paths = [parameters[k] for k in ("a", "b") if k in parameters]
    gaps = []
    if "selector" in parameters and selected.get("capacity_exhausted"):
        gaps.append(
            dict(subject="selection", reason="Subject selection capacity exhausted")
        )
    for path in paths:
        try:
            read_geometry(
                ctx.artifact.stage,
                path,
                parameters.get("time_s", parameters.get("interval_s", [0])[0]),
                parameters.get("representation", "closed-solids") == "closed-solids",
                approximation_m=parameters.get("approximation_m", 0.001),
                allow_implicit="interval_s" not in parameters,
            )
        except MissingEvidence as exc:
            gaps.append(dict(subject=path, reason=str(exc)))
    if not paths:
        gaps.append(dict(subject="selection", reason="No selected subjects"))
    if "interval_s" in parameters:
        from .continuous_motion import affine_times

        try:
            affine_times(ctx.artifact.stage, paths, parameters["interval_s"])
        except MissingEvidence as exc:
            gaps.append(dict(subject="motion interval", reason=str(exc)))
    return gaps


def bounds(ctx, parameters):
    from .brief_measurements import world_bounds

    try:
        world_bounds(ctx.artifact.stage, parameters["path"], parameters["time_code"])
        # An absent required subject is a measurable failure, not a prerequisite gap.
        return []
    except MissingEvidence as exc:
        return [dict(subject=parameters["path"], reason=str(exc))]


def checks(artifact, selected, registry=None):
    from .packs import default_registry

    registry = registry or default_registry(selected={x["pack"] for x in selected})
    ctx = SimpleNamespace(artifact=artifact, bundle=artifact.bundle, sources=[])
    rows = []
    for check in selected:
        spec = registry.get(check["pack"]).checks[check["check"]]
        Draft202012Validator(spec.parameters).validate(check["parameters"])
        if spec.preflight is None:
            rows.append(
                dict(
                    id=check["id"],
                    status="not_available",
                    gaps=[],
                    reason="Provider has no executable prerequisite declaration",
                )
            )
            continue
        try:
            gaps = spec.preflight(ctx, deepcopy(check["parameters"]))
        except MissingEvidence as exc:
            gaps = [dict(subject="selection", reason=str(exc))]
        rows.append(
            dict(
                id=check["id"],
                status="unresolved" if gaps else "ready",
                gaps=gaps,
                reason="Prerequisites only; no acceptance claim",
            )
        )
    if not artifact.unchanged():
        raise ContractError("Preflight provider mutated admitted inputs")
    return dict(
        schema_version="1.0",
        status=(
            "unresolved"
            if any(r["status"] == "unresolved" for r in rows)
            else (
                "ready_with_limits"
                if any(r["status"] == "not_available" for r in rows)
                else "ready"
            )
        ),
        checks=rows,
    )


def capture_budget(captures, budget):
    slots = {}
    for c in captures:
        # Sharing needs a matching declared framing, camera and capability plan.
        key = (
            c.get("sharing_group") or c["id"],
            c.get("camera_id"),
            c.get("projection"),
            c.get("view_role"),
            c.get("camera_guidance"),
            tuple(sorted(c.get("capabilities", []))),
            c.get("min_width"),
            c.get("min_height"),
        )
        slots.setdefault(key, set()).update(c["times_seconds"])
    count = sum(len(v) for v in slots.values())
    gap = f"Combined capture plan needs {count} planned image slots; available scene-image budget is {budget}"
    if count > budget:
        for c in captures:
            c.setdefault("feasibility_gaps", []).append(gap)
    return dict(
        status="unresolved" if count > budget else "planned",
        planned_image_slots=count,
        available_image_slots=budget,
        additional_slots_needed=max(0, count - budget),
        note="Planning compatibility is not visibility proof. Caller evidence must still establish each requested view.",
    )


def preparation_readiness(prerequisites, captures, requirements=()):
    """Readiness to proceed with a proposal, separate from scope/outcome approval."""
    blockers = [
        dict(kind="check_prerequisite", id=row["id"], gaps=row["gaps"])
        for row in prerequisites["checks"]
        if row["status"] == "unresolved"
    ]
    blockers.extend(
        dict(
            kind="capture_feasibility",
            id=c["id"],
            gaps=[dict(subject=c["id"], reason=g) for g in c["feasibility_gaps"]],
        )
        for c in captures
        if c.get("feasibility_gaps")
    )
    blockers.extend(
        dict(
            kind="requirement_mapping",
            id=r["id"],
            gaps=[
                dict(
                    subject=r["id"],
                    reason=r.get("basis", r.get("reason", "Unresolved mapping")),
                )
            ],
        )
        for r in requirements
        if r.get("evaluation_route", r.get("route")) in ("unresolved", "unsupported")
    )
    unchecked = [
        r["id"] for r in prerequisites["checks"] if r["status"] == "not_available"
    ]
    return dict(
        status=(
            "unresolved" if blockers else "ready_with_limits" if unchecked else "ready"
        ),
        ready_for_capture=not blockers,
        blockers=blockers,
        checks_without_preflight=unchecked,
        next_action="revise_preparation" if blockers else "review_scope_then_capture",
        diagnostic_checks_allowed=True,
        note="Prerequisites only. Owner scope approval and evidence validation remain separate; readiness is not acceptance.",
    )
