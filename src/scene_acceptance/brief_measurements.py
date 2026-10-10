"""Explicit, bounded measurements. This pack does not interpret a brief."""

from pathlib import Path
import math
from pxr import Gf, Sdf, Usd, UsdGeom
from .builtin_packs import obj, TEXT, VEC3
from .coverage import assessment
from .model import ContractError, MissingEvidence, sha
from .packs import CheckSpec, Outcome, Pack
from .image_evidence import resolve_asset_input


def world_bounds(stage, path, time_code):
    """Recompute Cube/Mesh bounds from geometry, never an authored extent hint."""
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsActive() or not prim.IsDefined():
        return None
    if not stage.HasAuthoredMetadata("metersPerUnit"):
        raise MissingEvidence("Named bounds need authored metres per unit")
    units = UsdGeom.GetStageMetersPerUnit(stage)
    if not math.isfinite(units) or units <= 0:
        raise MissingEvidence("Stage units must be finite and positive")
    current = prim
    while current and not current.IsPseudoRoot():
        if any(
            p.GetName().startswith(("skel:", "primvars:skel:"))
            for p in current.GetAuthoredProperties()
        ):
            raise MissingEvidence(
                "Bounds cannot evaluate skinning or blend shapes: " + path
            )
        current = current.GetParent()
    time = Usd.TimeCode(time_code)
    if prim.IsA(UsdGeom.Cube):
        size = UsdGeom.Cube(prim).GetSizeAttr().Get(time)
        if size is None or not math.isfinite(size) or size <= 0:
            raise MissingEvidence("Cube has no finite positive size")
        points = [
            (x * size / 2, y * size / 2, z * size / 2)
            for x in (-1, 1)
            for y in (-1, 1)
            for z in (-1, 1)
        ]
    elif prim.IsA(UsdGeom.Cylinder) or prim.IsA(UsdGeom.Sphere):
        shape = (
            UsdGeom.Cylinder(prim)
            if prim.IsA(UsdGeom.Cylinder)
            else UsdGeom.Sphere(prim)
        )
        radius = shape.GetRadiusAttr().Get(time)
        if not radius or not math.isfinite(radius) or radius <= 0:
            raise MissingEvidence("Implicit shape needs positive radius: " + path)
        matrix = UsdGeom.XformCache(time).GetLocalToWorldTransform(prim)
        if (
            any(abs(matrix[i][3]) > 1e-12 for i in range(3))
            or abs(matrix[3][3] - 1) > 1e-12
        ):
            raise MissingEvidence(
                "Projective transforms are outside implicit bounds coverage"
            )
        center = matrix.Transform(Gf.Vec3d(0)) * units
        if prim.IsA(UsdGeom.Sphere):
            half = [
                radius * math.sqrt(sum(matrix[j][i] ** 2 for j in range(3))) * units
                for i in range(3)
            ]
        else:
            height = shape.GetHeightAttr().Get(time)
            axis = {"X": 0, "Y": 1, "Z": 2}[str(shape.GetAxisAttr().Get(time))]
            if not height or not math.isfinite(height) or height <= 0:
                raise MissingEvidence("Cylinder needs positive height: " + path)
            half = [
                (
                    height / 2 * abs(matrix[axis][i])
                    + radius
                    * math.sqrt(sum(matrix[j][i] ** 2 for j in range(3) if j != axis))
                )
                * units
                for i in range(3)
            ]
        if not all(math.isfinite(x) for x in [*center, *half]):
            raise MissingEvidence("Nonfinite implicit bounds")
        return dict(
            minimum_m=[center[i] - half[i] for i in range(3)],
            maximum_m=[center[i] + half[i] for i in range(3)],
            size_m=[2 * h for h in half],
            center_m=list(center),
        )
    elif prim.IsA(UsdGeom.Mesh):
        points = UsdGeom.Mesh(prim).GetPointsAttr().Get(time)
        if points is None or not len(points) or len(points) > 100000:
            raise MissingEvidence("Mesh needs 1–100000 points")
    else:
        raise MissingEvidence(
            "Named bounds support Cube, planar Mesh, Cylinder and Sphere; aggregate bounds need an explicit selection"
        )
    matrix = UsdGeom.XformCache(time).GetLocalToWorldTransform(prim)
    if (
        any(abs(matrix[i][3]) > 1e-12 for i in range(3))
        or abs(matrix[3][3] - 1) > 1e-12
    ):
        raise MissingEvidence("Projective transforms are outside bounds coverage")
    points = [matrix.Transform(Gf.Vec3d(*p)) * units for p in points]
    if not all(math.isfinite(v) for p in points for v in p):
        raise MissingEvidence("Non-finite geometry or transform")
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    return dict(
        minimum_m=low,
        maximum_m=high,
        size_m=[high[i] - low[i] for i in range(3)],
        center_m=[(high[i] + low[i]) / 2 for i in range(3)],
    )


def outcome(rows, scope, **extra):
    status = "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
    return Outcome(
        status,
        scope,
        dict(assessment=assessment("requirement comparisons", rows, scope), **extra),
    )


def bounds(ctx, params):
    observed = world_bounds(ctx.artifact.stage, params["path"], params["time_code"])
    if observed is None:
        return outcome(
            [
                dict(
                    subject=params["path"],
                    status="FAIL",
                    reason="Required named geometry is absent",
                )
            ],
            "Named world bounds",
        )
    rows = []
    for key in ("size_m", "center_m", "minimum_m", "maximum_m"):
        if key not in params:
            continue
        errors = [
            abs(a - b) for a, b in zip(observed[key], params[key]) if b is not None
        ]
        if not errors:
            raise ContractError("At least one bounds axis must be constrained")
        error = max(errors)
        rows.append(
            dict(
                subject=params["path"] + ":" + key,
                status="PASS" if error <= params["tolerance_m"] else "FAIL",
                observed=observed[key],
                expected=params[key],
                max_error_m=error,
                tolerance_m=params["tolerance_m"],
                reason=f"{key}: observed {observed[key]}; expected {params[key]}; largest error {error:.6g} m",
            )
        )
    if not rows:
        raise ContractError("Bounds needs a size or centre target")
    return outcome(
        rows,
        "Named Cube/Mesh world axis-aligned bounds at one time; no shape equivalence or topology claim",
        **observed,
    )


def children(ctx, params):
    prim = ctx.artifact.stage.GetPrimAtPath(params["parent"])
    if not prim or not prim.IsActive():
        return outcome(
            [
                dict(
                    subject=params["parent"],
                    status="FAIL",
                    reason="Required parent is absent",
                )
            ],
            "Direct-child count",
        )
    paths = [
        str(p.GetPath())
        for p in prim.GetChildren()
        if p.GetTypeName() == params["type"]
    ]
    row = dict(
        subject=params["parent"],
        status="PASS" if len(paths) == params["count"] else "FAIL",
        observed=len(paths),
        expected=params["count"],
        paths=paths,
        reason=f"{len(paths)} direct {params['type']} children; expected {params['count']}",
    )
    return outcome(
        [row],
        "Count active defined direct children of one declared type; no dimensions or physical function claim",
    )


def metadata(ctx, params):
    rows = []
    stage = ctx.artifact.stage
    for name, expected in params["values"].items():
        authored = stage.HasAuthoredMetadata(name)
        observed = stage.GetMetadata(name) if authored else None
        match = authored and (
            observed == expected
            if isinstance(expected, str)
            else isinstance(observed, (int, float))
            and math.isfinite(observed)
            and abs(observed - expected) <= params["tolerance"]
        )
        rows.append(
            dict(
                subject="/:" + name,
                status="PASS" if match else "FAIL",
                observed=observed,
                expected=expected,
                authored=authored,
                reason=f"{name}: authored {observed!r}; required {expected!r}",
            )
        )
    return outcome(
        rows,
        "Explicit authored stage metadata targets; no inference from fallback values or geometry",
    )


def axis_gap(ctx, params):
    a = world_bounds(ctx.artifact.stage, params["a"], params["time_code"])
    b = world_bounds(ctx.artifact.stage, params["b"], params["time_code"])
    subject = params["a"] + " → " + params["b"]
    if a is None or b is None:
        return outcome(
            [
                dict(
                    subject=subject,
                    status="FAIL",
                    reason="A required named geometry is absent",
                )
            ],
            "Directed axis gap",
        )
    axis = "xyz".index(params["axis"])
    gap = b["minimum_m"][axis] - a["maximum_m"][axis]
    return outcome(
        [
            dict(
                subject=subject,
                status=(
                    "PASS"
                    if gap + params["tolerance_m"] >= params["minimum_m"]
                    else "FAIL"
                ),
                observed_gap_m=gap,
                expected_minimum_m=params["minimum_m"],
                tolerance_m=params["tolerance_m"],
                reason=f"{params['axis'].upper()} gap {gap:.6g} m; required at least {params['minimum_m']:.6g} m",
            )
        ],
        "Directed gap between two world bounding boxes at one time; not collision, access, or safety certification",
        a=a,
        b=b,
    )


def read_image(path):
    from .image_policy import load_image

    return load_image(path, max_bytes=1048576, max_pixels=262144, modes=("RGB",))


def _comparison_pixels(ctx, params, size):
    """Return the declared pixel selection; rectangles use half-open coordinates."""
    width, height = size
    selected = bytearray(width * height)
    regions = params.get("regions", [dict(x=0, y=0, width=width, height=height)])
    excluded = params.get("excluded_regions", [])
    for rectangles, value in ((regions, 1), (excluded, 0)):
        for rectangle in rectangles:
            x, y, w, h = (rectangle[k] for k in ("x", "y", "width", "height"))
            if x < 0 or y < 0 or w < 1 or h < 1 or x + w > width or y + h > height:
                raise ContractError(
                    "Comparison rectangle is outside the reference image"
                )
            for row in range(y, y + h):
                selected[row * width + x : row * width + x + w] = bytes([value]) * w
    mask_evidence = None
    if params.get("mask_image"):
        name = params["mask_image"]
        if name not in ctx.sources:
            raise ContractError("Comparison mask must be a declared evidence source")
        path = ctx.bundle.record(name, missing=True)
        mask = read_image(path)
        if mask.size != size:
            raise ContractError("Comparison mask must match reference image dimensions")
        for i, pixel in enumerate(mask.get_flattened_data()):
            if pixel not in ((0, 0, 0), (255, 255, 255)):
                raise ContractError(
                    "Comparison mask requires RGB black/excluded or white/included pixels"
                )
            selected[i] &= pixel == (255, 255, 255)
        mask_evidence = dict(
            path=name, sha256=sha(path), white="included", black="excluded"
        )
    if not any(selected):
        raise ContractError("Comparison policy selects no pixels")
    return selected, dict(
        coordinate_system="stored image pixels; x right, y down; half-open rectangles",
        regions=regions,
        excluded_regions=excluded,
        mask=mask_evidence,
        combination="union of regions, minus exclusions, intersected with white mask pixels",
    )


def image_pixels(ctx, params):
    attribute = ctx.artifact.stage.GetAttributeAtPath(params["asset_attribute"])
    if not attribute or attribute.GetTypeName() != Sdf.ValueTypeNames.Asset:
        return outcome(
            [
                dict(
                    subject=params["asset_attribute"],
                    status="FAIL",
                    reason="Required texture attribute is absent",
                )
            ],
            "Reference image pixels",
        )
    actual, resolution = resolve_asset_input(ctx, attribute)
    if actual is None:
        raise MissingEvidence("Selected texture reference is empty")
    if params["reference_image"] not in ctx.sources:
        raise ContractError("Reference image must be a declared evidence source")
    reference = ctx.bundle.record(params["reference_image"], missing=True)
    try:
        observed, expected = read_image(actual), read_image(reference)
    except MissingEvidence:
        raise
    except (OSError, ValueError, SyntaxError) as exc:
        raise MissingEvidence("Image could not be decoded: " + str(exc)) from exc
    same_size = observed.size == expected.size
    selected, policy = _comparison_pixels(ctx, params, expected.size)
    maximum = whole_maximum = different = None
    means = whole_means = None
    compared = sum(selected) if same_size else 0
    if same_size:
        sums = [0, 0, 0]
        whole_sums = [0, 0, 0]
        maximum = whole_maximum = different = 0
        pairs = zip(observed.get_flattened_data(), expected.get_flattened_data())
        for i, (a, b) in enumerate(pairs):
            delta = [abs(x - y) for x, y in zip(a, b)]
            whole_maximum = max(whole_maximum, *delta)
            for channel in range(3):
                whole_sums[channel] += delta[channel]
            if selected[i]:
                maximum = max(maximum, *delta)
                different += any(error > params["max_channel_error"] for error in delta)
                for channel in range(3):
                    sums[channel] += delta[channel]
        means = [total / compared for total in sums]
        whole_means = [total / len(selected) for total in whole_sums]
    mean_limit = params.get("max_mean_channel_error")
    passed = (
        same_size
        and maximum <= params["max_channel_error"]
        and (mean_limit is None or max(means) <= mean_limit)
    )
    policy.update(
        max_channel_error=params["max_channel_error"],
        max_mean_channel_error=mean_limit,
        mean_metric="arithmetic mean absolute error per RGB channel; every channel must satisfy the limit",
        colour_management="none; stored RGB channel values",
    )
    return outcome(
        [
            dict(
                subject=params["asset_attribute"],
                status="PASS" if passed else "FAIL",
                observed_size=list(observed.size),
                expected_size=list(expected.size),
                differing_pixels=different,
                compared_pixels=compared,
                excluded_pixels=len(selected) - sum(selected),
                maximum_channel_error=maximum,
                allowed_channel_error=params["max_channel_error"],
                mean_channel_errors=means,
                allowed_mean_channel_error=mean_limit,
                whole_image_maximum_channel_error=whole_maximum,
                whole_image_mean_channel_errors=whole_means,
                reason=f"Image {observed.size} vs {expected.size}; compared pixels {compared}; differing pixels {different}; maximum channel error {maximum}; mean errors {means}",
            )
        ],
        "Decoded RGB source pixels in stored row order; no UV, shader connectivity, colour-management or rendered-appearance proof",
        actual_image_sha256=sha(actual),
        reference_image_sha256=sha(reference),
        comparison_policy=policy,
        asset_resolution=resolution,
    )


def brief_measurement_pack():
    from .preflight import bounds as bounds_preflight
    from .requirement_values import (
        attribute_value,
        relative_motion,
        VALUE_SCHEMA,
        RELATIVE_SCHEMA,
    )

    nonnegative = {"type": "number", "minimum": 0}
    bounds_schema = obj(
        {
            "path": TEXT,
            "time_code": {"type": "number"},
            "size_m": {**VEC3, "items": {"type": ["number", "null"]}},
            "center_m": {**VEC3, "items": {"type": ["number", "null"]}},
            "minimum_m": {**VEC3, "items": {"type": ["number", "null"]}},
            "maximum_m": {**VEC3, "items": {"type": ["number", "null"]}},
            "tolerance_m": nonnegative,
        },
        required=["path", "time_code", "tolerance_m"],
    )
    bounds_schema["anyOf"] = [
        {"required": [k]} for k in ("size_m", "center_m", "minimum_m", "maximum_m")
    ]
    rectangle = obj(
        {
            "x": {"type": "integer", "minimum": 0},
            "y": {"type": "integer", "minimum": 0},
            "width": {"type": "integer", "minimum": 1},
            "height": {"type": "integer", "minimum": 1},
        }
    )
    rectangles = {"type": "array", "items": rectangle, "minItems": 1, "maxItems": 64}
    image_schema = obj(
        {
            "asset_attribute": TEXT,
            "reference_image": TEXT,
            "max_channel_error": {"type": "integer", "minimum": 0, "maximum": 255},
            "max_mean_channel_error": {"type": "number", "minimum": 0, "maximum": 255},
            "regions": rectangles,
            "excluded_regions": rectangles,
            "mask_image": TEXT,
        },
        required=["asset_attribute", "reference_image", "max_channel_error"],
    )
    from .requirement_values import rotation_rate

    return Pack(
        "brief.measurements",
        "1.4.0",
        "Explicit named-geometry, stage metadata and reference-image comparisons",
        {
            "rotation_rate": CheckSpec(
                rotation_rate,
                obj(
                    dict(
                        attribute=TEXT,
                        interval_s={
                            "type": "array",
                            "items": {"type": "number", "minimum": 0},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        expected_rpm={"type": "number"},
                        tolerance_rpm={"type": "number", "minimum": 0},
                    )
                ),
                "Compare authored scalar rotation rate",
                "Every linear scalar angle segment; local coordinates",
            ),
            "attribute_value": CheckSpec(
                attribute_value,
                VALUE_SCHEMA,
                "Compare an authored value",
                "One owner-selected attribute and time; no rendered appearance",
            ),
            "relative_motion": CheckSpec(
                relative_motion,
                RELATIVE_SCHEMA,
                "Compare relative world displacement",
                "Two saved times; no path or continuous-motion claim",
            ),
            "metadata": CheckSpec(
                metadata,
                obj(
                    {
                        "values": {
                            "type": "object",
                            "minProperties": 1,
                            "properties": {
                                "upAxis": {"enum": ["Y", "Z"]},
                                "metersPerUnit": {
                                    "type": "number",
                                    "exclusiveMinimum": 0,
                                },
                                "startTimeCode": {"type": "number"},
                                "endTimeCode": {"type": "number"},
                                "timeCodesPerSecond": {
                                    "type": "number",
                                    "exclusiveMinimum": 0,
                                },
                            },
                            "additionalProperties": False,
                        },
                        "tolerance": nonnegative,
                    }
                ),
                "Authored stage metadata matches specified values",
                "Selected authored metadata fields",
                ("No active motion or world-coordinate interpretation claim",),
            ),
            "bounds": CheckSpec(
                bounds,
                bounds_schema,
                "Named geometry size and centre",
                "World Cube/Mesh/Cylinder/Sphere bounds at one time",
                ("No shape equivalence",),
                capabilities={
                    "geometry": ["Cube", "Mesh", "Cylinder", "Sphere"],
                    "time": "named",
                },
                preflight=bounds_preflight,
            ),
            "children": CheckSpec(
                children,
                obj(
                    {
                        "parent": TEXT,
                        "type": TEXT,
                        "count": {"type": "integer", "minimum": 0, "maximum": 10000},
                    }
                ),
                "Required direct-child count",
                "One parent and type",
                ("Count does not establish function or dimensions",),
            ),
            "axis_gap": CheckSpec(
                axis_gap,
                obj(
                    {
                        "a": TEXT,
                        "b": TEXT,
                        "axis": {"enum": ["x", "y", "z"]},
                        "time_code": {"type": "number"},
                        "minimum_m": nonnegative,
                        "tolerance_m": nonnegative,
                    }
                ),
                "Required directed axis gap",
                "Two named Cube/Mesh world bounding boxes",
                ("Not a walkability or safety test",),
            ),
            "image_pixels": CheckSpec(
                image_pixels,
                image_schema,
                "Delivered texture matches a reference image",
                "Declared regions/mask of static decoded RGB source pixels",
                (
                    "Does not prove rendered appearance; excluded pixels are not accepted",
                ),
            ),
        },
        tuple(
            str(Path(__file__).with_name(n))
            for n in (
                "brief_measurements.py",
                "image_evidence.py",
                "image_policy.py",
                "preflight.py",
                "requirement_values.py",
                "continuous_motion.py",
                "motion_timing.py",
                "observations.py",
            )
        ),
        ("usd-core", "Pillow"),
    )
