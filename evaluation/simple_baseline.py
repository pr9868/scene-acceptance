"""Competent single-layer checking script; deliberately no reusable report framework.

Shares JSON schema validation and OpenUSD, not the harness reader/check registry.
It declares claims, receipts and composition outside its scope instead of passing them.
"""

from pathlib import Path
import math
from pxr import Usd, UsdGeom, Sdf, Gf
from scene_acceptance.model import strict_json, validate_contract, sha

SUPPORTED = {"usd", "profile", "metadata", "layout", "target", "preserved"}


def run(directory):
    d = Path(directory)
    try:
        c = strict_json(d / "contract.json")
        validate_contract(c)
        if set(c["checks"]["required"]) - SUPPORTED:
            return {
                "verdict": "INSUFFICIENT_EVIDENCE",
                "scope_supported": False,
                "reason": "Required claim, receipt or report coverage is outside this script.",
            }
        before = {p.name: sha(p) for p in d.iterdir() if p.is_file()}
        stages = []
        for name in ["scene.usda", "baseline.usda"]:
            layer = Sdf.Layer.FindOrOpen(str(d / name))
            layer.Reload(force=True)
            if (
                layer.GetExternalReferences()
                or layer.GetExternalAssetDependencies()
                or layer.subLayerPaths
                or layer.ListAllTimeSamples()
            ):
                return {
                    "verdict": "INSUFFICIENT_EVIDENCE",
                    "scope_supported": False,
                    "reason": "Only static single-layer inputs are supported.",
                }
            s = Usd.Stage.Open(str(d / name))
            stages.append(s)
            if any(
                p.GetTypeName() not in ["Xform", "Scope", "Cube"]
                or p.IsInstanceable()
                or not p.IsActive()
                for p in s.TraverseAll()
            ):
                return {
                    "verdict": "INSUFFICIENT_EVIDENCE",
                    "scope_supported": False,
                    "reason": "Unsupported representation.",
                }
        stage, baseline = stages
        tol = c["tolerance_m"]
        issues = []
        if not stage.HasAuthoredMetadata(
            "metersPerUnit"
        ) or not stage.HasAuthoredMetadata("upAxis"):
            issues.append("Missing authored metadata")
        if (
            UsdGeom.GetStageMetersPerUnit(stage) != c["stage"]["meters_per_unit"]
            or str(UsdGeom.GetStageUpAxis(stage)) != c["stage"]["up_axis"]
        ):
            issues.append("Wrong stage units/axis")

        def boxes(s):
            result = {}
            units = UsdGeom.GetStageMetersPerUnit(s)
            for p in s.Traverse():
                if not p.IsA(UsdGeom.Cube):
                    continue
                cube = UsdGeom.Cube(p)
                size = cube.GetSizeAttr().Get()
                matrix = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(
                    Usd.TimeCode.Default()
                )
                if size <= 0 or not math.isfinite(size):
                    raise ValueError("Invalid cube size")
                points = [
                    matrix.Transform(Gf.Vec3d(x, y, z)) * units
                    for x in [-size / 2, size / 2]
                    for y in [-size / 2, size / 2]
                    for z in [-size / 2, size / 2]
                ]
                lo = [min(v[i] for v in points) for i in range(3)]
                hi = [max(v[i] for v in points) for i in range(3)]
                if not all(math.isfinite(v) for v in lo + hi):
                    raise ValueError("Invalid world geometry")
                color = cube.GetDisplayColorAttr().Get()
                result[str(p.GetPath())] = {
                    "min": lo,
                    "max": hi,
                    "center": [(a + b) / 2 for a, b in zip(lo, hi)],
                    "color": [list(x) for x in color] if color is not None else None,
                }
            return result

        a = boxes(stage)
        b = boxes(baseline)
        layout = c["layout"]
        root = layout["root"]
        prim = stage.GetPrimAtPath(root)
        children = sorted(x.GetName() for x in prim.GetChildren()) if prim else []
        if children != sorted(layout["required_children"]):
            issues.append("Wrong equipment set")
        for path, v in a.items():
            if not path.startswith(root + "/"):
                continue
            if any(
                v["min"][i] < layout["cell_min_m"][i] - tol
                or v["max"][i] > layout["cell_max_m"][i] + tol
                for i in range(3)
            ):
                issues.append("Outside cell")
            if v["min"][1] < layout["aisle_min_y_m"] - tol:
                issues.append("Aisle intrusion")
        if "target" in c["checks"]["required"]:
            t = c["target"]
            v = a.get(t["path"])
            if not v or any(
                abs(x - y) > tol for x, y in zip(v["center"], t["center_m"])
            ):
                issues.append("Target not reached")
        if "preserved" in c["checks"]["required"]:
            p = c["protected"]
            subset = lambda data: {
                k: v
                for k, v in data.items()
                if k == p["root"] or k.startswith(p["root"] + "/")
            }
            aa, bb = subset(a), subset(b)
            if not bb or aa.keys() != bb.keys():
                issues.append("Protected identities differ")
            for key in aa.keys() & bb.keys():
                if (
                    "display_color" in p["properties"]
                    and aa[key]["color"] != bb[key]["color"]
                ):
                    issues.append("Protected color changed")
                if "world_bounds" in p["properties"] and any(
                    abs(x - y) > tol
                    for field in ["min", "max"]
                    for x, y in zip(aa[key][field], bb[key][field])
                ):
                    issues.append("Protected bounds changed")
        if before != {p.name: sha(p) for p in d.iterdir() if p.is_file()}:
            raise RuntimeError("Inputs changed during evaluation")
        return {
            "verdict": "REJECT" if issues else "ACCEPT_FOR_USE",
            "scope_supported": True,
            "issues": issues,
        }
    except Exception as exc:
        return {
            "verdict": "EVALUATION_ERROR",
            "scope_supported": True,
            "reason": type(exc).__name__ + ": " + str(exc),
        }
