"""Bounded composed subject selection, with exclusions retained as evidence."""

from pxr import Sdf, Usd, UsdGeom
from .model import ContractError, MissingEvidence
from .usd_composition import prims

SELECTOR = {
    "type": "object",
    "properties": {
        "root": {"type": "string"},
        "paths": {"type": "array", "items": {"type": "string"}, "maxItems": 4096},
        "collection": {"type": "string"},
        "tag": {
            "type": "object",
            "properties": {
                "attribute": {"type": "string"},
                "value": {"type": ["string", "number", "boolean"]},
            },
            "required": ["attribute", "value"],
            "additionalProperties": False,
        },
        "exclude": {"type": "array", "items": {"type": "string"}, "maxItems": 256},
        "max_subjects": {"type": "integer", "minimum": 1, "maximum": 100000},
    },
    "additionalProperties": False,
}


def absolute(path):
    p = Sdf.Path(path)
    if not p.IsAbsolutePath() or not (p.IsPrimPath() or p == Sdf.Path.absoluteRootPath):
        raise ContractError("Expected absolute subject prim path: " + path)
    return p


def resolve(stage, selector):
    from jsonschema import Draft202012Validator

    Draft202012Validator(SELECTOR).validate(selector)
    if sum(k in selector for k in ("paths", "collection", "tag")) > 1:
        raise ContractError(
            "Choose paths, collection or tag, not multiple selector modes"
        )
    root = absolute(selector.get("root", "/"))
    exclusions = [absolute(x) for x in selector.get("exclude", [])]
    explicit = (
        {str(absolute(p)) for p in selector.get("paths", [])}
        if "paths" in selector
        else None
    )
    query = None
    if "collection" in selector:
        collection = Usd.CollectionAPI.Get(stage, selector["collection"])
        if not collection:
            raise MissingEvidence("Missing USD collection: " + selector["collection"])
        query = collection.ComputeMembershipQuery()
    selected = []
    excluded = []
    unavailable = []
    capacity_exhausted = False
    limit = selector.get("max_subjects", 4096)
    for p in prims(stage):
        path = p.GetPath()
        name = str(path)
        if not path.HasPrefix(root):
            continue
        if explicit is not None and name not in explicit:
            continue
        if query and not query.IsPathIncluded(path):
            continue
        if "tag" in selector:
            t = selector["tag"]
            a = p.GetAttribute(t["attribute"])
            if not a or a.Get() != t["value"]:
                continue
        elif explicit is None and not p.IsA(UsdGeom.Gprim):
            if p.HasPayload() and not p.IsLoaded():
                unavailable.append(name)
            continue
        if any(path.HasPrefix(x) for x in exclusions):
            excluded.append(name)
            continue
        if not p.IsActive() or not p.IsDefined() or not p.IsLoaded():
            unavailable.append(name)
            continue
        selected.append(name)
        if len(selected) > limit:
            selected.pop()
            capacity_exhausted = True
            break
    missing = sorted(p for p in (explicit or set()) if not stage.GetPrimAtPath(p))
    return dict(
        paths=sorted(selected),
        excluded=sorted(excluded),
        unavailable=sorted(set(unavailable)),
        missing=missing,
        selected_count=len(selected),
        exclusion_count=len(excluded),
        capacity_exhausted=capacity_exhausted,
        observed_at_least=len(selected) + int(capacity_exhausted),
        coverage="Composed subjects including instance proxies; render visibility is not an exemption.",
        selector=selector,
    )
