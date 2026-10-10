"""Local USD admission independent of geometry, materials or animation policy."""

from pxr import Usd, Sdf, UsdShade
from .usd_reader import Bundle
from .model import BoundaryError, MissingEvidence, sha, digest_json
from .usd_composition import prims, udim_tiles


class EvidenceBundle(Bundle):
    def __init__(self, root, dependencies, *, max_dependency_files=64, max_prims=10000):
        super().__init__(
            root,
            dependencies,
            max_dependency_files=max_dependency_files,
            max_prims=max_prims,
        )
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

    Local variants, payloads, instances, inherits and specializes are admitted.
    Every authored branch is scanned before composition, including unselected variants.
    Resolver URLs, packages, value clips and dynamic file formats remain excluded.
    """

    def __init__(self, bundle, path):
        self.bundle = bundle
        self.root = bundle.record(path)
        self.layers = {}
        self.assets = {}
        self.udim_sets = {}
        # Missing MDL source assets can be supplied by a renderer's resolver.
        # Retain that uncertainty without resolving outside the admitted bundle.
        self.runtime_assets = {}
        self.dependency_references = {}
        self._ordinary_asset_paths = set()
        self._visit(self.root, set())
        self.stage = Usd.Stage.Open(str(self.root), load=Usd.Stage.LoadAll)
        if self.stage is None:
            raise ValueError("OpenUSD could not open the saved stage")
        if self.stage.GetCompositionErrors():
            raise ValueError(
                "USD composition errors: " + str(self.stage.GetCompositionErrors())
            )
        for layer in self.stage.GetUsedLayers():
            if not layer.anonymous and bundle.path(layer.realPath) not in self.layers:
                raise BoundaryError("Composition used an unrecorded layer")
        for i, prim in enumerate(prims(self.stage)):
            if i >= bundle.max_prims:
                from .model import PrimLimitExceeded

                raise PrimLimitExceeded(bundle.max_prims, i + 1)
        self._classify_runtime_assets()
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
        self.bundle.check_dependency_count(len(self.layers) + len(self.assets) + 1)
        if path.suffix.lower() not in (".usd", ".usda", ".usdc"):
            raise BoundaryError("USD input must have a USD file extension")
        self.bundle.record(path, missing=True)
        self.layers[path] = sha(path)
        layer = Sdf.Layer.FindOrOpen(str(path))
        if not layer:
            raise ValueError("Cannot parse USD layer")
        layer.Reload(force=True)
        authored_assets = set()
        runtime_references = {}
        ordinary_references = set()

        def inspect(p):
            spec = layer.GetObjectAtPath(p)
            if isinstance(spec, Sdf.PrimSpec):
                for key in ("clips",):
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
                                is_mdl_candidate = (
                                    spec.name == "info:mdl:sourceAsset"
                                    and spec.typeName == Sdf.ValueTypeNames.Asset
                                    and asset.path.endswith(".mdl")
                                )
                                if is_mdl_candidate:
                                    runtime_references.setdefault(
                                        asset.path, []
                                    ).append(
                                        {
                                            "layer": str(
                                                path.relative_to(self.bundle.root)
                                            ),
                                            "attribute": str(p),
                                            "identifier": asset.path,
                                            "source_type": "mdl",
                                        }
                                    )
                                else:
                                    ordinary_references.add(asset.path)

        layer.Traverse(Sdf.Path.absoluteRootPath, inspect)
        refs = set(layer.GetExternalReferences()) | set(layer.subLayerPaths)
        assets = set(layer.GetExternalAssetDependencies()) | authored_assets
        for value in sorted(refs | assets):
            if not value:
                continue
            if "<UDIM>" in value and value not in refs:
                targets = udim_tiles(self.bundle, path, value)
                template = self.bundle.path(path.parent / value)
                self.udim_sets[template] = (path, value, targets)
                if not targets:
                    # Keep an absent set in the evidence identity; never invent a tile.
                    self.assets[template] = None
                    self.bundle.record_optional(template)
                    self.bundle.check_dependency_count(
                        len(self.layers) + len(self.assets)
                    )
                for target in targets:
                    if target not in self.bundle.allowed:
                        raise MissingEvidence(
                            "Undeclared UDIM tile: "
                            + str(target.relative_to(self.bundle.root))
                        )
                    self.bundle.check_dependency_count(
                        len(set(self.layers) | set(self.assets) | {target})
                    )
                    self.assets[target] = sha(self.bundle.record(target))
                    self.dependency_references.setdefault(target, []).append(
                        {
                            "layer": str(path.relative_to(self.bundle.root)),
                            "identifier": value,
                        }
                    )
                continue
            if any(x in value for x in (":", "[", "]", "<", ">", "*", "?")):
                raise BoundaryError(
                    "Only explicit local dependency paths are supported"
                )
            target = self.bundle.path(path.parent / value)
            self.dependency_references.setdefault(target, []).append(
                {
                    "layer": str(path.relative_to(self.bundle.root)),
                    "identifier": value,
                }
            )
            if value in ordinary_references or value in refs:
                self._ordinary_asset_paths.add(target)
                self.runtime_assets.pop(target, None)
            elif (
                value in runtime_references and target not in self._ordinary_asset_paths
            ):
                self.runtime_assets.setdefault(target, []).extend(
                    runtime_references[value]
                )
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
                self.bundle.check_dependency_count(
                    len(self.layers) + len(self.assets) + 1
                )
                recorded = self.bundle.record_optional(target)
                self.assets[target] = sha(recorded) if recorded else None

    def _classify_runtime_assets(self):
        """Confirm MDL candidates against composed shader type and property stacks.

        A layer can author an ``over`` while another layer supplies the Shader
        type or implementation metadata. Property stacks also preserve the
        authoring paths when a referenced prim is remapped into the root stage.
        Ordinary uses of any resolved dependency always take precedence.
        """
        shader_specs = set()
        for prim in prims(self.stage):
            shader = UsdShade.Shader(prim)
            if (
                not shader
                or shader.GetImplementationSource() != UsdShade.Tokens.sourceAsset
            ):
                continue
            attribute = prim.GetAttribute("info:mdl:sourceAsset")
            if attribute:
                for spec in attribute.GetPropertyStack():
                    if spec.layer.realPath:
                        shader_specs.add(
                            (self.bundle.path(spec.layer.realPath), str(spec.path))
                        )
        for path, references in list(self.runtime_assets.items()):
            if path in self._ordinary_asset_paths or not all(
                (self.bundle.path(ref["layer"]), ref["attribute"]) in shader_specs
                for ref in references
            ):
                del self.runtime_assets[path]

    def memory_digest(self):
        return digest_json(
            {
                layer.identifier: layer.ExportToString()
                for layer in self.stage.GetUsedLayers()
            }
        )

    def unchanged(self):
        return self.memory_digest() == self._memory and all(
            udim_tiles(self.bundle, layer, identifier) == tiles
            for layer, identifier, tiles in self.udim_sets.values()
        )
