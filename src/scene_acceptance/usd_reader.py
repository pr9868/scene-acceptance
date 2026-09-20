"""Bounded local composition and static geometry; never trust authored extents."""

from pathlib import Path
import math
from pxr import Sdf, Usd, UsdGeom, Gf
from .model import BoundaryError, MissingEvidence, sha, digest_json


class Bundle:
    def __init__(self, root, dependencies):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise BoundaryError("Bundle root must be a directory")
        self.allowed = {self.path(p) for p in dependencies}
        self.hashes = {}

    def path(self, path):
        raw = str(path)
        if ":" in raw or "[" in raw or "]" in raw:
            raise BoundaryError("Only ordinary local paths are allowed")
        p = Path(path)
        p = (p if p.is_absolute() else self.root / p).resolve()
        if not p.is_relative_to(self.root):
            raise BoundaryError("Input path leaves the declared bundle")
        return p

    def record(self, path, missing=False):
        p = self.path(path)
        if not p.is_file():
            if missing:
                raise MissingEvidence(
                    "Missing declared input: " + str(p.relative_to(self.root))
                )
            raise BoundaryError(
                "Required input file is missing: " + str(p.relative_to(self.root))
            )
        if p.stat().st_size > 32 * 1024 * 1024:
            raise BoundaryError("Input exceeds the 32 MiB pilot limit")
        self.hashes[str(p.relative_to(self.root))] = sha(p)
        return p

    def unchanged(self):
        return all(
            (self.root / p).is_file() and sha(self.root / p) == h
            for p, h in self.hashes.items()
        )


class Scene:
    def __init__(self, bundle, path, profile="usd-static-cubes-v1"):
        self.bundle = bundle
        self.root = bundle.record(path)
        self.files = {}
        self.unsupported = []
        self._visit(self.root, set())
        self.stage = Usd.Stage.Open(str(self.root))
        if self.stage is None:
            raise ValueError("OpenUSD could not open the saved stage")
        for layer in self.stage.GetUsedLayers():
            if not layer.anonymous and layer.realPath:
                p = bundle.path(layer.realPath)
                if p not in self.files:
                    raise BoundaryError("Composition used an unrecorded dependency")
        self.identity = {
            "root": str(self.root.relative_to(bundle.root)),
            "files": {
                str(p.relative_to(bundle.root)): h
                for p, h in sorted(self.files.items())
            },
        }
        self.artifact_set_sha256 = digest_json(self.identity)
        self.units = UsdGeom.GetStageMetersPerUnit(self.stage)
        self.profile = profile
        self.cubes = {}
        self.meshes = {}
        self.geometry = {}
        self.shapes = {}
        self.mesh_stats = {}
        self.mesh_issues = {}
        self.mesh_sizes = [0, 0, 0]
        allowed = ["Xform", "Scope", "Cube"]
        if profile == "usd-static-geometry-v1":
            allowed.append("Mesh")
        self.xforms = UsdGeom.XformCache(Usd.TimeCode.Default())
        for index, prim in enumerate(self.stage.TraverseAll()):
            if index >= 10000:
                raise BoundaryError("Stage exceeds the 10,000 prim pilot limit")
            path = str(prim.GetPath())
            if prim.IsInstanceable() or not prim.IsActive() or not prim.IsDefined():
                self.unsupported.append(path + ": instanced/inactive/undefined prim")
            if prim.GetTypeName() not in allowed:
                self.unsupported.append(
                    path + ": unsupported type " + prim.GetTypeName()
                )
            if prim.IsA(UsdGeom.Cube):
                try:
                    self.cubes[path] = self._cube(prim)
                    self.geometry[path] = self.cubes[path]
                except MissingEvidence as e:
                    self.unsupported.append(path + ": " + str(e))
            elif prim.IsA(UsdGeom.Mesh) and "Mesh" in allowed:
                from .mesh import read_mesh

                try:
                    read_mesh(self, prim)
                except MissingEvidence as e:
                    self.unsupported.append(path + ": " + str(e))
        if not self.geometry and not self.mesh_issues:
            self.unsupported.append("No supported geometry found")

    def _visit(self, path, visiting):
        if path in visiting:
            raise MissingEvidence("Cyclic layer dependency is not supported")
        if path in self.files:
            return
        if len(self.files) >= 64:
            raise BoundaryError("Dependency closure exceeds 64 files")
        self.bundle.record(path, missing=True)
        self.files[path] = sha(path)
        layer = Sdf.Layer.FindOrOpen(str(path))
        if layer is None:
            raise ValueError("Cannot parse USD layer")
        layer.Reload(force=True)
        if layer.ListAllTimeSamples():
            self.unsupported.append("Time-sampled data is outside the static profile")

        def inspect(p):
            spec = layer.GetObjectAtPath(p)
            if isinstance(spec, Sdf.PrimSpec):
                for key in [
                    "variantSetNames",
                    "variantSelection",
                    "clips",
                    "payload",
                    "inheritPaths",
                    "specializes",
                ]:
                    if spec.HasInfo(key):
                        self.unsupported.append(
                            str(p) + ": unsupported composition " + key
                        )

        layer.Traverse(Sdf.Path.absoluteRootPath, inspect)
        deps = (
            set(layer.GetExternalReferences())
            | set(layer.GetExternalAssetDependencies())
            | set(layer.subLayerPaths)
        )
        for value in sorted(deps):
            if not value:
                continue
            if ":" in value or "[" in value:
                raise BoundaryError("External URI/package reference is not allowed")
            target = self.bundle.path(path.parent / value)
            if target not in self.bundle.allowed:
                raise MissingEvidence(
                    "Referenced file is not declared: "
                    + str(target.relative_to(self.bundle.root))
                )
            if target.suffix.lower() not in [".usd", ".usda", ".usdc"]:
                raise MissingEvidence("External non-USD asset is outside this profile")
            self._visit(target, visiting | {path})

    def _cube(self, prim):
        size = UsdGeom.Cube(prim).GetSizeAttr().Get()
        matrix = self.xforms.GetLocalToWorldTransform(prim)
        flat = [float(matrix[i][j]) for i in range(4) for j in range(4)]
        if (
            size is None
            or not math.isfinite(size)
            or size <= 0
            or not all(math.isfinite(x) for x in flat)
        ):
            raise MissingEvidence("Invalid or non-finite geometry")
        if (
            any(abs(matrix[i][3]) > 1e-12 for i in range(3))
            or abs(matrix[3][3] - 1) > 1e-12
        ):
            raise MissingEvidence("Non-affine transform")
        determinant = matrix.GetDeterminant()
        if not math.isfinite(determinant) or determinant == 0:
            raise MissingEvidence("Singular or non-finite transform")
        if not math.isfinite(self.units) or self.units <= 0:
            raise MissingEvidence("Invalid stage units")
        corners = [
            matrix.Transform(Gf.Vec3d(x * size / 2, y * size / 2, z * size / 2))
            * self.units
            for x in [-1, 1]
            for y in [-1, 1]
            for z in [-1, 1]
        ]
        self.shapes[str(prim.GetPath())] = {
            "kind": "Cube",
            "points": [list(v) for v in corners],
        }
        lo = [min(v[i] for v in corners) for i in range(3)]
        hi = [max(v[i] for v in corners) for i in range(3)]
        if not all(math.isfinite(x) for x in lo + hi):
            raise MissingEvidence("Non-finite transformed corners")
        color = UsdGeom.Gprim(prim).GetDisplayColorAttr().Get()
        return {
            "min": lo,
            "max": hi,
            "center": [(a + b) / 2 for a, b in zip(lo, hi)],
            "dimensions": [b - a for a, b in zip(lo, hi)],
            "display_color": [list(v) for v in color] if color is not None else None,
        }

    def under(self, root):
        return {
            p: v
            for p, v in self.geometry.items()
            if p == root or p.startswith(root + "/")
        }
