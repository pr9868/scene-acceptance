"""Triangle-surface distance and conservative sweeps of translating closed solids."""

from collections import Counter
from pathlib import Path
import math

from pxr import Gf, Usd, UsdGeom

from .builtin_packs import obj, TEXT, VEC3
from .continuous_motion import affine_times, matrix_at
from .model import ContractError, MissingEvidence
from .motion_timing import elapsed_time_code, read_clock
from .packs import CheckSpec, Outcome, Pack

BOX_FACES = [
    (0, 1, 3),
    (0, 3, 2),
    (4, 6, 7),
    (4, 7, 5),
    (0, 4, 5),
    (0, 5, 1),
    (2, 3, 7),
    (2, 7, 6),
    (0, 2, 6),
    (0, 6, 4),
    (1, 5, 7),
    (1, 7, 3),
]


def box(lo, hi):
    vertices = [
        Gf.Vec3d(x, y, z)
        for x in (lo[0], hi[0])
        for y in (lo[1], hi[1])
        for z in (lo[2], hi[2])
    ]
    return [tuple(vertices[i] for i in face) for face in BOX_FACES]


def read_triangles(stage, path, seconds, solid):
    prim = stage.GetPrimAtPath(path)
    if not prim:
        raise MissingEvidence("Missing clearance subject: " + path)
    clock = read_clock(stage)
    matrix = matrix_at(stage, path, clock, seconds)
    units = UsdGeom.GetStageMetersPerUnit(stage)
    if (
        not stage.HasAuthoredMetadata("metersPerUnit")
        or not math.isfinite(units)
        or units <= 0
    ):
        raise MissingEvidence("Clearance requires authored positive stage units")
    if prim.IsA(UsdGeom.Cube):
        attr = UsdGeom.Cube(prim).GetSizeAttr()
        size = attr.Get()
        if (
            attr.GetNumTimeSamples()
            or size is None
            or not math.isfinite(size)
            or size <= 0
        ):
            raise MissingEvidence("Only static positive cube size is admitted")
        triangles = box([-size / 2] * 3, [size / 2] * 3)
    elif prim.IsA(UsdGeom.Mesh):
        mesh = UsdGeom.Mesh(prim)
        attrs = [
            mesh.GetPointsAttr(),
            mesh.GetFaceVertexCountsAttr(),
            mesh.GetFaceVertexIndicesAttr(),
        ]
        if (
            any(a.GetNumTimeSamples() for a in attrs)
            or mesh.GetSubdivisionSchemeAttr().Get() != "none"
            or mesh.GetHoleIndicesAttr().Get()
        ):
            raise MissingEvidence(
                "Clearance requires static unsubdivided triangle topology without holes"
            )
        points, counts, indices = [a.Get() for a in attrs]
        if (
            points is None
            or counts is None
            or indices is None
            or not len(counts)
            or any(c != 3 for c in counts)
            or len(indices) != 3 * len(counts)
        ):
            raise MissingEvidence("Clearance requires explicit triangular faces")
        if (
            len(points) > 100000
            or len(counts) > 100000
            or any(i < 0 or i >= len(points) for i in indices)
        ):
            raise MissingEvidence("Invalid topology or clearance mesh budget exceeded")
        faces = [list(indices[i : i + 3]) for i in range(0, len(indices), 3)]
        if solid:
            edges = Counter((f[i], f[(i + 1) % 3]) for f in faces for i in range(3))
            if any(n != 1 or edges.get((b, a)) != 1 for (a, b), n in edges.items()):
                raise MissingEvidence(
                    "Closed-solid policy requires a consistently oriented two-manifold mesh"
                )
        triangles = [tuple(Gf.Vec3d(*points[i]) for i in f) for f in faces]
    else:
        raise MissingEvidence("Clearance supports selected Cube or triangle Mesh prims")
    result = [
        tuple(matrix.Transform(p) * units for p in triangle) for triangle in triangles
    ]
    for a, b, c in result:
        if (
            not all(math.isfinite(x) for p in (a, b, c) for x in p)
            or Gf.Cross(b - a, c - a).GetLength() <= 1e-15
        ):
            raise MissingEvidence("Non-finite or degenerate triangle")
    return result


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
    if determinant == 0:
        # Coplanar/parallel pairs are handled by edge and point distances.
        return False
    scale = edge1.GetLength() * edge2.GetLength() * direction.GetLength()
    if abs(determinant) <= 1e-14 * scale:
        raise MissingEvidence(
            "Near-parallel triangle intersection is numerically unresolved"
        )
    s = p - a
    u = Gf.Dot(s, h) / determinant
    v = Gf.Dot(direction, Gf.Cross(s, edge1)) / determinant
    t = Gf.Dot(edge2, Gf.Cross(s, edge1)) / determinant
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
    a = read_triangles(ctx.artifact.stage, params["a"], params["time_s"], solid)
    b = read_triangles(ctx.artifact.stage, params["b"], params["time_s"], solid)
    value = distance(a, b, solid, params["max_triangle_pairs"])
    margin = params["numeric_margin_m"]
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


def zone(ctx, params):
    lo, hi = params["zone_min_m"], params["zone_max_m"]
    if any(a >= b for a, b in zip(lo, hi)):
        raise ContractError("Clear-height zone bounds must increase on every axis")
    target = box(lo, hi)
    rows = []
    for path in params["obstacles"]:
        triangles = read_triangles(ctx.artifact.stage, path, params["time_s"], True)
        value = distance(triangles, target, True, params["max_triangle_pairs"])
        rows.append(
            dict(
                path=path,
                distance_m=value,
                status=(
                    "FAIL"
                    if value == 0
                    else "UNKNOWN" if value <= params["numeric_margin_m"] else "PASS"
                ),
            )
        )
    statuses = {r["status"] for r in rows}
    return Outcome(
        (
            "FAIL"
            if "FAIL" in statuses
            else "UNKNOWN" if "UNKNOWN" in statuses else "PASS"
        ),
        "Checked caller-named obstacles against the declared world-space clear volume.",
        dict(
            findings=rows,
            zone_min_m=lo,
            zone_max_m=hi,
            time_s=params["time_s"],
            coverage="Named obstacles only; the caller must include every relevant obstacle. Stage axes, metres; no navigation or reachability inference.",
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
        "1.0.0",
        "Triangle clearance, clear volumes and bounded translating sweeps",
        {
            "distance": CheckSpec(
                static,
                obj({**common, "time_s": {"type": "number", "minimum": 0}}),
                "Measure mesh or cube clearance",
                "Selected surfaces at a named time",
                (
                    "Closed solids must be consistently oriented and free of self-intersections.",
                ),
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
            ),
            "clear_zone": CheckSpec(
                zone,
                obj(
                    {
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
                    }
                ),
                "Check a clear-height volume",
                "Caller-selected obstacles and world-space box",
                ("A clear list is not proof that the caller named every obstacle.",),
            ),
        },
        (
            str(Path(__file__)),
            str(Path(__file__).with_name("continuous_motion.py")),
            str(Path(__file__).with_name("motion_timing.py")),
        ),
        ("usd-core",),
    )
