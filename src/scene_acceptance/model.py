"""Strict inputs and verdict rules. An empty or interrupted check never passes."""

from pathlib import Path
from importlib.resources import files
import hashlib, json, math
from jsonschema import Draft202012Validator

CHECK_IDS = {
    "usd",
    "profile",
    "metadata",
    "layout",
    "target",
    "mesh",
    "shape",
    "preserved",
    "claims",
    "freshness",
    "report_grounding",
}
CORE = {"usd", "profile", "metadata", "layout"}


class ContractError(ValueError):
    pass


class MissingEvidence(ValueError):
    pass


class BoundaryError(ValueError):
    pass


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest_json(data):
    return digest_bytes(
        json.dumps(
            data, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )


def sha(path):
    return digest_bytes(Path(path).read_bytes())


def schema(name):
    return json.loads(
        files("scene_acceptance").joinpath("schemas", name + ".schema.json").read_text()
    )


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ContractError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def strict_json(path):
    def constant(value):
        raise ContractError("Non-finite number: " + value)

    data = json.loads(
        Path(path).read_text(), object_pairs_hook=pairs, parse_constant=constant
    )

    def finite(x):
        if isinstance(x, float) and not math.isfinite(x):
            raise ContractError("Non-finite numeric input")
        if isinstance(x, dict):
            for v in x.values():
                finite(v)
        if isinstance(x, list):
            for v in x:
                finite(v)

    finite(data)
    return data


def validate(data, name):
    errors = sorted(
        Draft202012Validator(schema(name)).iter_errors(data),
        key=lambda e: str(list(e.absolute_path)),
    )
    if errors:
        raise ContractError(
            "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
        )


def validate_contract(c):
    validate(c, "contract")
    req = set(c["checks"]["required"])
    adv = set(c["checks"]["advisory"])
    if req & adv:
        raise ContractError("A check cannot be both required and advisory")
    if not CORE <= req:
        raise ContractError("Required core checks: " + ", ".join(sorted(CORE)))
    if c["profile"] == "usd-static-geometry-v1" and "mesh" not in req:
        raise ContractError("Static geometry profile requires the mesh check")
    if c.get("mesh_rules") and (
        c["profile"] != "usd-static-geometry-v1" or "mesh" not in req
    ):
        raise ContractError(
            "Mesh rules require the geometry profile and required mesh check"
        )
    if "shape" in c and "shape" not in req:
        raise ContractError("Declared shape preservation requires the shape check")
    if "shape" in req | adv and "shape" not in c:
        raise ContractError("shape check requires shape parameters")
    if "target" in req | adv and "target" not in c:
        raise ContractError("target check requires target parameters")
    if c.get("required_claims") and "claims" not in req:
        raise ContractError("Required claim coverage requires a required claims check")
    if len({x["id"] for x in c.get("required_claims", [])}) != len(
        c.get("required_claims", [])
    ):
        raise ContractError("Required claim IDs must be unique")
    if "preserved" in req | adv and "protected" not in c:
        raise ContractError("preserved check requires protected parameters")
    if any(
        a >= b for a, b in zip(c["layout"]["cell_min_m"], c["layout"]["cell_max_m"])
    ):
        raise ContractError("Cell minimum must be below maximum on each axis")
    from pxr import Sdf

    for p in (
        [c["layout"]["root"]]
        + [
            c[k]["path" if k == "target" else "root"]
            for k in ["target", "protected"]
            if k in c
        ]
        + c.get("protected", {}).get("exclude_paths", [])
        + [x["path"] for x in c.get("required_claims", [])]
        + c.get("shape", {}).get("paths", [])
        + c.get("mesh_rules", {}).get("require_closed_edges", [])
    ):
        path = Sdf.Path(p)
        if not path.IsAbsolutePath() or not path.IsPrimPath():
            raise ContractError("Expected an absolute prim path: " + p)


def check(check_id, status, reason, evidence=None, required=True, duration_ms=0):
    return dict(
        id=check_id,
        status=status,
        reason=reason,
        evidence=evidence or {},
        required=required,
        duration_ms=duration_ms,
    )


def reduce_results(results):
    required = [r for r in results if r["required"]]
    statuses = [r["status"] for r in required]
    complete = not any(x in ["ERROR", "UNKNOWN", "NOT_APPLICABLE"] for x in statuses)
    if not statuses:
        return "EVALUATION_ERROR", False
    if "FAIL" in statuses:
        return "REJECT", complete
    if any(x not in ["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"] for x in statuses):
        return "EVALUATION_ERROR", False
    if "NOT_APPLICABLE" in statuses:
        return "EVALUATION_ERROR", False
    if "UNKNOWN" in statuses:
        return "INSUFFICIENT_EVIDENCE", False
    return "ACCEPT_FOR_USE", True
