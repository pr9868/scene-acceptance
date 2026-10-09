"""Evaluate every declared check, preserving gaps and input revisions."""

from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
import time, platform, importlib.metadata, json
from jsonschema import Draft202012Validator
from pxr import Usd
from . import model
from .model import (
    check,
    MissingEvidence,
    validate_contract,
    strict_json,
    reduce_results,
    sha,
    digest_json,
)
from .usd_reader import Bundle, Scene
from .checks import REGISTRY

VERSION = "0.7.0.dev1"


def implementation_digest():
    root = Path(__file__).parent
    return digest_json(
        {
            str(p.relative_to(root)): sha(p)
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.suffix in [".py", ".json"]
        }
    )


def _evaluate_v1(
    contract_path,
    candidate_path,
    *,
    bundle_root,
    baseline_path=None,
    claims_path=None,
    receipt_path=None,
    expected_contract_sha256=None,
    registry=None,
    max_dependency_files=64,
):
    started = time.perf_counter()
    results = []
    contract = None
    identity = {}
    planned = []
    ctx = None
    admission_limits = {}
    try:
        preliminary = Bundle(bundle_root, [], max_dependency_files=max_dependency_files)
        admission_limits = {"max_dependency_files": preliminary.max_dependency_files}
        cp = preliminary.record(contract_path)
        contract_sha = sha(cp)
        identity = {"contract_sha256": contract_sha}
        if (
            expected_contract_sha256 is not None
            and contract_sha != expected_contract_sha256
        ):
            raise model.ContractError(
                "Contract hash does not match the caller-pinned requirement"
            )
        contract = strict_json(cp)
        validate_contract(contract)
        planned = [(n, True) for n in contract["checks"]["required"]] + [
            (n, False) for n in contract["checks"]["advisory"]
        ]
        bundle = Bundle(
            bundle_root,
            contract["allowed_dependencies"],
            max_dependency_files=max_dependency_files,
        )
        bundle.record(cp)
        for source in contract["evidence_sources"]:
            bundle.record(source, missing=True)
        claim_data = strict_json(bundle.record(claims_path)) if claims_path else None
        receipt_data = (
            strict_json(bundle.record(receipt_path)) if receipt_path else None
        )
        # Record receipt integrity as an input, but exclude it from the identity it attests to.
        scene = Scene(bundle, candidate_path, contract["profile"])
        baseline = (
            Scene(bundle, baseline_path, contract["profile"]) if baseline_path else None
        )
        identity = {
            "contract_sha256": contract_sha,
            "candidate": scene.identity,
            "baseline": baseline.identity if baseline else None,
            "claims_sha256": sha(bundle.path(claims_path)) if claims_path else None,
            "source_sha256": {
                p: sha(bundle.path(p)) for p in contract["evidence_sources"]
            },
            "checker_version": VERSION,
            "checker_sha256": implementation_digest(),
            "usd_version": list(Usd.GetVersion()),
            "jsonschema_version": importlib.metadata.version("jsonschema"),
        }
        ctx = SimpleNamespace(
            contract=contract,
            bundle=bundle,
            scene=scene,
            baseline=baseline,
            claims=claim_data,
            receipt=receipt_data,
            identity=identity,
        )
        providers = REGISTRY if registry is None else registry
        for name, required in planned:
            tick = time.perf_counter()
            try:
                if name not in providers:
                    raise RuntimeError("Declared provider is unavailable: " + name)
                record = providers[name](ctx)
                if not isinstance(record, dict) or record.get("id") != name:
                    raise RuntimeError(
                        "Provider did not return a complete check result"
                    )
                record.update(
                    required=required,
                    duration_ms=round((time.perf_counter() - tick) * 1000, 3),
                )
                Draft202012Validator(
                    model.schema("result")["properties"]["checks"]["items"]
                ).validate(record)
                json.dumps(record, allow_nan=False)
            except MissingEvidence as exc:
                record = check(name, "UNKNOWN", str(exc))
            except Exception as exc:
                record = check(name, "ERROR", type(exc).__name__ + ": " + str(exc))
            record.update(
                required=required,
                duration_ms=round((time.perf_counter() - tick) * 1000, 3),
            )
            results.append(record)
        if not bundle.unchanged():
            results.append(
                check(
                    "input_integrity",
                    "ERROR",
                    "An input changed during evaluation; this run cannot authorize acceptance.",
                )
            )
    except MissingEvidence as exc:
        results = [
            check("input_coverage", "UNKNOWN", str(exc), getattr(exc, "evidence", {}))
        ] + [
            check(
                name, "UNKNOWN", "Input coverage prevents execution.", required=required
            )
            for name, required in planned
        ]
    except Exception as exc:
        results = [check("input", "ERROR", type(exc).__name__ + ": " + str(exc))] + [
            check(
                name,
                "UNKNOWN",
                "Input/contract error prevents execution.",
                required=required,
            )
            for name, required in planned
        ]
    verdict, complete = reduce_results(results)
    if any(
        r["id"] in ["input", "input_integrity"] and r["status"] == "ERROR"
        for r in results
    ):
        verdict = "EVALUATION_ERROR"
        complete = False
    report = {
        "schema_version": "1.0",
        "checker_version": VERSION,
        "verdict": verdict,
        "complete": complete,
        "intended_use": (
            contract.get("intended_use")
            if isinstance(contract, dict)
            and isinstance(contract.get("intended_use"), str)
            else None
        ),
        "contract_id": (
            contract.get("id")
            if isinstance(contract, dict) and isinstance(contract.get("id"), str)
            else None
        ),
        "identity": identity,
        "checks": results,
        "coverage": {
            "profile": (
                contract.get("profile")
                if isinstance(contract, dict)
                and isinstance(contract.get("profile"), str)
                else None
            ),
            "checked": "Only the declared profile and checks listed in the results: static layout, requested edit, mesh structure, optional shape preservation, protected properties, input identity and typed claims.",
            "unchecked": [
                "pairwise collision, self-intersection, face planarity, vertex manifoldness or watertightness",
                "mesh normals, UVs, materials and subdivision surfaces",
                "shape equivalence across reindexing, remeshing or Cube/Mesh conversion",
                "photographic/visual fidelity",
                "actual plant measurements",
                "physical prediction or robot behavior",
                "free-form reports",
                "security isolation against a producer with the same filesystem permissions",
            ],
            "provided_claims_checked": bool(
                claims_path and any(n == "claims" for n, _ in planned)
            ),
            "provided_receipt_checked": bool(
                receipt_path and any(n == "freshness" for n, _ in planned)
            ),
        },
        "runtime": {
            "admission_limits": admission_limits,
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "provider_override": registry is not None,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "python": platform.python_version(),
            "usd": list(Usd.GetVersion()),
            "network_or_model_required": False,
        },
    }
    model.validate(report, "result")
    return report


def evaluate(
    contract_path,
    candidate_path,
    *,
    bundle_root,
    baseline_path=None,
    claims_path=None,
    receipt_path=None,
    expected_contract_sha256=None,
    registry=None,
    pack_registry=None,
    approved_packs=(),
    max_dependency_files=64,
    runtime_dependency_policy="local-only",
    runtime_environment_sha256=None,
    runtime_dependency_evidence=None,
):
    # Old malformed inputs still receive the original structured input-error report.
    try:
        cp = Bundle(bundle_root, []).record(contract_path)
        version = strict_json(cp).get("schema_version")
    except Exception:
        version = None
    if version == "2.0":
        from .pack_engine import evaluate_packs

        return evaluate_packs(
            contract_path,
            candidate_path,
            bundle_root=bundle_root,
            baseline_path=baseline_path,
            expected_contract_sha256=expected_contract_sha256,
            pack_registry=pack_registry,
            approved_packs=approved_packs,
            max_dependency_files=max_dependency_files,
            runtime_dependency_policy=runtime_dependency_policy,
            runtime_environment_sha256=runtime_environment_sha256,
            runtime_dependency_evidence=runtime_dependency_evidence,
            legacy_inputs_present=bool(
                claims_path or receipt_path or registry is not None
            ),
        )
    if (
        runtime_dependency_evidence is not None
        or runtime_dependency_policy != "local-only"
        or runtime_environment_sha256 is not None
    ):
        raise model.ContractError("Runtime dependency evidence requires contract v2")
    return _evaluate_v1(
        contract_path,
        candidate_path,
        bundle_root=bundle_root,
        baseline_path=baseline_path,
        claims_path=claims_path,
        receipt_path=receipt_path,
        expected_contract_sha256=expected_contract_sha256,
        registry=registry,
        max_dependency_files=max_dependency_files,
    )
