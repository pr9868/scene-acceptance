"""Read-only scene geometry; conversions never modify authored layers."""

from collections import Counter
from dataclasses import dataclass
import math
from pxr import Gf, Usd, UsdGeom
from .model import MissingEvidence
from .continuous_motion import matrix_at
from .motion_timing import read_clock

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


@dataclass
class Geometry:
    triangles: list
    error_m: float = 0.0
    method: str = "authored-triangles"

    def bounds(self):
        return (
            [min(p[i] for t in self.triangles for p in t) for i in range(3)],
            [max(p[i] for t in self.triangles for p in t) for i in range(3)],
        )


def triangulate(points, face):
    """Ear clipping of a simple planar polygon; refuse ambiguous geometry."""
    if len(face) == 3:
        return [face]
    if len(face) > 256:
        raise MissingEvidence("Polygon exceeds 256-vertex triangulation budget")
    vertices = [Gf.Vec3d(*points[i]) for i in face]
    normal = sum(
        (Gf.Cross(a, b) for a, b in zip(vertices, vertices[1:] + vertices[:1])),
        Gf.Vec3d(0),
    )
    scale = max((p - vertices[0]).GetLength() for p in vertices)
    if normal.GetLength() <= 1e-14 * max(scale * scale, 1e-30):
        raise MissingEvidence("Degenerate polygon")
    normal.Normalize()
    if any(
        abs(Gf.Dot(p - vertices[0], normal)) > max(scale, 1e-9) * 1e-10
        for p in vertices
    ):
        raise MissingEvidence("Nonplanar polygon requires caller-supplied tessellation")
    axes = [i for i in range(3) if i != max(range(3), key=lambda i: abs(normal[i]))]
    v = [(p[axes[0]], p[axes[1]]) for p in vertices]

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(v, v[1:] + v[:1]))
    sign = 1 if area > 0 else -1
    eps = max(scale * scale, 1e-30) * 1e-12

    def on(a, b, p):
        return abs(cross(a, b, p)) <= eps and all(
            min(a[i], b[i]) - 1e-12 * scale <= p[i] <= max(a[i], b[i]) + 1e-12 * scale
            for i in (0, 1)
        )

    for i in range(len(v)):
        for j in range(i + 1, len(v)):
            if j in (i, (i + 1) % len(v)) or i == (j + 1) % len(v):
                continue
            a, b = v[i], v[(i + 1) % len(v)]
            c, d = v[j], v[(j + 1) % len(v)]
            if (
                cross(a, b, c) * cross(a, b, d) < 0
                and cross(c, d, a) * cross(c, d, b) < 0
                or any((on(a, b, c), on(a, b, d), on(c, d, a), on(c, d, b)))
            ):
                raise MissingEvidence("Self-intersecting polygon")
    remaining = list(range(len(v)))
    triangles = []
    while len(remaining) > 3:
        for k, i in enumerate(remaining):
            a = remaining[k - 1]
            b = remaining[(k + 1) % len(remaining)]
            if sign * cross(v[a], v[i], v[b]) <= eps:
                continue
            if any(
                all(
                    sign * cross(x, y, v[j]) >= -eps
                    for x, y in [(v[a], v[i]), (v[i], v[b]), (v[b], v[a])]
                )
                for j in remaining
                if j not in (a, i, b)
            ):
                continue
            triangles.append([face[a], face[i], face[b]])
            remaining.pop(k)
            break
        else:
            raise MissingEvidence(
                "Polygon triangulation could not establish a valid ear"
            )
    triangles.append([face[i] for i in remaining])
    actual = sum(
        abs(cross(v[face.index(a)], v[face.index(b)], v[face.index(c)]))
        for a, b, c in triangles
    )
    if abs(actual - abs(area)) > max(abs(area), 1e-30) * 1e-9:
        raise MissingEvidence("Polygon area preservation failed")
    return triangles


def read_triangles(stage, path, seconds, solid):
    return read_geometry(stage, path, seconds, solid, allow_implicit=False).triangles


def read_geometry(
    stage, path, seconds, solid, *, allow_implicit=True, approximation_m=0.001
):
    prim = stage.GetPrimAtPath(path)
    if not prim:
        raise MissingEvidence("Missing clearance subject: " + path)
    # Rest points are not evaluated skinning/blend-shape geometry. Bindings can
    # be inherited, so inspect the composed ancestor chain as well as the mesh.
    current = prim
    while current and not current.IsPseudoRoot():
        for prop in current.GetAuthoredProperties():
            if prop.GetName().startswith(("skel:", "primvars:skel:")):
                raise MissingEvidence(
                    "Clearance does not evaluate skinning or blend-shape bindings; "
                    "supply baked geometry: " + str(prop.GetPath())
                )
        current = current.GetParent()
    clock = read_clock(stage)
    matrix = matrix_at(stage, path, clock, seconds)
    units = UsdGeom.GetStageMetersPerUnit(stage)
    if (
        not stage.HasAuthoredMetadata("metersPerUnit")
        or not math.isfinite(units)
        or units <= 0
    ):
        raise MissingEvidence("Clearance requires authored positive stage units")
    method = "authored-triangles"
    error = 0.0
    if prim.IsA(UsdGeom.Cube):
        attr = UsdGeom.Cube(prim).GetSizeAttr()
        size = attr.Get()
        if (
            attr.GetNumTimeSamples()
            or attr.HasSpline()
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
            any(
                a.GetNumTimeSamples() or a.HasSpline()
                for a in [
                    *attrs,
                    mesh.GetSubdivisionSchemeAttr(),
                    mesh.GetHoleIndicesAttr(),
                ]
            )
            or mesh.GetSubdivisionSchemeAttr().Get() != "none"
            or mesh.GetHoleIndicesAttr().Get()
        ):
            raise MissingEvidence(
                "Clearance requires static unsubdivided polygon topology without holes"
            )
        points, counts, indices = [a.Get() for a in attrs]
        if (
            points is None
            or counts is None
            or indices is None
            or not len(counts)
            or any(c < 3 for c in counts)
            or len(indices) != sum(counts)
        ):
            raise MissingEvidence("Clearance requires explicit valid polygon faces")
        if (
            len(points) > 100000
            or len(counts) > 100000
            or sum(c - 2 for c in counts) > 100000
            or any(i < 0 or i >= len(points) for i in indices)
        ):
            raise MissingEvidence("Invalid topology or clearance mesh budget exceeded")
        faces = []
        offset = 0
        for count in counts:
            faces.extend(triangulate(points, list(indices[offset : offset + count])))
            offset += count
        method = (
            "planar-polygon-triangulation" if any(c != 3 for c in counts) else method
        )
        if solid:
            edges = Counter((f[i], f[(i + 1) % 3]) for f in faces for i in range(3))
            if any(n != 1 or edges.get((b, a)) != 1 for (a, b), n in edges.items()):
                raise MissingEvidence(
                    "Closed-solid policy requires a consistently oriented two-manifold mesh"
                )
        triangles = [tuple(Gf.Vec3d(*points[i]) for i in f) for f in faces]
    elif allow_implicit and (prim.IsA(UsdGeom.Cylinder) or prim.IsA(UsdGeom.Sphere)):
        shape = (
            UsdGeom.Cylinder(prim)
            if prim.IsA(UsdGeom.Cylinder)
            else UsdGeom.Sphere(prim)
        )
        attrs = [shape.GetRadiusAttr()]
        if isinstance(shape, UsdGeom.Cylinder):
            attrs += [shape.GetHeightAttr(), shape.GetAxisAttr()]
        if any(a.GetNumTimeSamples() or a.HasSpline() for a in attrs):
            raise MissingEvidence(
                "Animated implicit dimensions are unsupported: " + path
            )
        radius = shape.GetRadiusAttr().Get()
        if not radius or not math.isfinite(radius) or radius <= 0:
            raise MissingEvidence("Invalid implicit radius: " + path)
        # Frobenius norm bounds world-space amplification under affine transforms.
        gain = (
            math.sqrt(sum(matrix[i][j] ** 2 for i in range(3) for j in range(3)))
            * units
        )
        if not math.isfinite(gain) or gain <= 0:
            raise MissingEvidence("Invalid implicit transform: " + path)
        if not math.isfinite(approximation_m) or approximation_m <= 0:
            raise MissingEvidence("Approximation budget must be positive")
        if isinstance(shape, UsdGeom.Cylinder):
            h = shape.GetHeightAttr().Get()
            axis = str(shape.GetAxisAttr().Get())
            if axis not in ("X", "Y", "Z"):
                raise MissingEvidence("Invalid cylinder axis: " + path)
            if not h or not math.isfinite(h) or h <= 0:
                raise MissingEvidence("Invalid cylinder height: " + path)
            n = 8
            while (
                radius * (1 - math.cos(math.pi / n)) * gain > approximation_m
                and n < 512
            ):
                n *= 2
            error = radius * (1 - math.cos(math.pi / n)) * gain
            if error > approximation_m:
                raise MissingEvidence("Cylinder approximation budget exceeded: " + path)

            def xyz(x, y, z):
                return Gf.Vec3d(
                    (z, x, y)
                    if axis == "X"
                    else (y, z, x) if axis == "Y" else (x, y, z)
                )

            rings = [
                [
                    xyz(
                        radius * math.cos(2 * math.pi * i / n),
                        radius * math.sin(2 * math.pi * i / n),
                        z,
                    )
                    for i in range(n)
                ]
                for z in (-h / 2, h / 2)
            ]
            triangles = []
            for i in range(n):
                j = (i + 1) % n
                a, b = rings[0][i], rings[0][j]
                c, d = rings[1][i], rings[1][j]
                triangles.extend(
                    [
                        (a, b, d),
                        (a, d, c),
                        (xyz(0, 0, -h / 2), b, a),
                        (xyz(0, 0, h / 2), c, d),
                    ]
                )
        else:
            # Subdivide an inscribed octahedron. Each face's radial deficit bounds
            # its distance to the spherical patch; affine gain makes it world-space.
            vertices = [
                Gf.Vec3d(*v)
                for v in [
                    (1, 0, 0),
                    (-1, 0, 0),
                    (0, 1, 0),
                    (0, -1, 0),
                    (0, 0, 1),
                    (0, 0, -1),
                ]
            ]
            triangles = [
                tuple(vertices[i] * radius for i in f)
                for f in [
                    (0, 2, 4),
                    (2, 1, 4),
                    (1, 3, 4),
                    (3, 0, 4),
                    (2, 0, 5),
                    (1, 2, 5),
                    (3, 1, 5),
                    (0, 3, 5),
                ]
            ]
            for level in range(7):
                error = (
                    max(
                        radius - abs(Gf.Dot(Gf.Cross(b - a, c - a).GetNormalized(), a))
                        for a, b, c in triangles
                    )
                    * gain
                )
                if error <= approximation_m:
                    break
                if level == 6:
                    raise MissingEvidence(
                        "Sphere approximation budget exceeded: " + path
                    )
                refined = []
                for a, b, c in triangles:
                    ab = (a + b).GetNormalized() * radius
                    bc = (b + c).GetNormalized() * radius
                    ca = (c + a).GetNormalized() * radius
                    refined.extend(
                        [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
                    )
                triangles = refined
        method = "inscribed-implicit-tessellation"
    else:
        raise MissingEvidence(
            "Clearance supports Cube, planar Mesh and selected implicit shapes: " + path
        )
    result = [
        tuple(matrix.Transform(p) * units for p in triangle) for triangle in triangles
    ]
    for a, b, c in result:
        if (
            not all(math.isfinite(x) for p in (a, b, c) for x in p)
            or Gf.Cross(b - a, c - a).GetLength() <= 1e-15
        ):
            raise MissingEvidence("Non-finite or degenerate triangle")
    return Geometry(result, error, method)
