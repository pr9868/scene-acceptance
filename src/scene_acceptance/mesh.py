"""Static polygon readback. Native index validation is necessary, not task acceptance."""

import math
from collections import defaultdict
from pxr import UsdGeom, Gf
from .model import MissingEvidence, BoundaryError

LIMITS = (250_000, 250_000, 1_000_000)


def world_points(scene, prim, points):
    matrix = scene.xforms.GetLocalToWorldTransform(prim)
    flat = [float(matrix[i][j]) for i in range(4) for j in range(4)]
    if not all(math.isfinite(x) for x in flat):
        raise MissingEvidence("Non-finite transform")
    if (
        any(abs(matrix[i][3]) > 1e-12 for i in range(3))
        or abs(matrix[3][3] - 1) > 1e-12
    ):
        raise MissingEvidence("Non-affine transform")
    determinant = matrix.GetDeterminant()
    if not math.isfinite(determinant) or determinant == 0:
        raise MissingEvidence("Singular or non-finite transform")
    if not math.isfinite(scene.units) or scene.units <= 0:
        raise MissingEvidence("Invalid stage units")
    values = [list(matrix.Transform(Gf.Vec3d(*p)) * scene.units) for p in points]
    if not all(math.isfinite(x) for p in values for x in p):
        raise MissingEvidence("Non-finite transformed points")
    return values


def read_mesh(scene, prim):
    path = str(prim.GetPath())
    mesh = UsdGeom.Mesh(prim)
    if mesh.GetSubdivisionSchemeAttr().Get() != UsdGeom.Tokens.none:
        raise MissingEvidence(
            "Mesh subdivision is outside the polygon profile; require subdivisionScheme = none"
        )
    if mesh.GetHoleIndicesAttr().Get():
        raise MissingEvidence("Mesh holeIndices are outside this profile")
    points = mesh.GetPointsAttr().Get()
    counts = mesh.GetFaceVertexCountsAttr().Get()
    indices = mesh.GetFaceVertexIndicesAttr().Get()
    if points is None or counts is None or indices is None:
        raise MissingEvidence(
            "Mesh points, faceVertexCounts and faceVertexIndices are required"
        )
    for i, array in enumerate((points, counts, indices)):
        scene.mesh_sizes[i] += len(array)
        if scene.mesh_sizes[i] > LIMITS[i]:
            raise BoundaryError("Mesh stage point/face/index resource limit exceeded")
    stats = dict(
        point_count=len(points), face_count=len(counts), index_count=len(indices)
    )
    scene.mesh_stats[path] = stats
    valid, reason = UsdGeom.Mesh.ValidateTopology(indices, counts, len(points))
    stats["native_topology"] = dict(valid=valid, reason=reason)
    errors = []
    if not valid:
        errors.append(reason)
    if not points or not counts or not indices:
        errors.append("Empty mesh geometry")
    if not all(math.isfinite(x) for p in points for x in p):
        errors.append("Non-finite point coordinates")
    if any(n < 3 for n in counts):
        errors.append("Every face must have at least three vertices")
    if errors:
        scene.mesh_issues[path] = errors
        return
    faces = []
    edges = defaultdict(list)
    cursor = 0
    for face_id, count in enumerate(counts):
        face = list(indices[cursor : cursor + count])
        cursor += count
        faces.append(face)
        if len(set(face)) != count:
            errors.append(f"Face {face_id}: repeated vertex index")
        # Translation-independent normalized vector area. No triangulation/convexity claim.
        origin = points[face[0]]
        local = [Gf.Vec3d(*points[i]) - Gf.Vec3d(*origin) for i in face]
        scale = max(abs(x) for p in local for x in p)
        if scale == 0:
            errors.append(f"Face {face_id}: zero area")
        else:
            normalized = [p / scale for p in local]
            area = Gf.Vec3d(0)
            for a, b in zip(normalized, normalized[1:] + normalized[:1]):
                area += Gf.Cross(a, b)
            if area.GetLength() <= 1e-12:
                errors.append(f"Face {face_id}: zero/canceling vector area")
        for a, b in zip(face, face[1:] + face[:1]):
            edges[tuple(sorted((a, b)))].append((a, b))
    bad_edges = [
        edge
        for edge, uses in edges.items()
        if len(uses) != 2 or uses[0] != uses[1][::-1]
    ]
    stats.update(
        closed_consistent_edges=not bad_edges,
        nonclosing_or_inconsistent_edge_count=len(bad_edges),
        edge_examples=[list(x) for x in bad_edges[:20]],
    )
    used = sorted(set(indices))
    stats["unused_point_count"] = len(points) - len(used)
    if errors:
        scene.mesh_issues[path] = errors[:50]
        stats["violation_count"] = len(errors)
        return
    values = world_points(scene, prim, points)
    lo = [min(values[v][i] for v in used) for i in range(3)]
    hi = [max(values[v][i] for v in used) for i in range(3)]
    color = mesh.GetDisplayColorAttr().Get()
    box = dict(
        min=lo,
        max=hi,
        center=[(a + b) / 2 for a, b in zip(lo, hi)],
        dimensions=[b - a for a, b in zip(lo, hi)],
        display_color=[list(v) for v in color] if color is not None else None,
    )
    scene.meshes[path] = box
    scene.geometry[path] = box
    scene.shapes[path] = dict(
        kind="Mesh", points=values, face_counts=list(counts), face_indices=list(indices)
    )
