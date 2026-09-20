"""Local USD admission independent of geometry, materials or animation policy."""

from pxr import Usd, Sdf
from .usd_reader import Bundle
from .model import BoundaryError, MissingEvidence, sha, digest_json


class EvidenceBundle(Bundle):
    def __init__(self, root, dependencies):
        super().__init__(root, dependencies)
        self.missing = set()

    def record(self, path, missing=False):
        p = self.path(path)
        key = str(p.relative_to(self.root))
        if key in self.hashes and (not p.is_file() or sha(p) != self.hashes[key]):
            raise BoundaryError("Previously recorded input changed: " + key)
        return super().record(p, missing=missing)

    def record_optional(self, path):
        p = self.path(path)
        if not p.is_file():
            self.missing.add(str(p.relative_to(self.root)))
            return None
        return self.record(p)

    def unchanged(self):
        return super().unchanged() and all(
            not (self.root / p).exists() for p in self.missing
        )


class UsdArtifact:
    """Small local layer graphs and explicit local assets, including textures/time samples.

    No resolver URLs, packages, variants, value clips, payloads or dynamic file formats.
    These require an extended admission adapter, not silent partial composition.
    """

    def __init__(self, bundle, path):
        self.bundle = bundle
        self.root = bundle.record(path)
        self.layers = {}
        self.assets = {}
        self._visit(self.root, set())
        self.stage = Usd.Stage.Open(str(self.root), load=Usd.Stage.LoadNone)
        if self.stage is None:
            raise ValueError("OpenUSD could not open the saved stage")
        if self.stage.GetCompositionErrors():
            raise ValueError(
                "USD composition errors: " + str(self.stage.GetCompositionErrors())
            )
        for layer in self.stage.GetUsedLayers():
            if not layer.anonymous and bundle.path(layer.realPath) not in self.layers:
                raise BoundaryError("Composition used an unrecorded layer")
        for i, prim in enumerate(self.stage.TraverseAll()):
            if i >= 10000:
                raise BoundaryError("Stage exceeds 10,000 prim admission limit")
            if prim.IsInstanceable():
                raise MissingEvidence(
                    "Instanceable content is outside local USD admission"
                )
        self.identity = {
            "root": str(self.root.relative_to(bundle.root)),
            "files": {
                str(p.relative_to(bundle.root)): h
                for p, h in sorted({**self.layers, **self.assets}.items())
            },
        }
        self.artifact_set_sha256 = digest_json(self.identity)
        self._memory = self.memory_digest()

    def _visit(self, path, visiting):
        if path in visiting:
            raise MissingEvidence(
                "Cyclic USD composition is outside admission coverage"
            )
        if path in self.layers:
            return
        if len(self.layers) + len(self.assets) >= 64:
            raise BoundaryError("Dependency closure exceeds 64 files")
        if path.suffix.lower() not in (".usd", ".usda", ".usdc"):
            raise BoundaryError("USD input must have a USD file extension")
        self.bundle.record(path, missing=True)
        self.layers[path] = sha(path)
        layer = Sdf.Layer.FindOrOpen(str(path))
        if not layer:
            raise ValueError("Cannot parse USD layer")
        layer.Reload(force=True)
        authored_assets = set()

        def inspect(p):
            spec = layer.GetObjectAtPath(p)
            if isinstance(spec, Sdf.PrimSpec):
                for key in (
                    "variantSetNames",
                    "variantSelection",
                    "clips",
                    "payload",
                    "inheritPaths",
                    "specializes",
                ):
                    if spec.HasInfo(key):
                        raise MissingEvidence(
                            "Unsupported composition: " + str(p) + ":" + key
                        )
            if isinstance(spec, Sdf.AttributeSpec) and spec.typeName in (
                Sdf.ValueTypeNames.Asset,
                Sdf.ValueTypeNames.AssetArray,
            ):
                samples = layer.ListTimeSamplesForPath(p)
                if len(samples) > 10000:
                    raise BoundaryError(
                        "Asset dependency sampling exceeds 10,000 samples"
                    )
                values = [spec.default] + [layer.QueryTimeSample(p, t) for t in samples]
                for value in values:
                    items = [value] if isinstance(value, Sdf.AssetPath) else value
                    if items is not None and not isinstance(items, Sdf.ValueBlock):
                        for asset in items:
                            if isinstance(asset, Sdf.AssetPath) and asset.path:
                                authored_assets.add(asset.path)

        layer.Traverse(Sdf.Path.absoluteRootPath, inspect)
        refs = set(layer.GetExternalReferences()) | set(layer.subLayerPaths)
        assets = set(layer.GetExternalAssetDependencies()) | authored_assets
        for value in sorted(refs | assets):
            if not value:
                continue
            if any(x in value for x in (":", "[", "]", "<", ">", "*", "?")):
                raise BoundaryError(
                    "Only explicit local dependency paths are supported"
                )
            target = self.bundle.path(path.parent / value)
            if target not in self.bundle.allowed:
                raise MissingEvidence(
                    "Undeclared dependency: "
                    + str(target.relative_to(self.bundle.root))
                )
            if target in self.assets or target in self.layers:
                if target in visiting | {path}:
                    raise MissingEvidence("Cyclic USD composition")
                continue
            if value in refs:
                self._visit(target, visiting | {path})
            else:
                if len(self.layers) + len(self.assets) >= 64:
                    raise BoundaryError("Dependency closure exceeds 64 files")
                recorded = self.bundle.record_optional(target)
                self.assets[target] = sha(recorded) if recorded else None

    def memory_digest(self):
        return digest_json(
            {
                layer.identifier: layer.ExportToString()
                for layer in self.stage.GetUsedLayers()
            }
        )

    def unchanged(self):
        return self.memory_digest() == self._memory
