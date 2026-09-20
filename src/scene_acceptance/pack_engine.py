"""Contract v2 execution: explicit providers, prerequisites and evidence accounting."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import platform
import time
from jsonschema import Draft202012Validator
from pxr import Usd
from . import model
from .model import check, strict_json, sha, MissingEvidence, ContractError
from .artifact import EvidenceBundle, UsdArtifact
from .packs import default_registry, Outcome


@dataclass(frozen=True)
class Context:
    bundle: EvidenceBundle
    artifact: UsdArtifact
    baseline: UsdArtifact | None
    sources: tuple[str, ...]
    # Mutable USD objects are trusted in-process objects, not a security sandbox.


def plan_contract(c):
    model.validate(c, "contract-v2")
    ids = [x["id"] for x in c["checks"]]
    if len(set(ids)) != len(ids) or any(x.startswith("core.") for x in ids):
        raise ContractError("Duplicate or reserved check ID")
    if not any(x["required"] for x in c["checks"]):
        raise ContractError("At least one required pack check is necessary")
    if set(c["packs"]) != {x["pack"] for x in c["checks"]}:
        raise ContractError("Pack declarations must match selected packs exactly")
    remaining = list(c["checks"])
    ordered = []
    while remaining:
        ready = [
            x
            for x in remaining
            if set(x.get("after", [])) <= {y["id"] for y in ordered}
        ]
        if not ready:
            raise ContractError(
                "Check prerequisites are cyclic or refer to absent checks"
            )
        ordered.extend(ready)
        remaining = [x for x in remaining if x not in ready]
    return ordered


def evaluate_packs(
    contract_path,
    candidate_path,
    *,
    bundle_root,
    baseline_path=None,
    expected_contract_sha256=None,
    pack_registry=None,
    approved_packs=(),
    legacy_inputs_present=False,
):
    from .engine import VERSION, implementation_digest

    tick = time.perf_counter()
    c, plan, bundle, ctx = None, [], None, None
    results, descriptions = [], {}
    identity = {"checker_version": VERSION, "checker_sha256": implementation_digest()}
    try:
        preliminary = EvidenceBundle(bundle_root, [])
        cp = preliminary.record(contract_path)
        identity["contract_sha256"] = sha(cp)
        if (
            expected_contract_sha256
            and identity["contract_sha256"] != expected_contract_sha256
        ):
            raise ContractError(
                "Contract hash does not match caller-pinned requirements"
            )
        c = strict_json(cp)
        plan = plan_contract(c)
        if legacy_inputs_present:
            raise ContractError(
                "v2 uses declared evidence_sources and pack_registry; legacy overrides are unsupported"
            )
        registry = (
            pack_registry
            if pack_registry is not None
            else default_registry(approved_packs)
        )
        bundle = EvidenceBundle(bundle_root, c["allowed_dependencies"])
        bundle.record(cp)
        for source in c["evidence_sources"]:
            bundle.record_optional(source)
        artifact = UsdArtifact(bundle, candidate_path)
        baseline = UsdArtifact(bundle, baseline_path) if baseline_path else None
        ctx = Context(bundle, artifact, baseline, tuple(c["evidence_sources"]))
        identity.update(
            candidate=artifact.identity,
            baseline=baseline.identity if baseline else None,
        )
        results.append(
            check(
                "core.artifact",
                "UNKNOWN" if bundle.missing else "PASS",
                "Admitted local USD dependencies; missing files remain unresolved.",
                {"missing_files": sorted(bundle.missing), "adapter": "usd-local-v1"},
            )
        )
        for item in plan:
            start = time.perf_counter()
            name = item["id"]
            pack = None
            try:
                pack = registry.get(item["pack"])
                desc = pack.describe()
                if pack.id in descriptions and descriptions[pack.id] != desc:
                    raise ContractError(
                        "Pack implementation changed during execution: " + pack.id
                    )
                descriptions[pack.id] = desc
                pin = c["packs"][pack.id]
                if desc["version"] != pin["version"]:
                    raise ContractError("Pack version mismatch: " + pack.id)
                if pin.get("sha256") and pin["sha256"] != desc["implementation_sha256"]:
                    raise ContractError(
                        "Pack implementation digest mismatch: " + pack.id
                    )
                if item["check"] not in pack.checks:
                    raise ContractError("Pack does not provide check: " + item["check"])
                spec = pack.checks[item["check"]]
                Draft202012Validator(spec.parameters).validate(item["parameters"])
                missing_deps = [
                    k
                    for k, v in desc["dependencies"].items()
                    if v.get("available") is False
                ]
                if missing_deps:
                    raise RuntimeError(
                        "Required optional libraries unavailable: "
                        + ", ".join(missing_deps)
                    )
                blockers = [
                    r["id"]
                    for r in results
                    if r["id"] in item.get("after", []) and r["status"] != "PASS"
                ]
                if blockers:
                    raise MissingEvidence(
                        "Prerequisite did not pass: " + ", ".join(blockers)
                    )
                outcome = spec.run(ctx, deepcopy(item["parameters"]))
                if not isinstance(outcome, Outcome):
                    raise TypeError("Pack must return an Outcome")
                record = check(
                    name,
                    outcome.status,
                    outcome.reason,
                    deepcopy(outcome.evidence),
                    required=item["required"],
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
                required=item["required"],
                duration_ms=round((time.perf_counter() - start) * 1000, 3),
            )
            record["evidence"] = {
                "pack": item["pack"],
                "check": item["check"],
                "observations": record["evidence"],
            }
            results.append(record)
            if (
                not bundle.unchanged()
                or not artifact.unchanged()
                or (baseline and not baseline.unchanged())
            ):
                raise ContractError(
                    "An evaluator changed an input file or in-memory USD layer"
                )
            if (
                pack is not None
                and pack.id in descriptions
                and pack.describe() != descriptions[pack.id]
            ):
                raise ContractError(
                    "Pack implementation changed during execution: " + pack.id
                )
        identity["packs"] = descriptions
    except MissingEvidence as exc:
        results.append(check("core.coverage", "UNKNOWN", str(exc)))
    except Exception as exc:
        results.append(
            check("core.input", "ERROR", type(exc).__name__ + ": " + str(exc))
        )
    completed = {x["id"] for x in results}
    for item in plan:
        if item["id"] not in completed:
            results.append(
                check(
                    item["id"],
                    "UNKNOWN",
                    "Input or execution interruption prevented this check.",
                    required=item["required"],
                )
            )
    if bundle:
        identity["input_files"] = dict(bundle.hashes)
        identity["missing_files"] = sorted(bundle.missing)
        if not bundle.unchanged():
            results.append(
                check("core.integrity", "ERROR", "Inputs changed during evaluation")
            )
    identity["packs"] = descriptions
    verdict, complete = model.reduce_results(results)
    if any(r["id"] in ("core.input", "core.integrity") for r in results):
        verdict, complete = "EVALUATION_ERROR", False
    by_pack = {}
    if plan:
        for pack_id in dict.fromkeys(x["pack"] for x in plan):
            ids = {x["id"] for x in plan if x["pack"] == pack_id}
            selected = [r for r in results if r["id"] in ids]
            by_pack[pack_id] = {
                s: sum(r["status"] == s for r in selected)
                for s in ("PASS", "FAIL", "UNKNOWN", "ERROR", "NOT_APPLICABLE")
            }
    report = {
        "schema_version": "1.0",
        "checker_version": VERSION,
        "verdict": verdict,
        "complete": complete,
        "intended_use": c.get("intended_use")
        if isinstance(c, dict) and isinstance(c.get("intended_use"), str)
        else None,
        "contract_id": c.get("id")
        if isinstance(c, dict) and isinstance(c.get("id"), str)
        else None,
        "identity": identity,
        "checks": results,
        "coverage": {
            "contract_schema_version": "2.0",
            "profile": c.get("profile") if isinstance(c, dict) else None,
            "planned": plan,
            "by_pack": by_pack,
            "checked": "Only selected checks, parameters and reported coverage in this exact use profile.",
            "unchecked": [
                "Any requirement absent from the supplied contract",
                "Real-world material or physical accuracy without suitable reference evidence",
                "Security isolation from installed pack code (trusted in-process execution)",
                "Simulator execution, rendered appearance and general free-form claim grounding",
            ],
        },
        "runtime": {
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "usd": list(Usd.GetVersion()),
            "elapsed_ms": round((time.perf_counter() - tick) * 1000, 3),
            "execution_mode": "trusted-local-functions",
            "approved_entry_points": list(approved_packs),
        },
    }
    model.validate(report, "result")
    return report
