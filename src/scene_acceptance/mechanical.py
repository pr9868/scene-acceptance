"""Declared mechanical relationships; never infer joints or physical function."""

from pathlib import Path
import math
from pxr import Gf
from .builtin_packs import obj, TEXT, VEC3
from .continuous_motion import affine_times, matrix_at, connection
from .geometry_access import read_geometry
from .model import ContractError, MissingEvidence
from .observations import status_of
from .packs import CheckSpec, Outcome, Pack

ANCHOR = obj({"path": TEXT, "local_point": VEC3})
INTERVAL = {
    "type": "array",
    "items": {"type": "number", "minimum": 0},
    "minItems": 2,
    "maxItems": 2,
}
POSITIVE = {"type": "number", "exclusiveMinimum": 0}


def _axis(p):
    axis = Gf.Vec3d(*p["axis_world"])
    if not math.isfinite(axis.GetLength()) or abs(axis.GetLength() - 1) > 1e-9:
        raise ContractError("axis_world must be a unit vector")
    return axis


def prerequisites(ctx, p):
    paths = [p[k]["path"] if isinstance(p[k], dict) else p[k] for k in ("a", "b")]
    try:
        affine_times(ctx.artifact.stage, paths, p["interval_s"])
        if "axis_world" in p:
            _axis(p)
        if isinstance(p["a"], str):
            for path in paths:
                read_geometry(ctx.artifact.stage, path, p["interval_s"][0], False)
    except MissingEvidence as exc:
        return [dict(subject="declared relationship", reason=str(exc))]
    return []


def sliding(ctx, p):
    """Bound lateral separation and signed travel at every affine knot."""
    if p["minimum_travel_m"] > p["maximum_travel_m"]:
        raise ContractError("Travel range must increase")
    stage = ctx.artifact.stage
    axis = _axis(p)
    clock, units, times = affine_times(
        stage, [p[k]["path"] for k in ("a", "b")], p["interval_s"]
    )
    rows = []
    margin = p["numeric_margin_m"]
    for t in times:
        points = [
            matrix_at(stage, p[k]["path"], clock, t).Transform(
                Gf.Vec3d(*p[k]["local_point"])
            )
            * units
            for k in ("a", "b")
        ]
        offset = points[1] - points[0]
        travel = Gf.Dot(offset, axis)
        lateral = (offset - travel * axis).GetLength()
        fail = (
            lateral - margin > p["max_lateral_m"]
            or travel + margin < p["minimum_travel_m"]
            or travel - margin > p["maximum_travel_m"]
        )
        passed = (
            lateral + margin <= p["max_lateral_m"]
            and travel - margin >= p["minimum_travel_m"]
            and travel + margin <= p["maximum_travel_m"]
        )
        rows.append(
            dict(
                status="FAIL" if fail else "PASS" if passed else "UNKNOWN",
                time_s=t,
                lateral_m=lateral,
                travel_m=travel,
            )
        )
    return Outcome(
        status_of(rows),
        "Bounded declared sliding anchors and signed travel.",
        dict(
            findings=rows,
            subjects=[p[k]["path"] for k in ("a", "b")],
            interval_s=p["interval_s"],
            expected=dict(
                max_lateral_m=p["max_lateral_m"],
                minimum_travel_m=p["minimum_travel_m"],
                maximum_travel_m=p["maximum_travel_m"],
            ),
            coverage="Whole interval for affine translation; no inferred joint, collision or load-bearing claim.",
        ),
    )


def engagement(ctx, p):
    """Projected overlap is concave between affine knots; its minimum is at a knot."""
    stage = ctx.artifact.stage
    axis = _axis(p)
    _, _, times = affine_times(stage, [p["a"], p["b"]], p["interval_s"])
    rows = []
    for t in times:
        geometry = [
            read_geometry(
                stage, p[k], t, False, approximation_m=p.get("approximation_m", 0.001)
            )
            for k in ("a", "b")
        ]
        intervals = []
        for g in geometry:
            values = [Gf.Dot(v, axis) for tri in g.triangles for v in tri]
            intervals.append((min(values), max(values)))
        overlap = min(v[1] for v in intervals) - max(v[0] for v in intervals)
        error = sum(g.error_m for g in geometry) + p["numeric_margin_m"]
        status = (
            "FAIL"
            if overlap + error < p["minimum_overlap_m"]
            else "PASS" if overlap - error >= p["minimum_overlap_m"] else "UNKNOWN"
        )
        rows.append(
            dict(
                time_s=t,
                status=status,
                overlap_m=overlap,
                error_bound_m=error,
                expected_minimum_m=p["minimum_overlap_m"],
            )
        )
    return Outcome(
        status_of(rows),
        "Bounded projected engagement of the two declared parts.",
        dict(
            findings=rows,
            subjects=[p["a"], p["b"]],
            interval_s=p["interval_s"],
            coverage="One-dimensional projection over affine translation. Overlap is not physical contact; combine with lateral alignment and clearance checks.",
        ),
    )


def mechanical_pack():
    common = {"interval_s": INTERVAL, "numeric_margin_m": POSITIVE}
    anchor = {**common, "a": ANCHOR, "b": ANCHOR}
    return Pack(
        "mechanical.relationships",
        "1.0.0",
        "Owner-declared attachments, sliding travel and projected engagement",
        {
            "attachment": CheckSpec(
                connection,
                obj({**anchor, "max_gap_m": {"type": "number", "minimum": 0}}),
                "Bound declared anchor separation",
                "Whole admitted translation interval",
                capabilities={"time": "piecewise-affine-translation"},
                preflight=prerequisites,
            ),
            "sliding": CheckSpec(
                sliding,
                obj(
                    {
                        **anchor,
                        "axis_world": VEC3,
                        "max_lateral_m": POSITIVE,
                        "minimum_travel_m": {"type": "number"},
                        "maximum_travel_m": {"type": "number"},
                    }
                ),
                "Bound lateral alignment and signed travel",
                "Whole admitted translation interval",
                capabilities={"time": "piecewise-affine-translation"},
                preflight=prerequisites,
            ),
            "engagement": CheckSpec(
                engagement,
                obj(
                    {
                        **common,
                        "a": TEXT,
                        "b": TEXT,
                        "axis_world": VEC3,
                        "minimum_overlap_m": POSITIVE,
                    }
                ),
                "Bound minimum projected overlap",
                "Whole admitted translation interval; projection only",
                capabilities={"time": "piecewise-affine-translation"},
                preflight=prerequisites,
            ),
        },
        tuple(
            str(Path(__file__).with_name(n))
            for n in (
                "mechanical.py",
                "continuous_motion.py",
                "geometry_access.py",
                "observations.py",
                "motion_timing.py",
            )
        ),
        ("usd-core",),
    )
