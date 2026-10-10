"""Owner-held typed values and relative movement; no inferred targets."""

import math
from pxr import Gf, Sdf, Usd, UsdGeom
from .builtin_packs import obj, TEXT, VEC3
from .packs import Outcome
from .model import ContractError, MissingEvidence

PARTIAL = {**VEC3, "items": {"type": ["number", "null"]}}
VALUE_SCHEMA = obj(
    dict(
        attribute=TEXT,
        expected={
            "anyOf": [{"type": "string"}, {"type": "boolean"}, {"type": "number"}, VEC3]
        },
        time_code={"type": "number"},
        tolerance={"type": "number", "minimum": 0},
        unit_scale={"type": "number", "exclusiveMinimum": 0},
        expected_encoding={"enum": ["raw", "srgb", "linear_rgb"]},
    ),
    required=["attribute", "expected", "time_code", "tolerance"],
)
RELATIVE_SCHEMA = obj(
    dict(
        path=TEXT,
        start_s={"type": "number", "minimum": 0},
        end_s={"type": "number", "minimum": 0},
        delta_m=PARTIAL,
        tolerance_m={"type": "number", "minimum": 0},
    ),
    required=["path", "start_s", "end_s", "delta_m", "tolerance_m"],
)


def attribute_value(ctx, p):
    path = Sdf.Path(p["attribute"])
    if not path.IsAbsolutePath() or not path.IsPropertyPath():
        raise ContractError("Expected absolute attribute path")
    a = ctx.artifact.stage.GetAttributeAtPath(path)
    if not a or not a.HasAuthoredValueOpinion():
        raise MissingEvidence("Missing authored value: " + str(path))
    value = a.Get(Usd.TimeCode(p["time_code"]))
    expected = p["expected"]
    error = None
    if isinstance(expected, bool):
        ok = isinstance(value, bool) and value == expected
    elif isinstance(expected, str):
        ok = isinstance(value, str) and value == expected
    else:
        if isinstance(value, (bool, str)) or value is None:
            raise MissingEvidence(
                "Attribute type does not match numeric requirement: " + str(path)
            )
        try:
            actual = list(value) if isinstance(expected, list) else [float(value)]
        except (TypeError, ValueError):
            raise MissingEvidence(
                "Attribute type does not match requirement: " + str(path)
            )
        target = expected if isinstance(expected, list) else [expected]
        if len(actual) != len(target) or not all(
            isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v)
            for v in actual
        ):
            raise MissingEvidence("Nonfinite or incompatible attribute value")
        actual = [v * p.get("unit_scale", 1) for v in actual]
        if p.get("expected_encoding", "raw") != "raw":
            if len(target) != 3 or any(not 0 <= v <= 1 for v in target):
                raise ContractError("RGB expectations require three channels in [0,1]")
            # Authored shader RGB values are compared in linear space only when
            # the owner explicitly selects this encoding contract.
            if p["expected_encoding"] == "srgb":
                target = [
                    v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                    for v in target
                ]
        error = max(abs(a - b) for a, b in zip(actual, target))
        ok = error <= p["tolerance"]
        value = actual if isinstance(expected, list) else actual[0]
    row = dict(
        object=str(path),
        status="PASS" if ok else "FAIL",
        expected=expected,
        observed=value,
        max_error=error,
        time_code=p["time_code"],
        expected_encoding=p.get("expected_encoding", "raw"),
    )
    return Outcome(
        row["status"],
        "Compared explicit authored attribute with owner-held value.",
        dict(
            findings=[row],
            coverage="Authored value only; no rendered appearance, physics or engineering qualification.",
        ),
    )


def relative_motion(ctx, p):
    from .motion_timing import read_clock, elapsed_time_code
    from .continuous_motion import matrix_at

    stage = ctx.artifact.stage
    clock = read_clock(stage)
    prim = stage.GetPrimAtPath(p["path"])
    if not prim or not prim.IsActive() or not prim.IsDefined():
        raise MissingEvidence("Required moving subject is absent: " + p["path"])
    if p["end_s"] < p["start_s"]:
        raise ContractError("Relative motion end precedes start")
    if not stage.HasAuthoredMetadata("metersPerUnit"):
        raise MissingEvidence("Relative movement needs authored units")
    units = UsdGeom.GetStageMetersPerUnit(stage)
    if not math.isfinite(units) or units <= 0:
        raise MissingEvidence("Invalid stage units")
    values = [
        matrix_at(stage, p["path"], clock, t).ExtractTranslation() * units
        for t in [p["start_s"], p["end_s"]]
    ]
    delta = list(values[1] - values[0])
    errors = [abs(a - b) for a, b in zip(delta, p["delta_m"]) if b is not None]
    if not errors:
        raise ContractError("Relative movement needs at least one constrained axis")
    error = max(errors)
    status = "PASS" if error <= p["tolerance_m"] else "FAIL"
    return Outcome(
        status,
        "Compared displacement between two elapsed times.",
        dict(
            findings=[
                dict(
                    object=p["path"],
                    status=status,
                    expected=p["delta_m"],
                    observed=delta,
                    max_error_m=error,
                )
            ],
            coverage="World-origin displacement at endpoints only; intermediate path unassessed.",
        ),
    )


def rotation_rate(ctx, p):
    from .motion_timing import read_clock, elapsed_time_code

    stage = ctx.artifact.stage
    clock = read_clock(stage)
    a = stage.GetAttributeAtPath(p["attribute"])
    if not a or a.GetName().split(":")[1:2] not in (
        ["rotateX"],
        ["rotateY"],
        ["rotateZ"],
    ):
        raise MissingEvidence(
            "Rotation rate requires one authored scalar rotateX/Y/Z op"
        )
    xf = UsdGeom.Xformable(a.GetPrim())
    ops = (
        [op for op in xf.GetOrderedXformOps() if op.GetAttr().GetPath() == a.GetPath()]
        if xf
        else []
    )
    if len(ops) != 1 or ops[0].IsInverseOp():
        raise MissingEvidence(
            "Rotation rate requires one active forward scalar transform op"
        )
    if a.HasSpline() or stage.GetInterpolationType() != Usd.InterpolationTypeLinear:
        raise MissingEvidence(
            "Rotation rate supports linear saved scalar rotation only"
        )
    start, end = p["interval_s"]
    if start >= end:
        raise ContractError("Rotation interval must increase")
    lo, hi = [elapsed_time_code(clock, t) for t in (start, end)]
    knots = sorted({lo, hi, *[t for t in a.GetTimeSamples() if lo < t < hi]})
    if len(knots) > 4097:
        raise MissingEvidence("Rotation exceeds knot capacity")
    rows = []
    for t, u in zip(knots, knots[1:]):
        v, w = a.Get(Usd.TimeCode(t)), a.Get(Usd.TimeCode(u))
        if (
            not isinstance(v, (float, int))
            or not isinstance(w, (float, int))
            or not math.isfinite(v + w)
        ):
            raise MissingEvidence("Rotation has no finite scalar samples")
        rpm = (w - v) / 360 * 60 * clock["time_codes_per_second"] / (u - t)
        rows.append(
            dict(
                status=(
                    "PASS"
                    if abs(rpm - p["expected_rpm"]) <= p["tolerance_rpm"]
                    else "FAIL"
                ),
                expected_rpm=p["expected_rpm"],
                observed_rpm=rpm,
                start_s=(t - clock["start_time_code"]) / clock["time_codes_per_second"],
                end_s=(u - clock["start_time_code"]) / clock["time_codes_per_second"],
            )
        )
    from .observations import status_of

    return Outcome(
        status_of(rows),
        "Compared every scalar rotation segment with the declared rate.",
        dict(
            findings=rows,
            coverage="Authored local unwrapped angle only. This does not measure composed world rotation, simulation speed or a controller.",
        ),
    )
