"""Unified local invocation. Measurements and advisory opinions keep separate identities."""

from collections import Counter
from pathlib import Path
import json
from .model import ContractError, sha, strict_json
from .review_context import (
    context_for,
    intact,
    request_for_context,
    bounded_opinions,
    save,
)


def scripted(
    bundle,
    candidate,
    out,
    *,
    brief=None,
    expected_brief_sha256=None,
    approved_packs=(),
    max_dependency_files=64,
    max_prims=10000,
    review_record=None,
    runtime_dependency_policy="local-only",
    runtime_environment_sha256=None,
    runtime_dependency_evidence=None,
):
    if brief is not None:
        from .briefs import evaluate_brief

        result = evaluate_brief(
            brief,
            candidate,
            bundle_root=bundle,
            out=out,
            expected_sha256=expected_brief_sha256,
            approved_packs=approved_packs,
            max_dependency_files=max_dependency_files,
            max_prims=max_prims,
            review_record=review_record,
            runtime_dependency_policy=runtime_dependency_policy,
            runtime_environment_sha256=runtime_environment_sha256,
            runtime_dependency_evidence=runtime_dependency_evidence,
        )
        folder = out / "report"
        core = strict_json(
            folder
            / (
                "core-result.json"
                if (folder / "core-result.json").exists()
                else "result.json"
            )
        )
        scope = result["assessment_verdict"]
    else:
        if approved_packs:
            raise ContractError(
                "External packs require a mapped brief or legacy contract"
            )
        from .profiles import evaluate_baseline
        from .report import write_report

        core = evaluate_baseline(
            bundle,
            candidate,
            max_dependency_files=max_dependency_files,
            max_prims=max_prims,
            runtime_dependency_policy=runtime_dependency_policy,
            runtime_environment_sha256=runtime_environment_sha256,
            runtime_dependency_evidence=runtime_dependency_evidence,
        )
        write_report(core, out)
        folder = out
        scope = None
    return core, scope, folder


def evaluate_scene(
    *,
    bundle_root,
    candidate,
    out,
    mode="checks",
    brief=None,
    expected_brief_sha256=None,
    judge_config=None,
    views=None,
    rubric=None,
    judge_exposure="withheld",
    approved_packs=(),
    max_dependency_files=64,
    max_prims=10000,
    evidence_policy=None,
    evidence_error=None,
    evidence_requirements=None,
    review_record=None,
    runtime_dependency_policy="local-only",
    runtime_environment_sha256=None,
    runtime_dependency_evidence=None,
):
    """Library API for one saved USD scene, optional mapped brief and selected evaluators."""
    if mode not in ("checks", "judge", "both"):
        raise ContractError("Unknown evaluation mode")
    if any(v == "" for v in (candidate, brief, judge_config, views, rubric)):
        raise ContractError("Input paths must not be empty")
    if not candidate:
        raise ContractError("A candidate scene is required")
    if type(max_dependency_files) is not int or not 1 <= max_dependency_files <= 1024:
        raise ContractError("Invalid dependency budget")
    if expected_brief_sha256 and brief is None:
        raise ContractError("Brief hash requires a brief")
    if judge_exposure not in ("withheld", "script-aware"):
        raise ContractError("Unknown evidence exposure")
    if mode == "checks" and (
        judge_config is not None
        or views is not None
        or rubric is not None
        or judge_exposure != "withheld"
    ):
        raise ContractError("Judge options require judge or both mode")
    if review_record and (mode == "judge" or brief is None):
        raise ContractError(
            "Caller outcome review requires a mapped brief and scripted assessment"
        )
    if mode == "judge" and approved_packs:
        raise ContractError("Judge mode does not load content-check packs")
    if mode == "judge" and judge_exposure == "script-aware":
        raise ContractError("Script-aware review requires both mode")
    if mode != "checks" and judge_config is None:
        raise ContractError(
            "Judge and both modes require an explicit judge configuration"
        )
    from .runtime_dependencies import validate_runtime_policy

    validate_runtime_policy(runtime_dependency_policy, runtime_environment_sha256)
    if (
        runtime_dependency_evidence is not None
        and runtime_dependency_policy != "caller-attested"
    ):
        raise ContractError(
            "Runtime dependency evidence requires explicit caller-attested policy"
        )
    if mode == "judge" and runtime_dependency_evidence is not None:
        raise ContractError("Runtime dependency attestations require scripted checks")
    root = Path(bundle_root).resolve()
    output = Path(out).resolve()
    if output.exists() or output.is_relative_to(root) or root.is_relative_to(output):
        raise ContractError(
            "Output must be new and outside the scene bundle and its ancestors"
        )
    # Do not create an output over an explicit evidence/configuration file.
    for path in (
        judge_config,
        views,
        rubric,
        review_record,
        runtime_dependency_evidence,
    ):
        if path and Path(path).resolve().is_relative_to(output):
            raise ContractError("Output overlaps a supplied input")
    runtime_receipt_snapshot = None
    if runtime_dependency_evidence is not None:
        from .runtime_dependencies import read_receipt

        runtime_receipt_snapshot = read_receipt(runtime_dependency_evidence)
    output.mkdir(parents=True)
    from .engine import implementation_digest, VERSION

    result = dict(
        schema_version="1.0",
        mode=mode,
        execution_status="failed",
        checker_version=VERSION,
        checker_sha256=implementation_digest(),
        scene=None,
        brief_supplied=brief is not None,
        script=dict(
            status="not_requested" if mode == "judge" else "not_run",
            artifact_verdict=None,
            declared_scope_verdict=None,
            report=None,
            checks=[],
        ),
        judge=dict(
            status="not_requested" if mode == "checks" else "not_run",
            report=None,
            findings=[],
            evidence_exposure=judge_exposure,
        ),
        errors=[],
        source_unchanged=None,
        decision="EVALUATION_ERROR",
        exit_code=4,
        limits=[
            "Model opinions are advisory, not measurements or human approval.",
            "No brief means no inferred task-specific acceptance.",
            "Missing evidence is not a pass.",
        ],
    )
    if mode == "judge" and runtime_dependency_policy == "caller-attested":
        result["runtime_dependencies"] = dict(
            policy=runtime_dependency_policy,
            environment_sha256=runtime_environment_sha256,
            status="not_assessed",
            reason="Judge-only mode does not evaluate runtime dependency availability",
        )
    from .execution import checkpoint

    context = None
    admission = None
    core = None
    scope = None
    folder = None
    try:
        checkpoint("scene.admission")
        if mode != "checks":
            # Admit scene/brief independently from optional visual/configuration inputs.
            admission = context_for(
                root,
                candidate,
                output / "admission",
                brief=brief,
                expected_brief_sha256=expected_brief_sha256,
                max_dependency_files=max_dependency_files,
                max_prims=max_prims,
            )
            context = admission
            result["scene"] = admission["scene"]
        if mode != "judge":
            checkpoint("scripts.started")
            bundle = Path(admission["snapshot_bundle"]) if admission else root
            brief_name = (
                str((root / brief).resolve().relative_to(root))
                if brief is not None
                else None
            )
            core, scope, folder = scripted(
                bundle,
                admission["candidate"] if admission else candidate,
                output / "script",
                brief=brief_name,
                expected_brief_sha256=expected_brief_sha256,
                approved_packs=approved_packs,
                max_dependency_files=max_dependency_files,
                max_prims=max_prims,
                review_record=review_record,
                runtime_dependency_policy=runtime_dependency_policy,
                runtime_environment_sha256=runtime_environment_sha256,
                runtime_dependency_evidence=runtime_dependency_evidence,
            )
            result["runtime_dependencies"] = core["identity"].get(
                "runtime_dependencies"
            )
            overview = strict_json(folder / "overview.json")
            result["scene"] = admission["scene"] if admission else overview["scene"]
            result["script"] = dict(
                status=(
                    "error"
                    if core["verdict"] == "EVALUATION_ERROR"
                    or scope == "EVALUATION_ERROR"
                    else "completed"
                ),
                artifact_verdict=core["verdict"],
                declared_scope_verdict=scope,
                report=str((folder / "report.html").relative_to(output)),
                checks=overview["checks"],
                matrix=overview["matrix"],
                specifications=overview["specifications"],
            )
            if result["script"]["status"] == "error":
                result["errors"].append(
                    "Scripted evaluation reported an execution error; see component report."
                )
            if admission is None:
                receipt = output / "script/source-integrity.json"
                if receipt.exists():
                    result["source_unchanged"] = strict_json(receipt).get("unchanged")
                elif core["identity"].get("candidate"):
                    files = core["identity"]["candidate"]["files"]
                    result["source_unchanged"] = all(
                        (
                            (not (root / p).exists())
                            if h is None
                            else ((root / p).is_file() and sha(root / p) == h)
                        )
                        for p, h in files.items()
                    )
                    if not result["source_unchanged"]:
                        raise ContractError(
                            "Original scene changed after scripted evaluation"
                        )
            checkpoint("scripts.completed", checks=len(result["script"]["checks"]))
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ": " + str(exc))
    if mode != "checks":
        try:
            checkpoint("evidence.validation")
            if not admission or not intact(admission):
                raise ContractError(
                    "Scene/brief admission failed or changed; model review cannot proceed"
                )
            if evidence_error:
                raise ContractError(evidence_error)
            from .judge import load_config, run_request

            config = load_config(judge_config)
            context = context_for(
                root,
                candidate,
                output / "evidence",
                brief=brief,
                expected_brief_sha256=expected_brief_sha256,
                views=views,
                rubric=rubric,
                max_dependency_files=max_dependency_files,
                max_prims=max_prims,
            )
            if (
                not intact(admission)
                or context["scene"]["sha256"] != admission["scene"]["sha256"]
            ):
                raise ContractError("Scene changed between script and visual review")
            request = request_for_context(
                context,
                config,
                core=core,
                exposure=judge_exposure,
                evidence_policy=evidence_policy,
                evidence_requirements=evidence_requirements,
            )
            if not request["requirements"]:
                raise ContractError(
                    "No judge criteria selected; use checks mode or supply a rubric"
                )
            eligible = any(
                c["available"] for c in request["evidence_coverage"].values()
            )
            if eligible:
                inputs = {
                    **admission["original_hashes"],
                    **admission["snapshot_hashes"],
                    **context["original_hashes"],
                    **context["snapshot_hashes"],
                }
                inputs[str(output / "evidence/context.json")] = sha(
                    output / "evidence/context.json"
                )
                if core and judge_exposure == "script-aware":
                    core_path = folder / (
                        "core-result.json"
                        if (folder / "core-result.json").exists()
                        else "result.json"
                    )
                    inputs[str(core_path)] = sha(core_path)
                jr = run_request(
                    request, inputs, context["images"], config, output / "judge"
                )
            else:
                # There is no visual question the supplied evidence can answer. No CLI is launched.
                response = dict(
                    items=[
                        dict(
                            requirement_id=r["id"],
                            assessment="unknown",
                            explanation="Required evidence is absent or unsupported; no model call was made.",
                            evidence_ids=[],
                        )
                        for r in request["requirements"]
                    ]
                )
                jr = dict(
                    status="ADVISORY_REVIEW_COMPLETE",
                    request_sha256=request["request_sha256"],
                    model_requested=config["model"],
                    resolved_model=None,
                    usage=None,
                    elapsed_seconds=0,
                    response=response,
                    error=None,
                )
                save(output / "evidence/review-request.json", request)
            result["judge"] = dict(
                status=(
                    "completed"
                    if jr["status"] == "ADVISORY_REVIEW_COMPLETE"
                    else "error"
                ),
                report="judge/report.html" if eligible else None,
                raw_result="judge/judge-result.json" if eligible else None,
                request_sha256=jr["request_sha256"],
                evidence_exposure=judge_exposure,
                model_requested=jr["model_requested"],
                resolved_model=jr["resolved_model"],
                usage=jr["usage"],
                elapsed_seconds=jr["elapsed_seconds"],
                model_invoked=eligible,
                review_method="model" if eligible else "deterministic_missing_evidence",
                findings=(
                    bounded_opinions(jr["response"], request) if jr["response"] else []
                ),
                unassessed_areas=context["unassessed_areas"],
                requirements=context["requirements"],
                evidence_coverage=request["evidence_coverage"],
                error=jr["error"],
            )
            if jr["error"]:
                result["errors"].append(jr["error"])
        except Exception as exc:
            result["judge"]["status"] = "error"
            result["judge"]["error"] = type(exc).__name__ + ": " + str(exc)
            result["errors"].append(result["judge"]["error"])
    if admission:
        result["source_unchanged"] = intact(admission) and (
            context is admission or intact(context)
        )
        if not result["source_unchanged"]:
            result["errors"].append(
                "Original or copied evidence changed during evaluation"
            )
    if runtime_receipt_snapshot:
        receipt_path, receipt_hash, _ = runtime_receipt_snapshot
        try:
            from .runtime_dependencies import read_receipt

            _, current_hash, _ = read_receipt(receipt_path)
            if current_hash != receipt_hash:
                raise ContractError(
                    "Runtime dependency receipt changed during evaluation"
                )
        except Exception as exc:
            result["source_unchanged"] = False
            result["errors"].append(type(exc).__name__ + ": " + str(exc))
    completed = any(result[k]["status"] == "completed" for k in ("script", "judge"))
    result["execution_status"] = (
        ("partial" if completed else "failed") if result["errors"] else "completed"
    )
    opinions = Counter(x["assessment"] for x in result["judge"]["findings"])
    result["judge"]["counts"] = dict(opinions)
    if result["errors"]:
        decision, code = "EVALUATION_ERROR", 4
    elif core and (core["verdict"] == "REJECT" or scope == "REJECT"):
        decision, code = "REJECT", 2
    elif (
        mode == "judge"
        or scope == "NEEDS_REVIEW"
        or (core and core["verdict"] == "INSUFFICIENT_EVIDENCE")
        or opinions["concern"]
        or opinions["unknown"]
    ):
        decision, code = "NEEDS_REVIEW", 3
    else:
        decision, code = scope or (core or {}).get("verdict", "NEEDS_REVIEW"), 0
    result.update(decision=decision, exit_code=code)
    from .evaluation_report import write_evaluation

    write_evaluation(result, context, output)
    return result
