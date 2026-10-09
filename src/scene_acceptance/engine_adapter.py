"""Caller-configured bridge to a separately installed validation/runtime CLI."""

from pathlib import Path
import json
import shutil

from jsonschema import Draft202012Validator

from .model import ContractError, MissingEvidence, sha, strict_json
from .review.schemas import obj, array, TEXT, HASH
from .external_evidence import (
    ENGINE,
    ENGINE_RECEIPT,
    STATUS_MAPPING,
    native_status,
    pointer,
)
from .review_context import save

CONFIG = obj(
    {
        "schema_version": {"const": "1.0"},
        "executable": TEXT,
        "args": array(TEXT),
        "provider": {"enum": ["simready", "physx", "other"]},
        "engine": ENGINE,
        "profile_id": TEXT,
        "profile_sha256": HASH,
        "native_report": TEXT,
        "successful_exit_codes": {**array({"enum": [0, 1, 2]}, 1), "uniqueItems": True},
        "tests": array(STATUS_MAPPING, 1),
        "wall_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600},
        "memory_mib": {"type": "integer", "minimum": 128, "maximum": 65536},
        "cpu_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600},
    }
)


def collect_engine(
    *, bundle_root, candidate, adapter_config, out, max_dependency_files=64
):
    from .profiles import discover_artifact
    from .isolation import supervise

    root = Path(bundle_root).resolve()
    out = Path(out).resolve()
    config_path = Path(adapter_config).resolve()
    if out.exists() or out.is_relative_to(root) or root.is_relative_to(out):
        raise ContractError("Engine output must be new and outside the producer bundle")
    if config_path.is_relative_to(root) or config_path.is_relative_to(out):
        raise ContractError(
            "Executable adapter policy must be supplied outside the producer and output folders"
        )
    if config_path.stat().st_size > 1048576:
        raise ContractError("Adapter configuration exceeds 1 MiB")
    config = strict_json(config_path)
    Draft202012Validator(CONFIG).validate(config)
    config_hash = sha(config_path)
    keys = [(r["phase"], r["id"]) for r in config["tests"]]
    if len(set(keys)) != len(keys):
        raise ContractError("Duplicate configured engine test ID")
    artifact = discover_artifact(
        root, candidate, max_dependency_files=max_dependency_files
    )
    out.mkdir(parents=True)
    copy = out / "scene"
    copy.mkdir()
    for name, digest in artifact.identity["files"].items():
        if digest is None:
            continue
        dest = copy / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, dest)
        if sha(dest) != digest:
            raise ContractError("Scene changed while snapshotting for the engine")
    native = (out / config["native_report"]).resolve()
    if not native.is_relative_to(out) or native == out or native.is_relative_to(copy):
        raise ContractError(
            "Native report must be a relative output path outside the scene snapshot"
        )
    native.parent.mkdir(parents=True, exist_ok=True)
    substitutions = {
        "{scene}": str(copy / candidate),
        "{out}": str(out),
        "{report}": str(native),
    }
    args = [substitutions.get(arg, arg) for arg in config["args"]]
    if not any(arg == "{scene}" for arg in config["args"]):
        raise ContractError("Engine adapter must pass the admitted scene snapshot")
    result = supervise(
        [config["executable"], *args],
        wall_seconds=config["wall_seconds"],
        memory_mib=config["memory_mib"],
        cpu_seconds=config["cpu_seconds"],
        max_output_bytes=8388608,
    )
    save(out / "adapter-execution.json", result)
    (out / "stdout.log").write_text(result["stdout"])
    (out / "stderr.log").write_text(result["stderr"])
    if (
        not artifact.bundle.unchanged()
        or not artifact.unchanged()
        or sha(config_path) != config_hash
    ):
        raise ContractError(
            "Engine input or caller configuration changed during execution"
        )
    if any(
        digest is not None
        and (not (copy / name).is_file() or sha(copy / name) != digest)
        for name, digest in artifact.identity["files"].items()
    ):
        raise ContractError(
            "Engine modified the saved scene snapshot; do not stamp or repair during acceptance"
        )
    if (
        result["limit_reason"]
        or result["returncode"] not in config["successful_exit_codes"]
    ):
        raise ContractError(
            "Engine command did not complete under its configured limits; execution record retained"
        )
    if native.resolve() != native or not native.resolve().is_relative_to(out):
        raise ContractError("Engine report path changed or escaped through a symlink")
    if any(p.is_symlink() for p in out.rglob("*")):
        raise ContractError("Engine output contains an unsupported symlink")
    if not native.is_file() or native.stat().st_size > 8388608:
        raise MissingEvidence("Engine did not supply a bounded native JSON report")
    report = strict_json(native)
    rows = []
    for item in config["tests"]:
        status = native_status(report, item)
        rows.append(
            dict(
                id=item["id"],
                phase=item["phase"],
                status=status,
                reason="Native status selected by the caller-reviewed adapter mapping: "
                + item["status_pointer"],
                evidence_paths=[str(native.relative_to(out))],
            )
        )
    receipt = dict(
        schema_version="1.0",
        scene_sha256=artifact.artifact_set_sha256,
        engine=config["engine"],
        provider=config["provider"],
        profile_id=config["profile_id"],
        profile_sha256=config["profile_sha256"],
        execution_status="completed",
        tests=rows,
        attachments=[
            dict(
                path=str(native.relative_to(out)),
                sha256=sha(native),
                description="Original native engine JSON report",
            )
        ],
        producer="Caller-configured external CLI adapter",
        limitations=[
            "The caller owns the executable, environment/profile identity and native status mapping.",
            "Only selected native status values were imported. This is not certification of a whole profile or independent engine fidelity.",
        ],
    )
    Draft202012Validator(ENGINE_RECEIPT).validate(receipt)
    save(out / "engine-receipt.json", receipt)
    save(out / "adapter-config.json", config)
    save(
        out / "manifest.json",
        dict(
            files={
                str(p.relative_to(out)): sha(p)
                for p in out.rglob("*")
                if p.is_file() and p != out / "manifest.json"
            }
        ),
    )
    statuses = {row["status"] for row in rows}
    return dict(
        schema_version="1.0",
        execution_status="completed",
        exit_code=(
            4
            if "ERROR" in statuses
            else 2 if "FAIL" in statuses else 3 if statuses - {"PASS"} else 0
        ),
        receipt="engine-receipt.json",
        verification=dict(
            receipt_sha256=sha(out / "engine-receipt.json"),
            basis="Collected by the caller-configured engine adapter; execution and native report retained.",
            native_report=str(native.relative_to(out)),
            tests=config["tests"],
        ),
        scene_sha256=artifact.artifact_set_sha256,
        adapter_sha256=config_hash,
        tests=rows,
        acceptance_decision=None,
    )
