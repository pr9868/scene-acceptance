"""Triangle-surface distance and conservative sweeps of translating closed solids."""

from fractions import Fraction
from pathlib import Path
import math

from pxr import Gf

from .builtin_packs import obj, TEXT, VEC3
from .continuous_motion import affine_times, matrix_at
from .model import ContractError, MissingEvidence
from .packs import CheckSpec, Outcome, Pack

from .geometry_access import box, read_triangles, read_geometry
from .subjects import SELECTOR
from .preflight import geometry as geometry_preflight


def segment_distance(a, b, c, d):
    u, v, w = b - a, d - c, a - c
    aa, bb, cc, dd, ee = (
        Gf.Dot(u, u),
        Gf.Dot(u, v),
        Gf.Dot(v, v),
        Gf.Dot(u, w),
        Gf.Dot(v, w),
    )
    denominator = aa * cc - bb * bb
    s = (
        min(1.0, max(0.0, (bb * ee - cc * dd) / denominator))
        if denominator > 1e-30
        else 0.0
    )
    t = (bb * s + ee) / cc if cc else 0.0
    if t < 0:
        t = 0.0
        s = min(1.0, max(0.0, -dd / aa)) if aa else 0.0
    elif t > 1:
        t = 1.0
        s = min(1.0, max(0.0, (bb - dd) / aa)) if aa else 0.0
    return (w + s * u - t * v).GetLength()


def point_triangle(p, a, b, c):
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = Gf.Dot(ab, ap), Gf.Dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return ap.GetLength()
    bp = p - b
    d3, d4 = Gf.Dot(ab, bp), Gf.Dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return bp.GetLength()
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return (p - (a + ab * (d1 / (d1 - d3)))).GetLength()
    cp = p - c
    d5, d6 = Gf.Dot(ab, cp), Gf.Dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return cp.GetLength()
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return (p - (a + ac * (d2 / (d2 - d6)))).GetLength()
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        return (p - (b + (c - b) * ((d4 - d3) / ((d4 - d3) + (d5 - d6))))).GetLength()
    total = va + vb + vc
    if abs(total) < 1e-30:
        raise MissingEvidence("Triangle is numerically degenerate")
    return (p - (a + ab * (vb / total) + ac * (vc / total))).GetLength()


def crosses(p, q, triangle):
    a, b, c = triangle
    direction = q - p
    edge1, edge2 = b - a, c - a
    h = Gf.Cross(direction, edge2)
    determinant = Gf.Dot(edge1, h)
    scale = edge1.GetLength() * edge2.GetLength() * direction.GetLength()
    if abs(determinant) <= 1e-14 * scale:
        return _exact_crosses(p, q, triangle)
    s = p - a
    u = Gf.Dot(s, h) / determinant
    v = Gf.Dot(direction, Gf.Cross(s, edge1)) / determinant
    t = Gf.Dot(edge2, Gf.Cross(s, edge1)) / determinant
    return 0 <= u <= 1 and 0 <= v and u + v <= 1 and 0 <= t <= 1


def _exact_crosses(p, q, triangle):
    """Resolve near-parallel intersections exactly for the saved float points.

    A small determinant alone is not evidence of either a crossing or a gap.
    Rational arithmetic avoids division by a cancellation-rounded determinant.
    This predicate does not make the remaining distance arithmetic exact.
    """

    def vector(point):
        return tuple(Fraction(x) for x in point)

    def sub(a, b):
        return tuple(x - y for x, y in zip(a, b))

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    def cross(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    p, q = vector(p), vector(q)
    a, b, c = map(vector, triangle)
    direction, edge1, edge2 = sub(q, p), sub(b, a), sub(c, a)
    h = cross(direction, edge2)
    determinant = dot(edge1, h)
    if not determinant:
        # Exactly coplanar/parallel: edge and point distances handle contact.
        return False
    s = sub(p, a)
    u = dot(s, h) / determinant
    v = dot(direction, cross(s, edge1)) / determinant
    t = dot(edge2, cross(s, edge1)) / determinant
    return 0 <= u <= 1 and 0 <= v and u + v <= 1 and 0 <= t <= 1


def inside(point, triangles):
    angle = 0.0
    for triangle in triangles:
        a, b, c = [p - point for p in triangle]
        la, lb, lc = a.GetLength(), b.GetLength(), c.GetLength()
        if min(la, lb, lc) < 1e-14:
            return True
        angle += 2 * math.atan2(
            Gf.Dot(a, Gf.Cross(b, c)),
            la * lb * lc + Gf.Dot(a, b) * lc + Gf.Dot(b, c) * la + Gf.Dot(c, a) * lb,
        )
    return abs(angle) > 2 * math.pi


def distance(a, b, solid, max_pairs):
    if len(a) * len(b) > max_pairs:
        raise MissingEvidence("Triangle-pair budget exceeded")
    best = math.inf
    for ta in a:
        for tb in b:
            ea = [(ta[i], ta[(i + 1) % 3]) for i in range(3)]
            eb = [(tb[i], tb[(i + 1) % 3]) for i in range(3)]
            if any(crosses(p, q, tb) for p, q in ea) or any(
                crosses(p, q, ta) for p, q in eb
            ):
                return 0.0
            best = min(
                best,
                *(point_triangle(p, *tb) for p in ta),
                *(point_triangle(p, *ta) for p in tb),
                *(segment_distance(p, q, r, s) for p, q in ea for r, s in eb),
            )
    # Check every connected component through its face vertices, not just the
    # first face: a disconnected island can be inside the other solid.
    if solid and (any(inside(t[0], b) for t in a) or any(inside(t[0], a) for t in b)):
        return 0.0
    return best


def static(ctx, params):
    solid = params["representation"] == "closed-solids"
    ga = read_geometry(
        ctx.artifact.stage,
        params["a"],
        params["time_s"],
        solid,
        approximation_m=params.get("approximation_m", 0.001),
    )
    gb = read_geometry(
        ctx.artifact.stage,
        params["b"],
        params["time_s"],
        solid,
        approximation_m=params.get("approximation_m", 0.001),
    )
    a, b = ga.triangles, gb.triangles
    value = distance(a, b, solid, params["max_triangle_pairs"])
    margin = params["numeric_margin_m"] + ga.error_m + gb.error_m
    target = params["minimum_m"]
    status = (
        "FAIL"
        if value + margin < target
        else "PASS" if value - margin >= target else "UNKNOWN"
    )
    return Outcome(
        status,
        "Compared triangle clearance under the declared surface or closed-solid policy.",
        dict(
            distance_m=value,
            minimum_m=target,
            numeric_margin_m=margin,
            triangle_counts=[len(a), len(b)],
            approximation_error_m=ga.error_m + gb.error_m,
            geometry_methods=[ga.method, gb.method],
            time_s=params["time_s"],
            representation=params["representation"],
            subjects=[params["a"], params["b"]],
            coverage="Selected saved triangles only; no hidden procedural geometry or collider equivalence. Self-intersecting input solids require a separate mesh-validity check.",
        ),
    )


def sweep(ctx, params):
    stage = ctx.artifact.stage
    clock, units, times = affine_times(
        stage, [params["a"], params["b"]], params["interval_s"]
    )
    solid = params["representation"] == "closed-solids"
    rows = []
    status = "PASS"

    def at(time):
        a = read_triangles(stage, params["a"], time, solid)
        b = read_triangles(stage, params["b"], time, solid)
        return distance(a, b, solid, params["max_triangle_pairs"])

    pending = []
    for start, end in zip(times, times[1:]):
        speeds = []
        for path in (params["a"], params["b"]):
            p = matrix_at(stage, path, clock, start).ExtractTranslation() * units
            q = matrix_at(stage, path, clock, end).ExtractTranslation() * units
            speeds.append((q - p).GetLength() / (end - start))
        pending.append((start, end, sum(speeds)))
    while pending:
        if len(rows) >= params["max_evaluations"]:
            status = "UNKNOWN"
            break
        start, end, speed = pending.pop()
        mid = (start + end) / 2
        value = at(mid)
        margin = params["numeric_margin_m"]
        lower = math.nextafter(value - speed * (end - start) / 2 - margin, -math.inf)
        row = dict(
            start_s=start,
            end_s=end,
            midpoint_s=mid,
            observed_distance_m=value,
            lower_bound_m=max(0.0, lower),
            speed_bound_m_s=speed,
        )
        rows.append(row)
        if value + margin < params["minimum_m"]:
            row["status"] = "FAIL"
            status = "FAIL"
            break
        if lower >= params["minimum_m"]:
            row["status"] = "PASS"
            continue
        row["status"] = "subdivided"
        if end - start <= params["minimum_interval_s"]:
            row["status"] = "UNKNOWN"
            status = "UNKNOWN"
            break
        pending.extend([(start, mid, speed), (mid, end, speed)])
    return Outcome(
        status,
        "Bounded swept clearance using translation speeds and triangle-distance samples.",
        dict(
            interval_s=params["interval_s"],
            minimum_m=params["minimum_m"],
            intervals=rows,
            unfinished_intervals=len(pending),
            numeric_margin_m=params["numeric_margin_m"],
            coverage="Entire interval only when every interval is certified. Rotation, deformation, unresolved geometry or exhausted budget stays unknown. No explicit swept-volume mesh is generated.",
        ),
    )


def _clip_triangle(triangle, lo, hi):
    polygon = list(triangle)
    for axis in range(3):
        for edge, direction in [(lo[axis], 1), (hi[axis], -1)]:
            if not polygon:
                return []
            result = []
            for p, q in zip(polygon, polygon[1:] + polygon[:1]):
                a = (p[axis] - edge) * direction
                b = (q[axis] - edge) * direction
                if a >= 0:
                    result.append(p)
                if (a < 0 and b >= 0) or (a >= 0 and b < 0):
                    t = a / (a - b)
                    hit = p + (q - p) * t
                    hit[axis] = edge
                    result.append(hit)
            polygon = result
    return polygon


def zone(ctx, params):
    from .subjects import resolve
    from .observations import status_of
    from .coverage import assessment

    lo, hi = params["zone_min_m"], params["zone_max_m"]
    contact_tolerance = params.get("contact_tolerance_m", 0)
    if contact_tolerance and params.get("contact_policy", "forbid") != "allow":
        raise ContractError("A contact allowance requires contact_policy=allow")
    lo = [x + contact_tolerance for x in lo]
    hi = [x - contact_tolerance for x in hi]
    if any(a >= b for a, b in zip(lo, hi)):
        raise ContractError("Clear-height zone bounds must increase on every axis")
    if "selector" in params and "obstacles" in params:
        raise ContractError("Choose selector or obstacles, not both")
    selection = (
        resolve(ctx.artifact.stage, params["selector"])
        if "selector" in params
        else dict(
            paths=params.get("obstacles", []), excluded=[], missing=[], unavailable=[]
        )
    )
    paths = selection["paths"]
    target = box(lo, hi)
    rows = []
    if selection.get("capacity_exhausted"):
        rows.append(
            dict(
                path="selection",
                status="UNKNOWN",
                cause="capacity_limit",
                reason="Subject selection capacity exhausted; unvisited subjects remain unassessed",
                resolution="raise_resource_budget",
            )
        )
    for p in selection.get("missing", []):
        rows.append(
            dict(
                path=p,
                status="FAIL",
                reason="Required selected subject absent",
                cause="scene_mismatch",
            )
        )
    for p in selection.get("unavailable", []):
        rows.append(
            dict(
                path=p,
                status="UNKNOWN",
                reason="Subject inactive, undefined or unloaded",
                cause="missing_evidence",
            )
        )
    if not paths and not rows:
        rows.append(
            dict(
                path="selection",
                status="UNKNOWN",
                reason="No obstacles selected",
                cause="missing_evidence",
            )
        )
    solid = params.get("representation", "closed-solids") == "closed-solids"
    contact = params.get("contact_policy", "forbid")
    for path in paths:
        try:
            geom = read_geometry(
                ctx.artifact.stage,
                path,
                params["time_s"],
                solid,
                approximation_m=params.get("approximation_m", 0.001),
            )
            lower, upper = geom.bounds()
            margin = params["numeric_margin_m"] + geom.error_m
            separation = math.sqrt(
                sum(max(lo[i] - upper[i], lower[i] - hi[i], 0) ** 2 for i in range(3))
            )
            if separation > margin:
                rows.append(
                    dict(
                        path=path,
                        status="PASS",
                        distance_lower_bound_m=max(0, separation - geom.error_m),
                        method="conservative-bounds-separation",
                        approximation_error_m=geom.error_m,
                    )
                )
                continue
            touched = False
            ambiguous = False
            penetrated = False
            for index, triangle in enumerate(geom.triangles):
                if index * 12 >= params["max_triangle_pairs"]:
                    raise MissingEvidence("Triangle-pair capacity exceeded: " + path)
                polygon = _clip_triangle(triangle, lo, hi)
                if not polygon:
                    continue
                touched = True
                center = sum(polygon, Gf.Vec3d(0)) / len(polygon)
                depth = min(min(center[i] - lo[i], hi[i] - center[i]) for i in range(3))
                if depth > margin:
                    penetrated = True
                    break
                # Exact planar boundary contact is distinguishable from shallow
                # penetration. Approximate surfaces cannot certify this equality.
                boundary = any(
                    all(p[i] == edge for p in polygon)
                    for i in range(3)
                    for edge in (lo[i], hi[i])
                )
                ambiguous |= not boundary or geom.error_m > 0
            if not touched and solid:
                # This also catches a solid containing the entire clear zone.
                center = Gf.Vec3d(*[(a + b) / 2 for a, b in zip(lo, hi)])
                if inside(center, geom.triangles):
                    penetrated = True
            if penetrated:
                status = "FAIL"
            elif touched and contact == "forbid":
                status = "FAIL" if geom.error_m == 0 else "UNKNOWN"
            elif touched:
                status = "UNKNOWN" if ambiguous else "PASS"
            else:
                value = distance(
                    geom.triangles, target, False, params["max_triangle_pairs"]
                )
                status = "PASS" if value > margin else "UNKNOWN"
            rows.append(
                dict(
                    path=path,
                    status=status,
                    intersection=(
                        "penetration"
                        if penetrated
                        else "contact" if touched else "separated"
                    ),
                    geometry_method=geom.method,
                    approximation_error_m=geom.error_m,
                    contact_policy=contact,
                    representation="closed-solids" if solid else "surfaces",
                    cause=(
                        "scene_mismatch"
                        if status == "FAIL"
                        else "numeric_uncertainty" if status == "UNKNOWN" else None
                    ),
                )
            )
        except MissingEvidence as exc:
            rows.append(
                dict(
                    path=path,
                    status="UNKNOWN",
                    reason=str(exc),
                    cause=(
                        "capacity_limit"
                        if "capacity" in str(exc) or "budget" in str(exc)
                        else "unsupported_geometry"
                    ),
                    resolution="Choose supported evidence, geometry policy or a caller resource budget",
                )
            )
    scope = "Selected composed obstacles at one saved time; no navigation or reachability inference."
    return Outcome(
        status_of(rows),
        "Compared selected geometry with the declared clear volume and contact policy.",
        dict(
            findings=rows,
            assessment=assessment(
                "selected obstacle evaluations",
                [
                    dict(
                        subject=r["path"], **{k: v for k, v in r.items() if k != "path"}
                    )
                    for r in rows
                ],
                scope,
            ),
            selection=selection,
            zone_min_m=params["zone_min_m"],
            zone_max_m=params["zone_max_m"],
            contact_tolerance_m=contact_tolerance,
            evaluated_interior_min_m=lo,
            evaluated_interior_max_m=hi,
            time_s=params["time_s"],
            coverage=scope,
        ),
    )


def clearance_pack():
    common = dict(
        a=TEXT,
        b=TEXT,
        representation={"enum": ["surfaces", "closed-solids"]},
        minimum_m={"type": "number", "exclusiveMinimum": 0},
        numeric_margin_m={"type": "number", "exclusiveMinimum": 0},
        max_triangle_pairs={"type": "integer", "minimum": 1, "maximum": 250000},
    )
    return Pack(
        "geometry.clearance",
        "1.1.0",
        "Triangle clearance, clear volumes and bounded translating sweeps",
        {
            "distance": CheckSpec(
                static,
                obj(
                    {
                        **common,
                        "time_s": {"type": "number", "minimum": 0},
                        "approximation_m": {"type": "number", "exclusiveMinimum": 0},
                    },
                    required=[*common, "time_s"],
                ),
                "Measure mesh or cube clearance",
                "Selected surfaces at a named time",
                (
                    "Closed solids must be consistently oriented and free of self-intersections.",
                ),
                capabilities={
                    "geometry": ["Cube", "planar-Mesh", "Cylinder", "Sphere"],
                    "time": "named",
                },
                preflight=geometry_preflight,
            ),
            "sweep": CheckSpec(
                sweep,
                obj(
                    {
                        **common,
                        "interval_s": {
                            "type": "array",
                            "items": {"type": "number", "minimum": 0},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        "max_evaluations": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 4096,
                        },
                        "minimum_interval_s": {"type": "number", "exclusiveMinimum": 0},
                    }
                ),
                "Bound swept clearance",
                "Whole interval under piecewise affine translation",
                ("Unsupported motion and budget exhaustion remain unknown.",),
                capabilities={"time": "piecewise-affine-translation"},
                preflight=geometry_preflight,
            ),
            "clear_zone": CheckSpec(
                zone,
                obj(
                    {
                        "selector": SELECTOR,
                        "representation": {"enum": ["surfaces", "closed-solids"]},
                        "contact_policy": {"enum": ["forbid", "allow"]},
                        "contact_tolerance_m": {"type": "number", "minimum": 0},
                        "approximation_m": {"type": "number", "exclusiveMinimum": 0},
                        "zone_min_m": VEC3,
                        "zone_max_m": VEC3,
                        "obstacles": {
                            "type": "array",
                            "items": TEXT,
                            "minItems": 1,
                            "maxItems": 128,
                            "uniqueItems": True,
                        },
                        "time_s": {"type": "number", "minimum": 0},
                        "numeric_margin_m": {"type": "number", "exclusiveMinimum": 0},
                        "max_triangle_pairs": common["max_triangle_pairs"],
                    },
                    required=[
                        "zone_min_m",
                        "zone_max_m",
                        "time_s",
                        "numeric_margin_m",
                        "max_triangle_pairs",
                    ],
                ),
                "Check a clear-height volume",
                "Caller-selected obstacles and world-space box",
                ("A clear list is not proof that the caller named every obstacle.",),
                capabilities={"subjects": ["paths", "selector"], "time": "named"},
                preflight=geometry_preflight,
            ),
        },
        (
            str(Path(__file__)),
            str(Path(__file__).with_name("continuous_motion.py")),
            str(Path(__file__).with_name("motion_timing.py")),
            str(Path(__file__).with_name("geometry_access.py")),
            str(Path(__file__).with_name("subjects.py")),
            str(Path(__file__).with_name("observations.py")),
            str(Path(__file__).with_name("preflight.py")),
        ),
        ("usd-core",),
    )
