"""Whole-interval guarantees for explicitly admitted piecewise affine motion."""

from pathlib import Path
import math

from pxr import Gf, Usd, UsdGeom

from .builtin_packs import obj, TEXT, VEC3
from .model import ContractError, MissingEvidence
from .motion_timing import elapsed_time_code, read_clock
from .packs import CheckSpec, Outcome, Pack


def affine_times(stage, paths, interval):
    """Prove the selected world transforms have constant linear parts.

    Linear USD translation samples with static other ops remain affine under
    composition with static ancestor transforms. Arbitrary rotation/scale
    samples, matrix interpolation and runtime controllers are not admitted.
    """
    clock = read_clock(stage)
    start, end = interval
    if not math.isfinite(start + end) or start >= end:
        raise ContractError("Motion interval must be finite and increasing")
    elapsed_time_code(clock, start)
    elapsed_time_code(clock, end)
    if stage.GetInterpolationType() != Usd.InterpolationTypeLinear:
        raise MissingEvidence("Continuous proof requires linear USD interpolation")
    times = {start, end}
    for path in paths:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsA(UsdGeom.Xformable):
            raise MissingEvidence("Required transformable path is missing: " + path)
        while prim and not prim.IsPseudoRoot():
            if prim.IsA(UsdGeom.Xformable):
                xf = UsdGeom.Xformable(prim)
                for op in xf.GetOrderedXformOps():
                    # Splines can vary between endpoints while GetTimeSamples()
                    # is empty. The knot proof below covers USD samples only.
                    if op.GetAttr().HasSpline():
                        raise MissingEvidence(
                            "Continuous proof does not support spline animation: "
                            + str(op.GetAttr().GetPath())
                        )
                    samples = op.GetAttr().GetTimeSamples()
                    if samples and op.GetOpType() not in (
                        UsdGeom.XformOp.TypeTranslate,
                        UsdGeom.XformOp.TypeTranslateX,
                        UsdGeom.XformOp.TypeTranslateY,
                        UsdGeom.XformOp.TypeTranslateZ,
                    ):
                        raise MissingEvidence(
                            "Continuous proof admits animated translations only: "
                            + str(op.GetAttr().GetPath())
                        )
                    for sample in samples:
                        elapsed = (sample - clock["start_time_code"]) / clock[
                            "time_codes_per_second"
                        ]
                        if start <= elapsed <= end:
                            times.add(elapsed)
                    if len(times) > 4097 or len(samples) > 4097:
                        raise MissingEvidence("Continuous proof exceeds 4,097 knots")
                if xf.GetResetXformStack():
                    break
            prim = prim.GetParent()
    units = UsdGeom.GetStageMetersPerUnit(stage)
    if (
        not stage.HasAuthoredMetadata("metersPerUnit")
        or not math.isfinite(units)
        or units <= 0
    ):
        raise MissingEvidence("Continuous proof requires authored positive stage units")
    return clock, units, sorted(times)


def matrix_at(stage, path, clock, seconds):
    matrix = UsdGeom.XformCache(
        Usd.TimeCode(elapsed_time_code(clock, seconds))
    ).GetLocalToWorldTransform(stage.GetPrimAtPath(path))
    if (
        not all(math.isfinite(x) for row in matrix for x in row)
        or any(abs(matrix[i][3]) > 1e-12 for i in range(3))
        or abs(matrix[3][3] - 1) > 1e-12
        or abs(matrix.GetDeterminant()) < 1e-15
    ):
        raise MissingEvidence("Non-finite, singular or projective transform")
    return matrix


def connection(ctx, params):
    stage = ctx.artifact.stage
    clock, units, times = affine_times(
        stage, [params[k]["path"] for k in ("a", "b")], params["interval_s"]
    )
    rows = []
    for time in times:
        points = [
            matrix_at(stage, params[k]["path"], clock, time).Transform(
                Gf.Vec3d(*params[k]["local_point"])
            )
            * units
            for k in ("a", "b")
        ]
        gap = (points[0] - points[1]).GetLength()
        if not math.isfinite(gap):
            raise MissingEvidence("Non-finite world-space distance")
        rows.append(
            dict(elapsed_s=time, gap_m=gap, a_m=list(points[0]), b_m=list(points[1]))
        )
    maximum = max(row["gap_m"] for row in rows)
    margin = params["numeric_margin_m"]
    bound = math.nextafter(maximum + margin, math.inf)
    status = (
        "FAIL"
        if maximum - margin > params["max_gap_m"]
        else "PASS" if bound <= params["max_gap_m"] else "UNKNOWN"
    )
    return Outcome(
        status,
        "The norm of an affine relative position is convex; each segment reaches its maximum at a knot.",
        dict(
            knots=rows,
            interval_s=params["interval_s"],
            upper_bound_m=bound,
            numeric_margin_m=margin,
            max_gap_m=params["max_gap_m"],
            clock=clock,
            coverage="Whole interval for saved piecewise-linear translations and static other transforms. The caller must choose a numerical margin suitable for coordinate magnitude; no runtime physics, arbitrary rotations or formal floating-point certification.",
        ),
    )


def continuous_pack():
    return Pack(
        "motion.continuous",
        "1.0.1",
        "Continuous connection bound for saved affine translation paths",
        {
            "connection": CheckSpec(
                connection,
                obj(
                    {
                        "a": obj({"path": TEXT, "local_point": VEC3}),
                        "b": obj({"path": TEXT, "local_point": VEC3}),
                        "interval_s": {
                            "type": "array",
                            "items": {"type": "number", "minimum": 0},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        "max_gap_m": {"type": "number", "minimum": 0},
                        "numeric_margin_m": {"type": "number", "exclusiveMinimum": 0},
                    }
                ),
                "Bound connection distance throughout an interval",
                "All segments of admitted saved translation animation",
                (
                    "Unsupported transform animation stays unknown. Caller-defined points are not inferred joints.",
                ),
            ),
        },
        (str(Path(__file__)), str(Path(__file__).with_name("motion_timing.py"))),
        ("usd-core",),
    )
