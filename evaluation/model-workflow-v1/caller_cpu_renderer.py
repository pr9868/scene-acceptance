#!/usr/bin/env python3
"""Minimal software renderer for caller-supplied views (caller-owned constructed-test helper).

OpenUSD + NumPy + Pillow. Flat Lambert shading, UsdPreviewSurface diffuseColor (constant or
UsdUVTexture via primvars:st), z-buffer, perspective camera. Not photoreal; intended to give the
harness's visual review honest diagnostic views. Supported gprims: Mesh, Cube, Sphere,
Cylinder, Cone. Unsupported gprims are listed in the sidecar JSON, never silently dropped.

Examples:
  render_views.py --scene scene.usda --camera /World/Cameras/Overview --time 0 --out v.png
  render_views.py --scene scene.usda --target /World/Skid/CP_101 --view front --time 0 --out f.png
Views: front(-Y looking +Y) rear left(-X) right top iso. Writes <out>.json with camera, time and
coverage metadata for building capture receipts.
"""

import argparse, json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image
from pxr import Usd, UsdGeom, UsdShade, Gf, Sdf

DIRS = {
    "front": (0, -1, 0.35),
    "rear": (0, 1, 0.35),
    "left": (-1, 0, 0.35),
    "right": (1, 0, 0.35),
    "top": (0.001, -0.001, 1),
    "iso": (1, -1, 0.8),
}


def srgb_to_lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def unit_cube():
    v = np.array(
        [[x, y, z] for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)]
    )
    f = [
        (0, 1, 3, 2),
        (4, 6, 7, 5),
        (0, 4, 5, 1),
        (2, 3, 7, 6),
        (0, 2, 6, 4),
        (1, 5, 7, 3),
    ]
    tris = [(a, b, c) for (a, b, c, d) in f] + [(a, c, d) for (a, b, c, d) in f]
    return v, np.array(tris)


def sphere(r, n=16):
    pts, tris = [], []
    for i in range(n + 1):
        th = math.pi * i / n
        for j in range(n * 2):
            ph = 2 * math.pi * j / (n * 2)
            pts.append(
                (
                    r * math.sin(th) * math.cos(ph),
                    r * math.sin(th) * math.sin(ph),
                    r * math.cos(th),
                )
            )
    m = n * 2
    for i in range(n):
        for j in range(m):
            a, b, c, d = (
                i * m + j,
                i * m + (j + 1) % m,
                (i + 1) * m + j,
                (i + 1) * m + (j + 1) % m,
            )
            tris += [(a, c, b), (b, c, d)]
    return np.array(pts), np.array(tris)


def cylinder(r_bot, r_top, h, axis, n=24):
    pts, tris = [], []
    for k, (z, r) in enumerate(((-h / 2, r_bot), (h / 2, r_top))):
        for j in range(n):
            a = 2 * math.pi * j / n
            pts.append((r * math.cos(a), r * math.sin(a), z))
    pts += [(0, 0, -h / 2), (0, 0, h / 2)]
    cb, ct = 2 * n, 2 * n + 1
    for j in range(n):
        a, b = j, (j + 1) % n
        tris += [(a, b, n + a), (b, n + b, n + a), (cb, b, a), (ct, n + a, n + b)]
    p = np.array(pts)
    if axis == "X":
        p = p[:, [2, 0, 1]]
    elif axis == "Y":
        p = p[:, [1, 2, 0]]
    return p, np.array(tris)


def material_info(prim, time, cache):
    mat, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    key = str(mat.GetPath()) if mat else None
    if key in cache:
        return cache[key]
    info = dict(color=None, texture=None, material=key)
    if mat:
        shader = mat.ComputeSurfaceSource()[0]
        if shader:
            inp = shader.GetInput("diffuseColor")
            if inp:
                if inp.HasConnectedSource():
                    src = inp.GetConnectedSource()[0]
                    tex = UsdShade.Shader(src.GetPrim())
                    f = tex.GetInput("file")
                    if f and f.Get(time):
                        path = f.Get(time).resolvedPath
                        if path and Path(path).is_file():
                            img = Image.open(path).convert("RGB")
                            info["texture"] = srgb_to_lin(
                                np.asarray(img, float) / 255.0
                            )
                            info["texture_path"] = path
                elif inp.Get(time) is not None:
                    info["color"] = np.array(inp.Get(time), float)
    cache[key] = info
    return info


def collect(stage, time):
    xc = UsdGeom.XformCache(Usd.TimeCode(time))
    out, skipped, cache = [], [], {}
    for prim in Usd.PrimRange(stage.GetPseudoRoot(), Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdGeom.Gprim):
            continue
        img = UsdGeom.Imageable(prim)
        if img.ComputeVisibility(Usd.TimeCode(time)) == UsdGeom.Tokens.invisible:
            continue
        if img.ComputePurpose() in (UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide):
            continue
        t = Usd.TimeCode(time)
        uv = None
        if prim.IsA(UsdGeom.Mesh):
            m = UsdGeom.Mesh(prim)
            p = np.array(m.GetPointsAttr().Get(t) or [], float)
            counts = m.GetFaceVertexCountsAttr().Get(t) or []
            idx = m.GetFaceVertexIndicesAttr().Get(t) or []
            tris, fv, k = [], [], 0
            for c in counts:
                for i in range(1, c - 1):
                    tris.append((idx[k], idx[k + i], idx[k + i + 1]))
                    fv.append((k, k + i, k + i + 1))
                k += c
            tris = np.array(tris, int).reshape(-1, 3)
            st = UsdGeom.PrimvarsAPI(prim).GetPrimvar("st")
            if st and st.HasValue():
                vals = np.array(st.ComputeFlattened(t) or [], float)
                interp = st.GetInterpolation()
                if len(vals):
                    if interp == UsdGeom.Tokens.faceVarying and len(vals) == k:
                        uv = vals[np.array(fv, int).reshape(-1, 3)]
                    elif interp in (
                        UsdGeom.Tokens.vertex,
                        UsdGeom.Tokens.varying,
                    ) and len(vals) == len(p):
                        uv = vals[tris]
        elif prim.IsA(UsdGeom.Cube):
            p, tris = unit_cube()
            p = p * UsdGeom.Cube(prim).GetSizeAttr().Get(t)
        elif prim.IsA(UsdGeom.Sphere):
            p, tris = sphere(UsdGeom.Sphere(prim).GetRadiusAttr().Get(t))
        elif prim.IsA(UsdGeom.Cylinder):
            c = UsdGeom.Cylinder(prim)
            r = c.GetRadiusAttr().Get(t)
            p, tris = cylinder(r, r, c.GetHeightAttr().Get(t), c.GetAxisAttr().Get(t))
        elif prim.IsA(UsdGeom.Cone):
            c = UsdGeom.Cone(prim)
            p, tris = cylinder(
                c.GetRadiusAttr().Get(t),
                1e-4,
                c.GetHeightAttr().Get(t),
                c.GetAxisAttr().Get(t),
            )
        else:
            skipped.append(str(prim.GetPath()))
            continue
        if len(p) == 0 or len(tris) == 0:
            continue
        M = np.array(xc.GetLocalToWorldTransform(prim), float)
        w = np.c_[p, np.ones(len(p))] @ M
        info = material_info(prim, t, cache)
        if info["color"] is None and info["texture"] is None:
            dc = UsdGeom.Gprim(prim).GetDisplayColorAttr().Get(t)
            info = dict(
                info, color=np.array(dc[0], float) if dc else np.array([0.5, 0.5, 0.5])
            )
        out.append(dict(path=str(prim.GetPath()), V=w[:, :3], T=tris, UV=uv, info=info))
    return out, skipped


def look_at(eye, target, up=(0, 0, 1)):
    f = np.array(target, float) - eye
    f /= np.linalg.norm(f)
    r = np.cross(f, up)
    r = r / (np.linalg.norm(r) or 1)
    u = np.cross(r, f)
    return np.array([r, u, -f]), eye


def render(meshes, R, eye, fov_deg, W, H, ortho_width=None):
    color = np.full((H, W, 3), 0.92)
    zbuf = np.full((H, W), np.inf)
    light = np.array([0.4, -0.6, 0.7])
    light /= np.linalg.norm(light)
    fpx = (H / 2) / math.tan(math.radians(fov_deg) / 2)
    for m in meshes:
        Vc = (m["V"] - eye) @ R.T
        for ti, tri in enumerate(m["T"]):
            P = Vc[tri]
            if np.any(P[:, 2] > -0.01):
                continue
            n = np.cross(
                m["V"][tri[1]] - m["V"][tri[0]], m["V"][tri[2]] - m["V"][tri[0]]
            )
            nl = np.linalg.norm(n)
            if nl == 0:
                continue
            shade = 0.35 + 0.65 * abs(np.dot(n / nl, light))
            if ortho_width:
                s = W / ortho_width
                x = W / 2 + s * P[:, 0]
                y = H / 2 - s * P[:, 1]
                z = -P[:, 2]
            else:
                x = W / 2 + fpx * P[:, 0] / -P[:, 2]
                y = H / 2 - fpx * P[:, 1] / -P[:, 2]
                z = -P[:, 2]
            x0, x1 = max(int(x.min()), 0), min(int(x.max()) + 1, W)
            y0, y1 = max(int(y.min()), 0), min(int(y.max()) + 1, H)
            if x0 >= x1 or y0 >= y1:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            d = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
            if abs(d) < 1e-12:
                continue
            l0 = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / d
            l1 = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / d
            l2 = 1 - l0 - l1
            inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
            if not inside.any():
                continue
            if ortho_width:
                depth = l0 * z[0] + l1 * z[1] + l2 * z[2]
                zz = np.ones(3)
            else:
                iz = l0 / z[0] + l1 / z[1] + l2 / z[2]
                depth = 1 / iz
                zz = z
            sub = zbuf[y0:y1, x0:x1]
            win = inside & (depth < sub)
            if not win.any():
                continue
            info = m["info"]
            if info.get("texture") is not None and m["UV"] is not None:
                uv = m["UV"][ti]
                w = depth if not ortho_width else 1.0
                u = (
                    l0 * uv[0, 0] / zz[0]
                    + l1 * uv[1, 0] / zz[1]
                    + l2 * uv[2, 0] / zz[2]
                ) * w
                v = (
                    l0 * uv[0, 1] / zz[0]
                    + l1 * uv[1, 1] / zz[1]
                    + l2 * uv[2, 1] / zz[2]
                ) * w
                tex = info["texture"]
                th, tw = tex.shape[:2]
                px = np.clip((u * tw).astype(int), 0, tw - 1)
                py = np.clip(((1 - v) * th).astype(int), 0, th - 1)
                base = tex[py, px]
            else:
                c = (
                    info["color"]
                    if info.get("color") is not None
                    else np.array([0.5, 0.5, 0.5])
                )
                base = np.broadcast_to(c, win.shape + (3,))
            col = color[y0:y1, x0:x1]
            col[win] = (base * shade)[win]
            sub[win] = depth[win]
    return (lin_to_srgb(color) * 255).astype(np.uint8)
