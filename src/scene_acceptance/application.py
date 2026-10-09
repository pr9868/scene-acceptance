"""Versioned caller boundary: JSON envelopes, cooperative control and verified replay."""

import argparse
import json
from pathlib import Path
import sys
import time
from .model import ContractError, digest_json, sha, strict_json
from .execution import RunControl, controlled, Cancelled, DeadlineExceeded
from .review_context import save

OPERATIONS = (
    "prepare",
    "approve",
    "bind",
    "validate-evidence",
    "evaluate",
    "check",
    "doctor",
    "triage",
    "resolve-triage",
    "audit",
    "collect-engine",
)


def _operation(name):
    from .preparation import prepare_scene
    from .scope import approve_scope, bind_preparation
    from .prepared_run import evaluate_prepared, validate_prepared_evidence
    from .evaluation import evaluate_scene
    from .environment import doctor
    from .triage import run_triage
    from .triage_review import resolve_triage
    from .assumption_audit import run_audit
    from .engine_adapter import collect_engine

    return dict(
        zip(
            OPERATIONS,
            (
                prepare_scene,
                approve_scope,
                bind_preparation,
                validate_prepared_evidence,
                evaluate_prepared,
                evaluate_scene,
                doctor,
                run_triage,
                resolve_triage,
                run_audit,
                collect_engine,
            ),
        )
    )[name]


def _fingerprint(operation, params):
    """Hash only explicitly selected inputs/closures, including missing dependencies."""
    from .environment import environment_identity
    from .engine import implementation_digest
    from .profiles import discover_artifact
    from .preparation import _read_raw, load_preparation
    from .briefs import load_brief

    hashes = {}

    def record(path, limit=33554432):
        p = Path(path).resolve()
        if p.exists() and (not p.is_file() or p.stat().st_size > limit):
            raise ContractError("Replay input is not a bounded regular file: " + str(p))
        hashes[str(p)] = sha(p) if p.is_file() else None

    if operation == "triage":
        from .triage import load_context

        context = load_context(
            **{
                key: params[key]
                for key in (
                    "assessment",
                    "expected_assessment_sha256",
                    "policy",
                    "expected_policy_sha256",
                    "bundle_root",
                    "review_root",
                )
            }
        )
        hashes.update(context[4])
    if operation == "resolve-triage":
        folder = Path(params["triage_run"]).resolve()
        record(folder / "triage-result.json")
        if sha(folder / "triage-result.json") != params["expected_triage_sha256"]:
            raise ContractError("Triage result does not match its caller-pinned hash")
        previous = strict_json(folder / "triage-result.json")
        for name in previous["input_hashes"]:
            record(name)
        owner = Path(previous["context"]["review_root"]).resolve()
        from .triage import _inside

        review_path = _inside(owner, params["review_record"])
        record(review_path)
        for row in strict_json(review_path)["reviews"]:
            for evidence in row["evidence"]:
                record(_inside(owner, evidence["path"]))
        record(folder / "model/request.json")
    if params.get("preparation"):
        folder, plan = load_preparation(
            params["preparation"],
            allow_runtime_migration=params.get("migrate_runtime", False),
        )
        record(folder / "plan.json")
        for name in plan["files"]:
            record(folder / name)
    if params.get("bundle_root") and params.get("candidate"):
        root = Path(params["bundle_root"]).resolve()
        artifact = discover_artifact(
            root,
            params["candidate"],
            max_dependency_files=params.get("max_dependency_files") or 64,
        )
        for name in artifact.identity["files"]:
            record(root / name)
        if params.get("raw_brief"):
            _, _, files = _read_raw(root, params["raw_brief"])
            for name in files:
                record(root / name)
        if params.get("brief"):
            _, files, _ = load_brief(root, params["brief"])
            for name in files:
                record(root / name)
    for key in (
        "interpreter_config",
        "judge_config",
        "triage_config",
        "audit_config",
        "adapter_config",
        "producer_decisions",
        "script_report",
        "capture_capabilities",
        "rubric",
        "capture_overrides",
        "approval",
        "receipt",
        "views",
        "previous_run",
        "review_record",
        "runtime_dependency_evidence",
        "cost_context",
    ):
        if operation == "resolve-triage" and key == "review_record":
            continue
        value = params.get(key)
        if not value:
            continue
        path = Path(value).resolve()
        if key == "previous_run" and path.is_dir():
            path = path / "prepared-result.json"
        record(path)
        if path.is_file() and key == "runtime_dependency_evidence":
            from .runtime_dependencies import read_receipt

            read_receipt(path)
        if path.is_file() and key == "views":
            for view in strict_json(path)["views"]:
                child = (path.parent / view["path"]).resolve()
                if not child.is_relative_to(path.parent):
                    raise ContractError("View path escapes its root")
                record(child)
        if path.is_file() and key == "review_record":
            for review in strict_json(path)["reviews"]:
                for item in review["evidence"]:
                    child = (path.parent / item["path"]).resolve()
                    if not child.is_relative_to(path.parent):
                        raise ContractError("Review evidence escapes its root")
                    record(child)
        if path.is_file() and key.endswith("_config"):
            config = strict_json(path)
            # Trusted adapter implementation is an input as well as its JSON configuration.
            import shutil

            executable = shutil.which(config["executable"])
            if executable:
                record(executable, limit=536870912)
            for arg in config["args"]:
                if Path(arg).is_absolute() and Path(arg).is_file():
                    record(arg)
    return digest_json(
        dict(
            operation=operation,
            parameters=params,
            inputs=hashes,
            runtime=implementation_digest(),
            environment=environment_identity(),
        )
    )


def invoke(
    operation: str,
    *,
    control: RunControl | None = None,
    reuse_completed: bool = False,
    cost_context: str | Path | None = None,
    run_root: str | Path | None = None,
    **parameters,
) -> dict:
    """Return one envelope. A failed component remains in data; no automatic model retry."""
    started = time.monotonic()
    from .accounting import read_cost_context, metrics

    costs = None
    control = control or RunControl()
    params = json.loads(json.dumps(parameters, default=str))
    out = Path(params["out"]).resolve() if params.get("out") else None
    receipt = (
        out / "invocation.json"
        if out and operation not in ("approve", "doctor")
        else None
    )
    data = None
    error = None
    fingerprint = None
    owned = False
    reused = False
    retained = None
    try:
        if operation not in OPERATIONS:
            raise ContractError("Unknown operation: " + operation)
        if run_root is not None and (out or operation in ("approve", "doctor")):
            raise ContractError("--run-root requires a directory operation without --out")
        if not out and operation not in ("approve", "doctor"):
            if reuse_completed:
                raise ContractError("Verified replay requires the original explicit --out")
            from .run_storage import start_run

            retained = start_run(operation, params, run_root, control.run_id)
            out = retained[0] / "output"
            params["out"] = str(out)
            receipt = out / "invocation.json"
        costs = read_cost_context(cost_context)
        with controlled(control):
            control.checkpoint(operation + ".started")
            if reuse_completed:
                if receipt is None:
                    raise ContractError(
                        "Verified replay requires a directory-output operation"
                    )
                fingerprint = _fingerprint(
                    operation,
                    dict(
                        params, cost_context=str(cost_context) if cost_context else None
                    ),
                )
                if out.exists():
                    if not receipt.is_file():
                        raise ContractError(
                            "Output exists without a completed invocation receipt; use a new output"
                        )
                    old = strict_json(receipt)
                    if (
                        old["input_sha256"] != fingerprint
                        or old["envelope"]["status"] != "completed"
                    ):
                        raise ContractError(
                            "Completed output does not match this invocation; use a new output"
                        )
                    actual = {
                        str(p.relative_to(out)): sha(p)
                        for p in out.rglob("*")
                        if p.is_file() and p != receipt
                    }
                    if actual != old["files"]:
                        raise ContractError(
                            "Completed output was modified; replay refused"
                        )
                    control.checkpoint(operation + ".reused")
                    return dict(
                        old["envelope"],
                        run_id=control.run_id,
                        reused=True,
                        events=control.events,
                    )
            existed = bool(out and out.exists())
            if existed and operation != "doctor":
                raise ContractError(
                    "Output already exists; use a new output or verified replay"
                )
            owned = bool(out and not existed)
            data = _operation(operation)(**params)
            control.checkpoint(operation + ".completed")
            if (
                fingerprint
                and _fingerprint(
                    operation,
                    dict(
                        params, cost_context=str(cost_context) if cost_context else None
                    ),
                )
                != fingerprint
            ):
                raise ContractError(
                    "Inputs changed during invocation; cannot cache result"
                )
    except Exception as exc:
        error = exc
    code = 4 if error else data.get("exit_code", 0)
    if (
        not error
        and operation == "doctor"
        and (
            data["errors"]
            or not data["baseline_ready"]
            or (data["model"] and not data["model"]["executable_found"])
        )
    ):
        code = 4
    status = (
        "cancelled"
        if isinstance(error, Cancelled) or control.cancelled
        else (
            "timed_out"
            if isinstance(error, DeadlineExceeded) or control.timed_out
            else "failed" if error else data.get("execution_status", "completed")
        )
    )
    if code == 4 and status == "completed":
        status = "failed"
    errors = []
    if error:
        from jsonschema import ValidationError

        message = error.message if isinstance(error, ValidationError) else str(error)
        errors = [
            dict(
                code=type(error).__name__,
                phase=control.events[-1]["phase"] if control.events else operation,
                message=message,
                retryable=isinstance(error, (Cancelled, DeadlineExceeded))
                or control.cancelled
                or control.timed_out,
            )
        ]
    elif code == 4:
        errors = [
            dict(
                code="COMPONENT_ERROR", phase=operation, message=str(e), retryable=False
            )
            for e in data.get("errors", [])
        ]
    result = dict(
        schema_version="1.0",
        operation=operation,
        run_id=control.run_id,
        status=status,
        exit_code=code,
        reused=reused,
        data=data,
        errors=errors,
        events=control.events,
        metrics=metrics(
            time.monotonic() - started, out if owned else None, costs, operation
        ),
    )
    if retained:
        from .run_storage import storage_paths

        result["storage"] = storage_paths(retained[0])
    if owned and receipt and out.is_dir():
        files = {
            str(p.relative_to(out)): sha(p)
            for p in out.rglob("*")
            if p.is_file() and p != receipt
        }
        save(receipt, dict(input_sha256=fingerprint, envelope=result, files=files))
    if retained:
        from .run_storage import finish_run

        finish_run(*retained, result)
    return result


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ContractError(message)


def parser():
    p = Parser(
        description="Application-facing scene harness; one JSON envelope on stdout"
    )
    sub = p.add_subparsers(dest="operation", required=True, parser_class=Parser)
    for operation in OPERATIONS:
        q = sub.add_parser(operation)
        q.add_argument(
            "--cost-context",
            help="Caller cost record for this invocation; unknown values are null",
        )
        q.add_argument("--deadline-seconds", type=float)
        q.add_argument("--cancel-file")
        q.add_argument(
            "--progress", action="store_true", help="JSONL progress on stderr"
        )
        q.add_argument(
            "--reuse-completed",
            action="store_true",
            help="Reuse only identical inputs and verified completed outputs",
        )
        if operation != "doctor":
            q.add_argument("--out", required=operation == "approve",
                           help="Explicit output; otherwise retain a unique dated run")
        if operation not in ("approve", "doctor"):
            q.add_argument("--run-root", help="History folder (default: ./scene-acceptance-runs)")
        if operation in (
            "prepare",
            "check",
            "bind",
            "doctor",
            "audit",
            "collect-engine",
        ):
            q.add_argument("--bundle-root", required=operation != "doctor")
            q.add_argument("--candidate", required=operation != "doctor")
            q.add_argument(
                "--max-dependency-files",
                type=int,
                default=None if operation == "bind" else 64,
            )
        if operation in ("approve", "bind", "validate-evidence", "evaluate"):
            q.add_argument("--preparation", required=True)
        if operation in ("prepare", "bind"):
            q.add_argument("--capture-capabilities")
        if operation == "prepare":
            for key in (
                "raw-brief",
                "interpreter-config",
                "rubric",
                "capture-overrides",
            ):
                q.add_argument("--" + key)
            q.add_argument("--allow-check", dest="allowed_checks", action="append")
            q.add_argument(
                "--review-profile",
                choices=["general", "static-visual", "animated-visual"],
                default="general",
            )
        if operation in ("approve", "bind"):
            q.add_argument("--expected-scope-sha256", required=True)
            q.add_argument("--reviewer", required=operation == "approve")
            q.add_argument("--reason", required=operation == "approve")
        if operation == "approve":
            q.add_argument(
                "--status",
                choices=["approved", "rejected", "needs_review"],
                default="approved",
            )
        if operation == "bind":
            q.add_argument("--migrate-runtime", action="store_true")
        if operation in ("check", "evaluate"):
            q.add_argument(
                "--mode", choices=["checks", "judge", "both"], default="checks"
            )
            q.add_argument(
                "--judge-exposure",
                choices=["withheld", "script-aware"],
                default="withheld",
            )
            q.add_argument("--review-record")
        if operation in ("check", "evaluate", "doctor"):
            q.add_argument("--judge-config")
        if operation in ("prepare", "check"):
            q.add_argument(
                "--runtime-dependency-policy",
                choices=["local-only", "caller-attested"],
                default="local-only",
            )
            q.add_argument("--runtime-environment-sha256")
        if operation in ("check", "evaluate"):
            q.add_argument("--runtime-dependency-evidence")
        if operation in ("evaluate", "validate-evidence"):
            q.add_argument("--expected-plan-sha256")
            q.add_argument("--receipt")
        if operation in ("check", "evaluate", "validate-evidence"):
            q.add_argument("--views")
        if operation == "evaluate":
            q.add_argument("--approval")
            q.add_argument("--previous-run")
        if operation == "resolve-triage":
            for key in ("triage-run", "expected-triage-sha256", "review-record"):
                q.add_argument("--" + key, required=True)
        if operation == "triage":
            for key in (
                "assessment",
                "expected-assessment-sha256",
                "policy",
                "expected-policy-sha256",
                "bundle-root",
                "review-root",
                "triage-config",
            ):
                q.add_argument("--" + key, required=True)
        if operation == "audit":
            q.add_argument("--audit-config", required=True)
            for key in (
                "raw-brief",
                "producer-decisions",
                "script-report",
                "expected-script-sha256",
                "views",
            ):
                q.add_argument("--" + key)
        if operation == "collect-engine":
            q.add_argument("--adapter-config", required=True)
        if operation == "check":
            q.add_argument("--brief")
            q.add_argument("--expected-brief-sha256")
            q.add_argument("--rubric")
            q.add_argument(
                "--approve-pack", dest="approved_packs", action="append", default=[]
            )
    return p


def main(argv=None):
    try:
        args = vars(parser().parse_args(argv))
        op = args.pop("operation")
        progress = args.pop("progress")
        control = RunControl(
            deadline_seconds=args.pop("deadline_seconds"),
            cancel_file=args.pop("cancel_file"),
            progress=(
                (lambda e: print(json.dumps(e), file=sys.stderr, flush=True))
                if progress
                else None
            ),
        )
        result = invoke(op, control=control, **args)
    except Exception as exc:
        result = dict(
            schema_version="1.0",
            operation="parse",
            run_id=RunControl().run_id,
            status="failed",
            exit_code=4,
            reused=False,
            data=None,
            events=[],
            errors=[
                dict(
                    code=type(exc).__name__,
                    phase="arguments",
                    message=str(exc),
                    retryable=False,
                )
            ],
        )
    print(json.dumps(result))
    return result["exit_code"]


def prepare_main(argv=None):
    return main(["prepare", *(sys.argv[1:] if argv is None else argv)])


def evaluate_main(argv=None):
    return main(["evaluate", *(sys.argv[1:] if argv is None else argv)])


def approve_main():
    return main(["approve", *sys.argv[1:]])


def bind_main():
    return main(["bind", *sys.argv[1:]])


def evidence_main():
    return main(["validate-evidence", *sys.argv[1:]])


def doctor_main():
    return main(["doctor", *sys.argv[1:]])


def triage_main():
    return main(["triage", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
