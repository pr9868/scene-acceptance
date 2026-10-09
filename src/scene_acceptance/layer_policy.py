"""Declared layer metadata policy and differential dependency accounting."""

from pathlib import Path
import math

from pxr import Sdf, UsdGeom, UsdUtils

from .builtin_packs import obj, TEXT
from .model import MissingEvidence
from .packs import CheckSpec, Outcome, Pack


def metadata(ctx, params):
    stage = ctx.artifact.stage
    root_units = UsdGeom.GetStageMetersPerUnit(stage)
    root_axis = str(UsdGeom.GetStageUpAxis(stage))
    rows = []
    for path in sorted(ctx.artifact.layers):
        layer = Sdf.Layer.FindOrOpen(str(path))
        pseudo = layer.pseudoRoot
        for name, expected in [
            ("metersPerUnit", params["meters_per_unit"]),
            ("upAxis", params["up_axis"]),
        ]:
            authored = pseudo.HasInfo(name)
            observed = pseudo.GetInfo(name) if authored else None
            if not authored:
                status = (
                    "FAIL" if params["require_authored_on_every_layer"] else "UNKNOWN"
                )
            elif name == "metersPerUnit":
                status = (
                    "PASS"
                    if math.isfinite(observed) and observed == expected
                    else "FAIL"
                )
            else:
                status = "PASS" if observed == expected else "FAIL"
            rows.append(
                dict(
                    layer=str(path.relative_to(ctx.bundle.root)),
                    field=name,
                    expected=expected,
                    observed=observed,
                    status=status,
                )
            )
    statuses = {r["status"] for r in rows}
    return Outcome(
        (
            "FAIL"
            if "FAIL" in statuses
            else "UNKNOWN" if "UNKNOWN" in statuses else "PASS"
        ),
        "Compared authored metadata with the caller's delivery policy; no automatic rescaling or axis conversion.",
        dict(
            findings=rows,
            composed_root_units=root_units,
            composed_root_axis=root_axis,
            coverage="All admitted layers, including unselected variants. Referenced-layer metadata does not automatically convert geometry.",
        ),
    )


def dependencies(ctx, params):
    # Admission has already inspected every local authored dependency before
    # this API is allowed to follow the same graph.
    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(
        Sdf.AssetPath(str(ctx.artifact.root))
    )
    names = set()
    for layer in layers:
        if layer.anonymous or not layer.realPath:
            raise MissingEvidence(
                "Dependency cross-check returned an anonymous or unresolved layer"
            )
        names.add(ctx.bundle.path(layer.realPath))
    for asset in assets:
        names.add(ctx.bundle.path(asset))
    expected = {
        p
        for p, h in {**ctx.artifact.layers, **ctx.artifact.assets}.items()
        if h is not None
    }
    missing = expected - names
    extra = names - expected
    relative = lambda paths: sorted(str(p.relative_to(ctx.bundle.root)) for p in paths)
    # Keep differences visible instead of declaring either reader authoritative.
    status = "UNKNOWN" if unresolved or missing or extra else "PASS"
    return Outcome(
        status,
        "Compared the admitted closure with OpenUSD ComputeAllDependencies.",
        dict(
            custom_files=relative(expected),
            openusd_files=relative(names),
            custom_only=relative(missing),
            openusd_only=relative(extra),
            unresolved=[str(x) for x in unresolved],
            coverage="Dependency discovery agreement only; no file-content or renderer compatibility claim.",
        ),
    )


def layer_pack():
    return Pack(
        "usd.layers",
        "1.0.0",
        "Caller-defined layer metadata and dependency coverage",
        {
            "metadata": CheckSpec(
                metadata,
                obj(
                    {
                        "meters_per_unit": {"type": "number", "exclusiveMinimum": 0},
                        "up_axis": {"enum": ["Y", "Z"]},
                        "require_authored_on_every_layer": {"type": "boolean"},
                    }
                ),
                "Require declared units and up axis",
                "Every admitted layer",
                ("Missing metadata is unknown unless explicitly forbidden.",),
            ),
            "dependencies": CheckSpec(
                dependencies,
                obj({}),
                "Cross-check dependency readers",
                "OpenUSD and harness file sets",
                ("Disagreement stays unknown; this is not a resolver sandbox.",),
            ),
        },
        (str(Path(__file__)),),
        ("usd-core",),
    )
