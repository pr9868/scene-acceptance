"""A caller-selected, versioned baseline; no task requirements are inferred."""

from importlib.resources import files
import json
from .artifact import EvidenceBundle, UsdArtifact
from .model import ContractError
from .packs import default_registry


def discover_artifact(bundle_root, candidate, *, max_dependency_files=64):
    """Admit and inventory inputs without importing or running content-check packs."""

    class Discovered(set):
        def __contains__(self, path):
            # UsdArtifact has already enforced root containment, explicit local
            # paths and caller budgets. This is discovery, not an external allowlist.
            self.add(path)
            return True

    bundle = EvidenceBundle(bundle_root, [], max_dependency_files=max_dependency_files)
    bundle.allowed = Discovered()
    artifact = UsdArtifact(bundle, candidate)
    if not bundle.unchanged() or not artifact.unchanged():
        raise ContractError("Input changed during baseline discovery")
    return artifact


def baseline_contract(bundle_root, candidate, *, max_dependency_files=64):
    artifact = discover_artifact(
        bundle_root, candidate, max_dependency_files=max_dependency_files
    )
    bundle = artifact.bundle
    contract = json.loads(
        files("scene_acceptance")
        .joinpath("profiles/usd-delivery-baseline.json")
        .read_text()
    )
    contract["allowed_dependencies"] = sorted(
        str(p.relative_to(bundle.root)) for p in bundle.allowed
    )
    registry = default_registry()
    for name in contract["packs"]:
        desc = registry.get(name).describe()
        contract["packs"][name] = {
            "version": desc["version"],
            "sha256": desc["implementation_sha256"],
        }
    return contract, artifact.identity


def discovery_failure_report(exc, bundle_root, max_dependency_files, candidate=None):
    """A failed discovery executes no content checks and invents no inventory."""
    import platform
    from datetime import datetime, timezone
    from pxr import Usd
    from .engine import VERSION, implementation_digest
    from .model import MissingEvidence, check, digest_json, validate
    from .coverage import enrich

    contract = json.loads(
        files("scene_acceptance")
        .joinpath("profiles/usd-delivery-baseline.json")
        .read_text()
    )
    missing = isinstance(exc, MissingEvidence)
    report = dict(
        schema_version="1.0",
        checker_version=VERSION,
        verdict="INSUFFICIENT_EVIDENCE" if missing else "EVALUATION_ERROR",
        complete=False,
        intended_use=contract["intended_use"],
        contract_id=contract["id"],
        identity={
            "requested_candidate": str(candidate) if candidate is not None else None,
            "checker_sha256": implementation_digest(),
            "contract_sha256": digest_json(contract),
            "contract_encoding": "canonical-json-sha256",
            "contract": contract,
        },
        checks=[
            check(
                "core.discovery",
                "UNKNOWN" if missing else "ERROR",
                "Baseline discovery: " + str(exc),
                getattr(exc, "evidence", {}),
            )
        ]
        + [
            check(
                x["id"],
                "UNKNOWN",
                "Discovery did not complete; check was not executed.",
                required=x["required"],
            )
            for x in contract["checks"]
        ],
        coverage={
            "profile": contract["profile"],
            "planned": contract["checks"],
            "unchecked": ["All content checks: input discovery did not complete"],
        },
        runtime={
            "admission_limits": {"max_dependency_files": max_dependency_files},
            "usd": list(Usd.GetVersion()),
            "python": platform.python_version(),
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    enrich(report, None)
    validate(report, "result")
    return report


def evaluate_baseline(
    bundle_root,
    candidate,
    *,
    max_dependency_files=64,
    implicit=True,
    runtime_dependency_policy="local-only",
    runtime_environment_sha256=None,
    runtime_dependency_evidence=None,
):
    """Shared baseline execution; CLI shape and model orchestration stay outside."""
    from .pack_engine import evaluate_packs

    try:
        contract, identity = baseline_contract(
            bundle_root, candidate, max_dependency_files=max_dependency_files
        )
    except Exception as exc:
        report = discovery_failure_report(
            exc, bundle_root, max_dependency_files, candidate
        )
    else:
        report = evaluate_packs(
            None,
            candidate,
            bundle_root=bundle_root,
            max_dependency_files=max_dependency_files,
            contract_data=contract,
            runtime_dependency_policy=runtime_dependency_policy,
            runtime_environment_sha256=runtime_environment_sha256,
            runtime_dependency_evidence=runtime_dependency_evidence,
        )
        if report["identity"].get("candidate") != identity:
            from .model import check

            report["checks"].append(
                check(
                    "core.discovery_integrity",
                    "ERROR",
                    "Input changed after profile discovery",
                )
            )
            report["verdict"], report["complete"] = "EVALUATION_ERROR", False
    report["coverage"]["profile_selection"] = (
        "Default shipped baseline; no brief or contract supplied; no inferred task requirements"
        if implicit
        else "Caller-selected shipped baseline; no inferred task requirements"
    )
    return report
