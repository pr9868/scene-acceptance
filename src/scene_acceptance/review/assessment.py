"""Keep artifact verdicts intact while making review gaps explicit."""

from pathlib import Path
from collections import Counter
from jsonschema import Draft202012Validator
from scene_acceptance import evaluate
from scene_acceptance.model import ContractError, digest_json, sha, strict_json
from .schemas import LAYERS, PLAN, PRODUCER, REVIEW

LIMITATIONS = [
    "Only listed obligations and choices are assessed; absent requirements remain undiscovered.",
    "Mapping relevance, inference approval and review judgments are caller responsibilities.",
    "Reviewer identity is recorded, not authenticated. Hashes identify files, not their truth.",
    "Producer explanations are claims, not independent evidence or approval.",
    "Geometry, materials, motion and physics are check domains, not review layers.",
    "No engineering certification, general scene suitability or physical truth is established.",
]


class Inputs:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.hashes = {}

    def path(self, name):
        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            raise ContractError("Input paths must be relative and stay inside their root")
        p = (self.root / p).resolve()
        if not p.is_relative_to(self.root):
            raise ContractError("Input path escapes its root")
        return p

    def record(self, name, limit=32 * 1024 * 1024):
        p = self.path(name)
        if p.exists() and (not p.is_file() or p.stat().st_size > limit):
            raise ContractError("Evidence must be a regular file within the size budget")
        h = sha(p) if p.is_file() else None
        if name in self.hashes and self.hashes[name] != h:
            raise ContractError("Input changed during assessment: " + name)
        self.hashes[name] = h
        return h

    def json(self, name, schema):
        if self.record(name, limit=4 * 1024 * 1024) is None:
            raise ContractError("Missing configured input: " + name)
        data = strict_json(self.path(name))
        errors = list(Draft202012Validator(schema).iter_errors(data))
        if errors:
            e = errors[0]
            raise ContractError(f"Invalid {name} at {list(e.absolute_path)}: {e.message}")
        return data

    def unchanged(self):
        for name, expected in self.hashes.copy().items():
            if self.record(name) != expected:
                raise ContractError("Input changed during assessment: " + name)


def indexed(items, key):
    result = {item[key]: item for item in items}
    if len(result) != len(items):
        raise ContractError("Duplicate identifier: " + key)
    return result


def semantic_report(report):
    # Durations and the wall clock change on replay; actual observations remain bound.
    checks=[]
    for c in report['checks']:
        item={k:v for k,v in c.items() if k!='duration_ms'}
        evidence=item.get('evidence',{})
        if (isinstance(evidence,dict)
                and (evidence.get('pack'),evidence.get('check')) == ('physics.incline-worker','displacement')
                and isinstance(evidence.get('observations'),dict)):
            # This pack declares process wall time separately from its simulated clock,
            # trajectory, job identity and result. Retain it in the original report.
            item['evidence']=evidence | {'observations':{
                k:v for k,v in evidence['observations'].items() if k!='elapsed_wall_s'}}
        elif (isinstance(evidence,dict)
                and (evidence.get('pack'),evidence.get('check')) == ('geometry','contract')
                and isinstance(evidence.get('observations'),dict)
                and isinstance(evidence['observations'].get('checks'),list)):
            # The compatibility adapter includes inner core execution durations.
            # Keep every status, input identity and measured observation bound.
            observations=evidence['observations']
            item['evidence']=evidence | {'observations':observations | {'checks':[
                {k:v for k,v in inner.items() if k!='duration_ms'} for inner in observations['checks']]}}
        checks.append(item)
    return {k: v for k, v in report.items() if k not in ("runtime", "checks")} | {
        "checks": checks}


def implementation():
    return {p.name: sha(p) for p in sorted(Path(__file__).parent.glob("*.py"))}


def assess(plan_path, *, review_root, bundle_root, expected_plan_sha256,
           decision_record=None, review_record=None, approved_packs=(), pack_registry=None, max_dependency_files=64,
           runtime_dependency_policy="local-only", runtime_environment_sha256=None, runtime_dependency_evidence=None):
    """Caller chooses trusted review files; the producer cannot select policy or approvals.

    plan_path/review_record resolve under review_root, outside bundle_root.
    decision_record and all core inputs resolve under bundle_root. Expected plan hash
    is mandatory. For a manual review, run once, review the snapshot, then rerun
    with the explicitly selected reviewer record. This is local trust, not a sandbox.
    """
    result = {"schema_version": "1.0", "review_version": "0.2.0",
              "assessment_verdict": "EVALUATION_ERROR", "core_verdict": None,
              "scope": "Only the declared obligations for the stated intended use",
              "intended_use": None, "snapshot_sha256": None,
              "items": [], "layers": {}, "gaps": [], "errors": [],
              "unmapped_decisions": [], "limitations": LIMITATIONS.copy(),
              "core_report": None, "identity": {}}
    try:
        owner, producer = Inputs(review_root), Inputs(bundle_root)
        if (owner.root.is_relative_to(producer.root)
                or producer.root.is_relative_to(owner.root)):
            raise ContractError("Review and producer roots must be separate, non-nested directories")
        source_hashes = implementation()
        plan = owner.json(plan_path, PLAN)
        if owner.hashes[plan_path] != expected_plan_sha256:
            raise ContractError("Plan does not match the caller-pinned hash")
        result["intended_use"] = plan["intended_use"]
        result['report_context'] = plan.get('report_context', {})
        entries = indexed(plan["items"], "id")
        if not any(x["required"] for x in entries.values()):
            raise ContractError("At least one declared obligation must be required")
        for entry in entries.values():
            if plan["layers"][entry["layer"]]["scope"] == "excluded":
                raise ContractError("An excluded layer cannot contain obligations")
            if (entry["layer"] == "inferred") != (entry["inference_authorization"] is not None):
                raise ContractError("Only inferred obligations require inference authorization")
            if entry["layer"] == "decisions":
                if not entry["decision_id"] or not entry["review_required"]:
                    raise ContractError("Decisions require a producer record and separate review")
            elif entry["decision_id"] is not None:
                raise ContractError("decision_id is only valid in the decisions layer")

        # Closed review schema rejects self-approval fields in the producer record.
        decisions = indexed(producer.json(decision_record, PRODUCER)["decisions"], "id") if decision_record else {}
        for decision in decisions.values():
            for path in decision["evidence"]:
                producer.record(path)
        reviews_data = owner.json(review_record, REVIEW) if review_record else None
        reviews = indexed(reviews_data["reviews"], "item_id") if reviews_data else {}
        for item_id, review in reviews.items():
            if item_id not in entries or not entries[item_id]["review_required"]:
                raise ContractError("Reviewer record refers to an unknown or non-review item")
            for evidence in review["evidence"]:
                owner.record(evidence["path"])

        # Policy references the producer contract by a caller-pinned hash.
        contract_path = producer.path(plan["contract"])
        producer.record(plan["contract"])
        if producer.hashes[plan["contract"]] != plan["contract_sha256"]:
            raise ContractError("Contract does not match the review plan")
        contract = strict_json(contract_path)
        if contract.get("schema_version") != "2.0":
            raise ContractError("This review extension currently supports contract v2 only")
        check_ids = {x["id"] for x in contract["checks"]}
        for entry in entries.values():
            if set(entry["check_ids"]) - check_ids:
                raise ContractError("Obligation maps to a check absent from the contract: " + entry["id"])
        producer.path(plan["candidate"])
        if plan["baseline"]:
            producer.path(plan["baseline"])
        core = evaluate(plan["contract"], plan["candidate"], bundle_root=producer.root,
                        baseline_path=plan["baseline"], expected_contract_sha256=plan["contract_sha256"],
                        approved_packs=approved_packs, pack_registry=pack_registry, max_dependency_files=max_dependency_files,
                        runtime_dependency_policy=runtime_dependency_policy, runtime_environment_sha256=runtime_environment_sha256,
                        runtime_dependency_evidence=runtime_dependency_evidence)
        result["core_report"], result["core_verdict"] = core, core["verdict"]
        for name, expected in core["identity"].get("input_files", {}).items():
            if producer.record(name) != expected:
                raise ContractError("Core input changed after evaluation: " + name)
        for name in core["identity"].get("missing_files", []):
            if producer.record(name) is not None:
                raise ContractError("Previously missing core evidence appeared: " + name)
        snapshot = digest_json({"plan_sha256": expected_plan_sha256,
                                "core": semantic_report(core),
                                "producer_inputs": producer.hashes,
                                "review_implementation": source_hashes})
        result["snapshot_sha256"] = snapshot
        fresh_review = reviews_data is not None and reviews_data["snapshot_sha256"] == snapshot
        checks = indexed(core["checks"], "id")

        for entry in entries.values():
            observations = []
            states = []

            def add(status, reason):
                states.append(status)
                observations.append({"status": status, "reason": reason})

            authorization = entry["inference_authorization"]
            authorized = authorization is None or authorization["status"] == "approved"
            if not authorized:
                add("UNKNOWN", "Proposed inference awaits caller approval; it is not an established obligation")
            for check_id in entry["check_ids"]:
                status = checks.get(check_id, {}).get("status", "UNKNOWN")
                if status == "NOT_APPLICABLE":
                    status = "UNKNOWN"
                # Preserve observations without treating an unapproved inference as a defect.
                add(status if authorized else "UNKNOWN", f"Mapped check {check_id}: {status}")
            if not entry["check_ids"] and not entry["review_required"]:
                add("UNKNOWN", "No automated check or reviewer assessment maps to this obligation")
            decision = decisions.get(entry["decision_id"])
            if entry["decision_id"]:
                if decision is None:
                    add("UNKNOWN", "Producer decision record is absent")
                else:
                    add("PASS", "Producer rationale recorded; this does not establish suitability")
                    for path in decision["evidence"]:
                        if producer.hashes[path] is None:
                            add("UNKNOWN", "Producer-referenced evidence is absent: " + path)
            review = reviews.get(entry["id"])
            if entry["review_required"]:
                if review is None:
                    add("UNKNOWN", "Separate reviewer judgment is required")
                elif not fresh_review:
                    add("UNKNOWN", "Reviewer record belongs to a different assessment snapshot")
                else:
                    evidence_ok = all(owner.hashes[e["path"]] == e["sha256"] for e in review["evidence"])
                    if not evidence_ok:
                        add("UNKNOWN", "Reviewer evidence is absent or does not match its pinned hash")
                    else:
                        status = {"approved": "PASS", "rejected": "FAIL", "needs_review": "UNKNOWN"}[review["status"]]
                        add(status if authorized else "UNKNOWN", "Recorded reviewer judgment: " + review["reason"])
            status = ("ERROR" if "ERROR" in states else "FAIL" if "FAIL" in states
                      else "UNKNOWN" if "UNKNOWN" in states else "PASS")
            result["items"].append(entry | {"status": status, "observations": observations,
                                          "producer_decision": decision, "review": review})

        if plan["mapping_review"]["status"] != "reviewed":
            result["gaps"].append("The caller has not completed review of the requirement-to-evidence mapping")
        result["mapping_review"] = plan["mapping_review"]
        mapped_decisions = {x["decision_id"] for x in entries.values() if x["decision_id"]}
        result["unmapped_decisions"] = sorted(set(decisions) - mapped_decisions)
        if result["unmapped_decisions"]:
            result["gaps"].append("Producer declared decisions outside the review plan; classify their significance")
        for layer, declaration in plan["layers"].items():
            items = [x for x in result["items"] if x["layer"] == layer]
            counts = {s: sum(x["status"] == s for x in items) for s in ("PASS", "FAIL", "UNKNOWN", "ERROR")}
            coverage = ("EXCLUDED" if declaration["scope"] == "excluded" else
                        "NOT_ASSESSED" if not items else
                        "ASSESSED_WITH_GAPS" if counts['UNKNOWN'] or counts['ERROR'] else "ASSESSED")
            result["layers"][layer] = declaration | {"coverage": coverage, "counts": counts}
            if coverage == "NOT_ASSESSED":
                result["gaps"].append("Included layer has no declared obligations: " + layer)

        required = [x["status"] for x in result["items"] if x["required"]]
        verdict = core["verdict"]
        if verdict == "EVALUATION_ERROR" or "ERROR" in required:
            overall = "EVALUATION_ERROR"
        elif verdict == "REJECT" or "FAIL" in required:
            overall = "REJECT"
        elif verdict != "ACCEPT_FOR_USE" or "UNKNOWN" in required or result["gaps"]:
            overall = "NEEDS_REVIEW"
        else:
            overall = "ACCEPT_FOR_DECLARED_SCOPE"
        owner.unchanged()
        producer.unchanged()
        if implementation() != source_hashes:
            raise ContractError("Review implementation changed during evaluation")
        result["identity"] = {"review_files": owner.hashes, "producer_files": producer.hashes,
                              "implementation": source_hashes}
        result["assessment_verdict"] = overall
    except Exception as exc:
        result["assessment_verdict"] = "EVALUATION_ERROR"
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    result['coverage_summary'] = {
        'unit': 'declared obligations',
        'total': len(result['items']),
        'required': dict(Counter(x['status'] for x in result['items'] if x['required'])),
        'advisory': dict(Counter(x['status'] for x in result['items'] if not x['required'])),
        'note': 'Obligations may share checks. These counts are not asset counts or proof that all requirements were declared.',
    }
    return result
