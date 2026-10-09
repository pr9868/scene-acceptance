"""Task-specific readbacks. Targets and tolerances are in the frozen PROTOCOL.md."""

from scene_acceptance.usd_composition import prims as composed_prims
from pathlib import Path
from collections import defaultdict
import math
import numpy as np
from PIL import Image
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf
from scene_acceptance.packs import Outcome
from scene_acceptance.model import MissingEvidence

EPS = 1e-6


def observation(ok, reason, **evidence):
    return Outcome("PASS" if ok else "FAIL", reason, evidence)


def close(actual, expected, tolerance=EPS):
    return bool(
        np.max(
            np.abs(np.asarray(actual, dtype=float) - np.asarray(expected, dtype=float))
        )
        <= tolerance
    )


def prim(stage, path):
    p = stage.GetPrimAtPath(path)
    if not p:
        raise MissingEvidence("Required prim absent: " + path)
    return p


def matrix(stage, path, time=Usd.TimeCode.Default()):
    return UsdGeom.XformCache(time).GetLocalToWorldTransform(prim(stage, path))


def fields(layer, ignore=()):
    result = {}

    def visit(path):
        spec = layer.GetObjectAtPath(path)
        if spec is not None:
            result[str(path)] = {
                k: repr(spec.GetInfo(k))
                for k in sorted(spec.ListInfoKeys())
                if (str(path), k) not in ignore
            }

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    return result


def diff_fields(a, b):
    return [p for p in sorted(set(a) | set(b)) if a.get(p) != b.get(p)]


def mesh_data(p):
    m = UsdGeom.Mesh(p)
    if not m:
        raise MissingEvidence("Expected Mesh at " + str(p.GetPath()))
    points = np.asarray(m.GetPointsAttr().Get(), dtype=float)
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or not len(points)
        or not np.all(np.isfinite(points))
    ):
        raise MissingEvidence("Mesh needs finite authored points")
    counts = list(m.GetFaceVertexCountsAttr().Get() or [])
    ids = list(m.GetFaceVertexIndicesAttr().Get() or [])
    valid, reason = UsdGeom.Mesh.ValidateTopology(ids, counts, len(points))
    if not valid or not counts or any(n < 3 for n in counts):
        raise MissingEvidence("Invalid mesh topology: " + reason)
    faces = []
    start = 0
    edges = defaultdict(list)
    for n in counts:
        f = ids[start : start + n]
        start += n
        faces.append(f)
        for a, b in zip(f, f[1:] + f[:1]):
            edges[tuple(sorted((a, b)))].append((a, b))
    triangles = [
        points[[f[0], f[i], f[i + 1]]] for f in faces for i in range(1, len(f) - 1)
    ]
    return m, points, faces, triangles, edges


def area2(poly):
    if len(poly) < 3:
        return 0.0
    p = np.asarray(poly)
    return (
        abs(
            float(
                np.sum(p[:, 0] * np.roll(p[:, 1], -1) - p[:, 1] * np.roll(p[:, 0], -1))
            )
        )
        / 2
    )


def clip_rectangle(poly, bounds):
    poly = [np.asarray(v, dtype=float) for v in poly]
    for axis, bound, sign in [
        (0, bounds[0], 1),
        (0, bounds[1], -1),
        (1, bounds[2], 1),
        (1, bounds[3], -1),
    ]:
        output = []
        if not poly:
            return []
        for a, b in zip(poly, poly[1:] + poly[:1]):
            ina = sign * (a[axis] - bound) >= 0
            inb = sign * (b[axis] - bound) >= 0
            if ina:
                output.append(a)
            if ina != inb:
                output.append(a + (b - a) * ((bound - a[axis]) / (b[axis] - a[axis])))
        poly = output
    return poly


def common(stage, selected):
    metadata = stage.HasAuthoredMetadata("metersPerUnit") and stage.HasAuthoredMetadata(
        "upAxis"
    )
    metadata = (
        metadata
        and UsdGeom.GetStageMetersPerUnit(stage) == 1
        and UsdGeom.GetStageUpAxis(stage) == "Z"
        and bool(stage.GetDefaultPrim())
    )
    if selected == "common.metadata":
        return observation(
            metadata,
            "Authored metre/Z-up metadata and default prim read through OpenUSD.",
            meters_per_unit=UsdGeom.GetStageMetersPerUnit(stage),
            up_axis=str(UsdGeom.GetStageUpAxis(stage)),
            default_prim=str(stage.GetDefaultPrim().GetPath()),
        )
    issues = []
    geometry = []

    def finite(v):
        if isinstance(v, (float, int)):
            return math.isfinite(v)
        if isinstance(v, (str, bytes, Sdf.AssetPath)) or v is None:
            return True
        try:
            return all(finite(x) for x in v)
        except TypeError:
            return True

    for p in composed_prims(stage):
        if p.IsA(UsdGeom.Gprim):
            geometry.append({"path": str(p.GetPath()), "type": p.GetTypeName()})
            if not (p.IsA(UsdGeom.Mesh) or p.IsA(UsdGeom.Cube)):
                issues.append(str(p.GetPath()) + ": unsupported geometry type")
        if p.IsA(UsdGeom.Mesh):
            m = UsdGeom.Mesh(p)
            pts = m.GetPointsAttr().Get() or []
            counts = m.GetFaceVertexCountsAttr().Get() or []
            ids = m.GetFaceVertexIndicesAttr().Get() or []
            valid, reason = UsdGeom.Mesh.ValidateTopology(ids, counts, len(pts))
            if not valid or m.GetSubdivisionSchemeAttr().Get() != "none":
                issues.append(str(p.GetPath()) + ": " + reason + " / subdivision")
        for a in p.GetAuthoredAttributes():
            for t in [Usd.TimeCode.Default(), *map(Usd.TimeCode, a.GetTimeSamples())]:
                if not finite(a.Get(t)):
                    issues.append(str(a.GetPath()) + ": non-finite")
    return observation(
        not issues,
        "Geometry types, native mesh indices, subdivision and authored numeric values inspected.",
        issues=issues,
        geometry=geometry,
    )


def tray(stage, selected, baseline=None):
    if selected == "tray.preserved":
        if baseline is None:
            raise MissingEvidence("The translated tray requires an admitted baseline")
        changes = diff_fields(
            fields(
                baseline.GetRootLayer(), [("/World/Tray.xformOp:translate", "default")]
            ),
            fields(
                stage.GetRootLayer(), [("/World/Tray.xformOp:translate", "default")]
            ),
        )
        return observation(
            not changes,
            "Every root-layer authored field compared except the tray translation default.",
            changed_spec_paths=changes,
        )
    if selected == "tray.transform":
        xform = matrix(stage, "/World/Tray")
        expected_x = 0.4 if baseline else 0
        target = Gf.Matrix4d(1)
        target.SetTranslate(Gf.Vec3d(expected_x, 0, 0))
        return observation(
            close(np.array(xform), np.array(target)),
            "World tray transform compared with the requested baseline/edit.",
            matrix=np.asarray(xform).tolist(),
            expected_translation_m=[expected_x, 0, 0],
        )
    if selected == "tray.fixture":
        fp = prim(stage, "/World/Fixture")
        bbox = (
            UsdGeom.BBoxCache(
                Usd.TimeCode.Default(),
                ["default", "render", "proxy"],
                useExtentsHint=False,
            )
            .ComputeWorldBound(fp)
            .ComputeAlignedRange()
        )
        return observation(
            close(list(bbox.GetMin()), [-0.3, -0.04, 0])
            and close(list(bbox.GetMax()), [-0.2, 0.04, 0.04]),
            "Protected fixture world dimensions and centre compared.",
            minimum_m=list(bbox.GetMin()),
            maximum_m=list(bbox.GetMax()),
        )
    p = prim(stage, "/World/Tray")
    m, pts, faces, tris, edges = mesh_data(p)
    lo = pts.min(axis=0)
    hi = pts.max(axis=0)
    if selected == "tray.dimensions":
        return observation(
            close(lo, [-0.15, -0.1, 0]) and close(hi, [0.15, 0.1, 0.08]),
            "Local outer extents compared.",
            minimum_m=lo.tolist(),
            maximum_m=hi.tolist(),
        )
    bad_edges = [list(k) for k, v in edges.items() if len(v) != 2 or v[0] != v[1][::-1]]
    # Each allowed plane has an outward normal and a rectangular projection.
    surfaces = [
        ("bottom", 2, 0, -1, (-0.15, 0.15, -0.1, 0.1), 0.06),
        ("floor", 2, 0.01, 1, (-0.14, 0.14, -0.09, 0.09), 0.0504),
        ("rim", 2, 0.08, 1, (-0.15, 0.15, -0.1, 0.1), 0.0096),
    ]
    for sign in [-1, 1]:
        surfaces += [
            (f"outer-x-{sign}", 0, sign * 0.15, sign, (-0.1, 0.1, 0, 0.08), 0.016),
            (f"outer-y-{sign}", 1, sign * 0.1, sign, (-0.15, 0.15, 0, 0.08), 0.024),
            (
                f"inner-x-{sign}",
                0,
                sign * 0.14,
                -sign,
                (-0.09, 0.09, 0.01, 0.08),
                0.0126,
            ),
            (
                f"inner-y-{sign}",
                1,
                sign * 0.09,
                -sign,
                (-0.14, 0.14, 0.01, 0.08),
                0.0196,
            ),
        ]
    areas = {s[0]: 0.0 for s in surfaces}
    issues = []
    volume = 0.0
    handed = -1 if m.GetOrientationAttr().Get() == "leftHanded" else 1
    for i, t in enumerate(tris):
        cross = np.cross(t[1] - t[0], t[2] - t[0]) * handed
        area = float(np.linalg.norm(cross)) / 2
        volume += float(np.dot(t[0], np.cross(t[1], t[2]))) * handed / 6
        matched = False
        for name, axis, value, sign, bounds, _ in surfaces:
            if np.max(np.abs(t[:, axis] - value)) > EPS:
                continue
            projected = t[:, [k for k in range(3) if k != axis]]
            contained = abs(area2(clip_rectangle(projected, bounds)) - area) < 1e-8
            hole = (
                area2(clip_rectangle(projected, (-0.14, 0.14, -0.09, 0.09)))
                if name == "rim"
                else 0
            )
            correct_normal = area > 1e-12 and cross[axis] * sign / (2 * area) > 1 - 1e-8
            if contained and hole < 1e-8 and correct_normal:
                areas[name] += area
                matched = True
                break
        if not matched:
            issues.append({"triangle": i, "points": t.tolist(), "area_m2": area})
    area_errors = {
        name: areas[name] - expected for name, _, _, _, _, expected in surfaces
    }
    if selected == "tray.cavity":
        return observation(
            not issues and all(abs(x) < 1e-7 for x in area_errors.values()),
            "Triangle surface coverage compared with the specified ideal cavity, walls, bottom and open rim.",
            surface_areas_m2=areas,
            area_errors_m2=area_errors,
            unmatched_triangles=issues,
            triangle_count=len(tris),
            coverage="Axis-aligned polygon construction; no general self-intersection or manufacturing certificate",
        )
    return observation(
        not bad_edges and abs(volume - 0.001272) < 1e-8,
        "Directed edge closure and signed material volume compared.",
        bad_edges=bad_edges,
        signed_volume_m3=volume,
        expected_volume_m3=0.001272,
    )


def panel(stage, bundle, kind, selected):
    if selected == "panel.pixels":
        expected = np.empty((256, 256, 3), dtype=np.uint8)
        for (y, x), color in zip(
            [(0, 0), (0, 128), (128, 0), (128, 128)],
            [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)],
        ):
            expected[y : y + 128, x : x + 128] = color
        expected_file = "textures/label.png" if kind == "png" else "textures/label.jpg"
        path = bundle.record(expected_file, missing=True)
        if path.stat().st_size > 1048576:
            raise MissingEvidence("Image exceeds the four-job 1 MiB budget")
        try:
            with Image.open(path) as im:
                if im.width * im.height > 65536:
                    raise MissingEvidence(
                        "Image exceeds the four-job 65536-pixel budget"
                    )
                im.load()
                info = {
                    "format": im.format,
                    "mode": im.mode,
                    "size": list(im.size),
                    "frames": getattr(im, "n_frames", 1),
                }
                arr = np.asarray(im)
            properties = (
                info["format"] == ("PNG" if kind == "png" else "JPEG")
                and info["mode"] == "RGB"
                and info["size"] == [256, 256]
                and info["frames"] == 1
            )
            if properties:
                delta = np.abs(arr.astype(int) - expected.astype(int))
                mask = np.ones((256, 256), bool)
                mask[120:136, :] = False
                mask[:, 120:136] = False
                stats = {
                    "whole_max_channel_error": int(delta.max()),
                    "interior_max_channel_error": int(delta[mask].max()),
                    "interior_mean_channel_error": delta[mask].mean(axis=0).tolist(),
                    "mismatching_pixels": int(np.any(delta != 0, axis=2).sum()),
                }
                pixels = (
                    bool(np.all(delta == 0))
                    if kind == "png"
                    else stats["interior_max_channel_error"] <= 32
                    and max(stats["interior_mean_channel_error"]) <= 4
                )
            else:
                stats = {}
                pixels = False
            image_result = observation(
                properties and pixels,
                "Decoded image compared with the declared quadrant pattern and format policy.",
                **info,
                **stats,
            )
        except MissingEvidence:
            raise
        except Exception as exc:
            image_result = observation(False, "Image readback failed: " + str(exc))
        return image_result
    if selected == "panel.equivalence":
        refpath = bundle.record("reference.usda", missing=True)
        ref = Sdf.Layer.FindOrOpen(str(refpath))
        if ref is None:
            raise MissingEvidence("Reference USD layer could not be opened")
        changes = diff_fields(
            fields(ref, [("/World/Looks/Label/Texture.inputs:file", "default")]),
            fields(
                stage.GetRootLayer(),
                [("/World/Looks/Label/Texture.inputs:file", "default")],
            ),
        )
        return observation(
            not changes,
            "PNG/JPEG sibling root-layer fields compared except the image filename.",
            changed_spec_paths=changes,
        )
    if selected == "panel.shader":
        texture = prim(stage, "/World/Looks/Label/Texture")
        asset = texture.GetAttribute("inputs:file").Get()
        expected_file = "textures/label.png" if kind == "png" else "textures/label.jpg"
        file_ok = isinstance(asset, Sdf.AssetPath) and asset.path == expected_file
        graph_issues = []
        if texture.GetAttribute("info:id").Get() != "UsdUVTexture":
            graph_issues.append("Texture is not UsdUVTexture")
        material = UsdShade.Material(prim(stage, "/World/Looks/Label"))
        surface = material.ComputeSurfaceSource()[0]
        if not surface or surface.GetIdAttr().Get() != "UsdPreviewSurface":
            graph_issues.append("Surface is not UsdPreviewSurface")
        elif [
            str(x) for x in surface.GetInput("diffuseColor").GetAttr().GetConnections()
        ] != ["/World/Looks/Label/Texture.outputs:rgb"]:
            graph_issues.append("Wrong diffuse connection")
        connection = texture.GetAttribute("inputs:st").GetConnections()
        if len(connection) != 1:
            graph_issues.append("Expected one texture-coordinate connection")
        else:
            reader = UsdShade.Shader(stage.GetPrimAtPath(connection[0].GetPrimPath()))
            if (
                not reader
                or reader.GetIdAttr().Get() != "UsdPrimvarReader_float2"
                or reader.GetInput("varname").Get() != "st"
                or connection[0].name != "outputs:result"
            ):
                graph_issues.append(
                    "Texture-coordinate reader does not read st into result"
                )
        return observation(
            file_ok and not graph_issues,
            "Named texture asset and connected shader/primvar graph inspected.",
            asset=str(asset),
            issues=graph_issues,
        )
    m, pts, faces, tris, _ = mesh_data(prim(stage, "/World/Panel"))
    world = np.asarray(
        [matrix(stage, "/World/Panel").Transform(Gf.Vec3d(*p)) for p in pts]
    )
    world_tris = [
        world[[f[0], f[i], f[i + 1]]] for f in faces for i in range(1, len(f) - 1)
    ]
    area = sum(
        float(np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0]))) / 2
        for t in world_tris
    )
    # The brief fixes size and the Z=0 plane, but deliberately leaves the X/Y anchor open.
    shape = (
        close(world.max(axis=0) - world.min(axis=0), [0.24, 0.16, 0])
        and np.max(np.abs(world[:, 2])) <= EPS
        and abs(area - 0.0384) < 1e-7
    )
    if selected == "panel.dimensions":
        return observation(
            shape,
            "World panel dimensions, Z=0 plane and polygon area compared; X/Y anchor is discretionary.",
            minimum_m=world.min(axis=0).tolist(),
            maximum_m=world.max(axis=0).tolist(),
            area_m2=area,
        )
    uv = UsdGeom.PrimvarsAPI(m).GetPrimvar("st")
    uv_points = np.asarray(uv.ComputeFlattened() if uv else [], dtype=float)
    interp = str(uv.GetInterpolation()) if uv else ""
    uv_ok = uv_points.ndim == 2 and uv_points.shape[1] == 2
    uv_area = 0.0
    index = 0
    if uv_ok:
        if interp in ("vertex", "varying") and len(uv_points) == len(pts):
            uv_faces = [uv_points[f] for f in faces]
        elif interp == "faceVarying" and len(uv_points) == sum(map(len, faces)):
            uv_faces = []
            for f in faces:
                uv_faces.append(uv_points[index : index + len(f)])
                index += len(f)
        else:
            uv_ok = False
            uv_faces = []
        uv_area = sum(area2(p) for p in uv_faces)
        uv_ok = (
            uv_ok
            and np.all(np.isfinite(uv_points))
            and close(uv_points.min(axis=0), [0, 0])
            and close(uv_points.max(axis=0), [1, 1])
            and abs(uv_area - 1) < EPS
        )
        # For this rectangular handoff, require an affine full-panel mapping.
        if uv_ok:
            if interp == "faceVarying":
                xy = np.concatenate([pts[f, :2] for f in faces])
            else:
                xy = pts[:, :2]
            design = np.column_stack([xy, np.ones(len(xy))])
            coeff = np.linalg.lstsq(design, uv_points, rcond=None)[0]
            uv_ok = bool(
                np.max(np.abs(design @ coeff - uv_points)) <= EPS
                and abs(np.linalg.det(coeff[:2])) > EPS
            )
    return observation(
        uv_ok,
        "Flattened st coordinates, interpolation, area and affine panel coverage inspected.",
        interpolation=interp,
        uv=uv_points.tolist(),
        uv_area=uv_area,
        coverage="Authored UV mapping; renderer/image orientation is not observed",
    )


def motion(stage, selected):
    if selected == "motion.clock":
        return observation(
            stage.GetStartTimeCode() == 12
            and stage.GetEndTimeCode() == 156
            and stage.GetTimeCodesPerSecond() == 48
            and all(
                stage.HasAuthoredMetadata(k)
                for k in ("startTimeCode", "endTimeCode", "timeCodesPerSecond")
            ),
            "Exact authored stage interval and rate compared.",
            start=stage.GetStartTimeCode(),
            end=stage.GetEndTimeCode(),
            rate=stage.GetTimeCodesPerSecond(),
        )
    if selected == "motion.geometry":
        visible = {
            name: any(
                p.IsA(UsdGeom.Gprim)
                for p in Usd.PrimRange(prim(stage, "/World/Mechanism/" + name))
            )
            for name in ("Crank", "Rod", "Slider")
        }
        return observation(
            all(visible.values()),
            "Named components contain authored geometry; visibility/rendering is not evaluated.",
            components=visible,
        )
    if not all(
        stage.HasAuthoredMetadata(k)
        for k in ("startTimeCode", "endTimeCode", "timeCodesPerSecond")
    ):
        raise MissingEvidence("Motion readback needs authored clock and range")
    start = stage.GetStartTimeCode()
    rate = stage.GetTimeCodesPerSecond()
    prefix = "/World/Mechanism/"
    paths = {
        k: prim(stage, prefix + p)
        for k, p in [
            ("centre", "Crank"),
            ("crank", "Crank/Pin"),
            ("rod", "Rod"),
            ("slider", "Slider/Pin"),
        ]
    }
    times = sorted(
        set(
            [3 * i / 256 for i in range(257)]
            + [3 * (i + 0.37) / 257 for i in range(257)]
        )
    )
    rows = []
    for t in times:
        cache = UsdGeom.XformCache(Usd.TimeCode(start + t * rate))
        pos = {
            k: np.array(cache.GetLocalToWorldTransform(p).Transform(Gf.Vec3d(0)), float)
            for k, p in paths.items()
        }
        rodend = np.array(
            cache.GetLocalToWorldTransform(paths["rod"]).Transform(
                Gf.Vec3d(0.14, 0, 0)
            ),
            float,
        )
        angle = math.radians(25) + 2 * math.pi * t / 3
        crank = np.array([0.042 * math.cos(angle), 0.042 * math.sin(angle), 0.1])
        slider = np.array([crank[0] + math.sqrt(0.14**2 - crank[1] ** 2), 0, 0.1])
        row = {
            "elapsed_s": t,
            "crank_pin_m": pos["crank"].tolist(),
            "slider_pin_m": pos["slider"].tolist(),
            "crank_gap_m": float(np.linalg.norm(pos["rod"] - pos["crank"])),
            "slider_gap_m": float(np.linalg.norm(rodend - pos["slider"])),
            "centre_error_m": float(np.linalg.norm(pos["centre"] - [0, 0, 0.1])),
            "radius_error_m": abs(
                float(np.linalg.norm(pos["crank"] - pos["centre"])) - 0.042
            ),
            "rod_length_error_m": abs(
                float(np.linalg.norm(rodend - pos["rod"])) - 0.14
            ),
            "slider_line_error_m": float(np.linalg.norm(pos["slider"][1:] - [0, 0.1])),
            "crank_trajectory_error_m": float(np.linalg.norm(pos["crank"] - crank)),
            "slider_trajectory_error_m": float(np.linalg.norm(pos["slider"] - slider)),
        }
        rows.append(row)
    maxima = {
        key: max(x[key] for x in rows)
        for key in rows[0]
        if key.endswith("error_m") or key.endswith("gap_m")
    }
    loop = max(
        float(np.linalg.norm(np.array(rows[0][k]) - rows[-1][k]))
        for k in ("crank_pin_m", "slider_pin_m")
    )
    angles = np.unwrap(
        [math.atan2(x["crank_pin_m"][1], x["crank_pin_m"][0]) for x in rows]
    )
    cycle_ok = (
        abs(float(angles[0]) - math.radians(25)) <= EPS
        and abs(float(angles[-1] - angles[0]) - 2 * math.pi) <= EPS
        and bool(np.all(np.diff(angles) >= -1e-9))
        and all(x["slider_pin_m"][0] > 0 for x in rows)
    )
    return {
        "motion.clock": observation(
            start == 12 and stage.GetEndTimeCode() == 156 and rate == 48,
            "Exact stage interval and rate compared.",
            start=start,
            end=stage.GetEndTimeCode(),
            rate=rate,
        ),
        "motion.lengths": observation(
            max(
                maxima[k]
                for k in (
                    "centre_error_m",
                    "radius_error_m",
                    "rod_length_error_m",
                    "slider_line_error_m",
                )
            )
            <= EPS,
            "Fixed centre, radius, rod length and slider line compared at two diagnostic grids.",
            maxima_m=maxima,
            sample_count=len(rows),
            samples=rows,
        ),
        "motion.cycle": observation(
            cycle_ok and loop <= EPS,
            "Start phase, sampled counterclockwise progression, positive slider branch and one-cycle closure compared without requiring a uniform angular rate.",
            start_angle_deg=math.degrees(float(angles[0])),
            angle_advance_deg=math.degrees(float(angles[-1] - angles[0])),
            minimum_sampled_angle_step_deg=math.degrees(float(np.diff(angles).min())),
            loop_error_m=loop,
            sample_count=len(rows),
            samples=rows,
        ),
        "motion.trajectory": observation(
            max(
                maxima[k]
                for k in ("crank_trajectory_error_m", "slider_trajectory_error_m")
            )
            <= 0.0005
            and loop <= EPS,
            "Saved pin positions compared with an independently expressed 25-degree, one-revolution, positive-branch crank-slider equation.",
            maxima_m=maxima,
            loop_error_m=loop,
            samples=rows,
        ),
        "motion.connections": observation(
            max(maxima["crank_gap_m"], maxima["slider_gap_m"]) <= 0.0005,
            "Both attachments compared at the pre-production diagnostic schedules.",
            maxima_m=maxima,
            sample_count=len(rows),
            samples=rows,
        ),
    }[selected]


def physics(stage, bundle, mu, selected):
    if selected == "physics.parameters":
        block = prim(stage, "/World/Block")
        contact = prim(stage, "/World/Contact")
        mass = block.GetAttribute("physics:mass").Get()
        static = contact.GetAttribute("physics:staticFriction").Get()
        dynamic = contact.GetAttribute("physics:dynamicFriction").Get()
        if any(v is None for v in (mass, static, dynamic)):
            raise MissingEvidence("Requested mass/friction attribute is absent")
        return observation(
            close([mass, static, dynamic], [1.25, mu, mu]),
            "Requested authored mass and friction read from saved USD.",
            mass_kg=mass,
            static_friction=static,
            dynamic_friction=dynamic,
            expected_friction=mu,
        )
    allowed = [
        ("/World/Block.physics:mass", "default"),
        ("/World/Contact.physics:staticFriction", "default"),
        ("/World/Contact.physics:dynamicFriction", "default"),
    ]
    base = Sdf.Layer.FindOrOpen(str(bundle.record("physics-base.usda", missing=True)))
    if base is None:
        raise MissingEvidence("Physics reference layer could not be opened")
    changed = diff_fields(fields(base, allowed), fields(stage.GetRootLayer(), allowed))
    return observation(
        not changed,
        "All root-layer fields compared against the supplied base except the three requested parameter values.",
        changed_spec_paths=changed,
    )
