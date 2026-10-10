"""Follow selected material networks to dependencies already admitted by the core."""

from pathlib import Path
from pxr import Sdf, Usd


def dependencies(ctx, materials):
    stage = ctx.artifact.stage
    pending = [(p, p) for p in sorted(materials)]
    visited, result, gaps = set(), {}, []
    while pending:
        path, owner = pending.pop()
        if (path, owner) in visited:
            continue
        visited.add((path, owner))
        if len(visited) > 4096:
            gaps.append(
                dict(
                    object=owner,
                    status="UNKNOWN",
                    reason="Material network exceeds 4096 nodes",
                    cause="capacity_limit",
                )
            )
            break
        prim = stage.GetPrimAtPath(path)
        if not prim:
            gaps.append(
                dict(
                    object=path,
                    status="UNKNOWN",
                    reason="Missing connected material node",
                    cause="missing_evidence",
                )
            )
            continue
        for attr in prim.GetAttributes():
            for connection in attr.GetConnections():
                if not stage.GetAttributeAtPath(connection):
                    gaps.append(
                        dict(
                            object=str(connection),
                            status="UNKNOWN",
                            reason="Missing material connection",
                            cause="missing_evidence",
                        )
                    )
                    continue
                pending.append((str(connection.GetPrimPath()), owner))
            if attr.GetTypeName() not in (
                Sdf.ValueTypeNames.Asset,
                Sdf.ValueTypeNames.AssetArray,
            ):
                continue
            for time in [
                Usd.TimeCode.Default(),
                *[Usd.TimeCode(t) for t in attr.GetTimeSamples()],
            ]:
                value = attr.Get(time)
                assets = [value] if isinstance(value, Sdf.AssetPath) else (value or [])
                for asset in assets:
                    if not asset.path:
                        continue
                    target = None
                    if asset.resolvedPath:
                        target = ctx.bundle.path(asset.resolvedPath)
                    else:
                        # Property stacks retain the authoring layer after reference remapping.
                        for spec in attr.GetPropertyStack(time):
                            if spec.layer.realPath and (
                                spec.HasDefaultValue()
                                or spec.layer.ListTimeSamplesForPath(spec.path)
                            ):
                                target = ctx.bundle.path(
                                    Path(spec.layer.realPath).parent / asset.path
                                )
                                break
                    if target is None:
                        gaps.append(
                            dict(
                                object=str(attr.GetPath()),
                                status="UNKNOWN",
                                reason="Unresolved asset authoring layer",
                                cause="missing_evidence",
                            )
                        )
                        continue
                    matches = [target]
                    if "<UDIM>" in asset.path:
                        info = ctx.artifact.udim_sets.get(target)
                        matches = list(info[2]) if info and info[2] else [target]
                    for item in matches:
                        if item not in ctx.artifact.assets:
                            gaps.append(
                                dict(
                                    object=str(attr.GetPath()),
                                    status="UNKNOWN",
                                    reason="Material asset outside admitted closure",
                                    cause="missing_evidence",
                                )
                            )
                            continue
                        result.setdefault(item, set()).add(owner)
    return {p: sorted(owners) for p, owners in result.items()}, gaps
