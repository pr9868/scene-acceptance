"""Shared composed traversal and bounded expansion of local UDIM asset names."""

from pathlib import Path
import re

from pxr import Usd

from .model import BoundaryError


def prims(stage):
    """Include instance proxies so a saved instance cannot hide checked geometry."""
    for prim in Usd.PrimRange(
        stage.GetPseudoRoot(), Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
    ):
        if not prim.IsPseudoRoot():
            yield prim


def udim_tiles(bundle, layer_path: Path, identifier: str) -> list[Path]:
    """Expand one filename token, with no resolver, recursive glob or URL access."""
    raw = Path(identifier)
    if (
        identifier.count("<UDIM>") != 1
        or "<UDIM>" not in raw.name
        or any(c in identifier.replace("<UDIM>", "") for c in ":[]<>*?")
    ):
        raise BoundaryError("Only one local filename <UDIM> token is supported")
    template = bundle.path(layer_path.parent / raw)
    directory = template.parent
    if not directory.is_dir():
        return []
    pattern = re.compile(
        re.escape(template.name).replace(re.escape("<UDIM>"), r"(1\d{3})")
    )
    tiles = []
    for index, child in enumerate(directory.iterdir()):
        if index >= 4096:
            raise BoundaryError("UDIM directory exceeds 4,096 entries")
        match = pattern.fullmatch(child.name)
        if match and 1001 <= int(match[1]) <= 1999:
            path = bundle.path(child)
            if not path.is_file():
                raise BoundaryError("UDIM tile must be a regular local file")
            tiles.append(path)
            bundle.check_dependency_count(len(tiles))
    return sorted(tiles)
