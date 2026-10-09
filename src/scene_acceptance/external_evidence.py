"""Accept scoped measurements from a caller-owned viewer or simulation engine."""

from pathlib import Path
import math
import statistics

from jsonschema import Draft202012Validator

from .builtin_packs import obj, TEXT
from .review.schemas import HASH, array, TEXT as NONBLANK_TEXT
from .model import ContractError, MissingEvidence, sha, strict_json
from .packs import CheckSpec, Outcome, Pack

ENGINE = obj({"name": TEXT, "version": TEXT, "environment_sha256": HASH})
ATTACHMENT = obj({"path": TEXT, "sha256": HASH, "description": TEXT})
STATUS_MAPPING = obj(
    {
        "id": NONBLANK_TEXT,
        "phase": {"enum": ["profile", "runtime"]},
        "status_pointer": NONBLANK_TEXT,
        "status_mapping": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {
                "enum": ["PASS", "FAIL", "UNKNOWN", "ERROR", "SKIPPED"]
            },
        },
    }
)
VIEWER_VERIFICATION = obj({"receipt_sha256": HASH, "basis": NONBLANK_TEXT})
ENGINE_VERIFICATION = obj(
    {
        "receipt_sha256": HASH,
        "basis": NONBLANK_TEXT,
        "native_report": TEXT,
        "tests": array(STATUS_MAPPING, 1),
    }
)
PERFORMANCE = obj(
    {
        "schema_version": {"const": "1.0"},
        "scene_sha256": HASH,
        "viewer": ENGINE,
        "measurement": {"enum": ["rendered_frame_duration", "draw_callback_duration"]},
        "resolution": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1, "maximum": 16384},
            "minItems": 2,
            "maxItems": 2,
        },
        "camera_path": ATTACHMENT,
        "warmup_seconds": {"type": "number", "minimum": 0},
        "frame_seconds": {
            "type": "array",
            "items": {"type": "number", "exclusiveMinimum": 0},
            "minItems": 1,
            "maxItems": 100000,
        },
        "method": TEXT,
        "producer": TEXT,
        "limitations": array(TEXT, 1),
    }
)
ENGINE_RECEIPT = obj(
    {
        "schema_version": {"const": "1.0"},
        "scene_sha256": HASH,
        "engine": ENGINE,
        "provider": {"enum": ["simready", "physx", "other"]},
        "profile_id": TEXT,
        "profile_sha256": HASH,
        "execution_status": {"enum": ["completed", "failed", "partial"]},
        "tests": array(
            obj(
                {
                    "id": TEXT,
                    "phase": {"enum": ["profile", "runtime"]},
                    "status": {"enum": ["PASS", "FAIL", "UNKNOWN", "ERROR", "SKIPPED"]},
                    "reason": TEXT,
                    "evidence_paths": {**array(TEXT, 1), "uniqueItems": True},
                }
            ),
            1,
        ),
        "attachments": array(ATTACHMENT, 1),
        "producer": TEXT,
        "limitations": array(TEXT, 1),
    }
)


def evidence(ctx, name):
    if name not in ctx.sources:
        raise ContractError(
            "External evidence must be explicitly declared in evidence_sources: " + name
        )
    return ctx.bundle.record(name, missing=True)


def read_receipt(ctx, params, schema):
    path = evidence(ctx, params["receipt"])
    if path.stat().st_size > 8388608:
        raise ContractError("External receipt exceeds 8 MiB")
    data = strict_json(path)
    Draft202012Validator(schema).validate(data)
    if data["scene_sha256"] != ctx.artifact.artifact_set_sha256:
        raise MissingEvidence("External receipt belongs to another scene revision")
    return data


def attachment(ctx, row):
    path = evidence(ctx, row["path"])
    if sha(path) != row["sha256"]:
        raise MissingEvidence("External evidence attachment changed: " + row["path"])


def caller_verified(ctx, params):
    """The trusted contract, never a receipt field, can attest collected bytes.

    A hash is not an execution signature. The caller owns this declaration and
    must create it from a trusted collection, not by hashing a producer claim.
    """
    verification = params.get("verification")
    if verification is None:
        return False
    if sha(evidence(ctx, params["receipt"])) != verification["receipt_sha256"]:
        raise MissingEvidence(
            "External receipt differs from the caller-verified collection"
        )
    return True


def pointer(document, path):
    if not path.startswith("/"):
        raise ContractError("Native result selectors must be JSON pointers")
    value = document
    for token in path[1:].split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not key.isdigit():
                raise ContractError("Invalid array index in native result pointer")
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise ContractError("Native result pointer does not select a value")
    if type(value) not in (str, bool, int):
        raise ContractError("Native test status must be a string, bool or integer")
    return str(value).lower() if type(value) is bool else str(value)


def native_status(document, item):
    try:
        return item["status_mapping"].get(
            pointer(document, item["status_pointer"]), "UNKNOWN"
        )
    except (KeyError, IndexError, TypeError):
        return "UNKNOWN"


def performance(ctx, params):
    receipt = read_receipt(ctx, params, PERFORMANCE)
    attachment(ctx, receipt["camera_path"])
    if (
        receipt["viewer"] != params["viewer"]
        or receipt["resolution"] != params["resolution"]
        or receipt["camera_path"]["sha256"] != params["camera_path_sha256"]
    ):
        raise MissingEvidence(
            "Viewer, environment, resolution or camera path differs from the requested benchmark"
        )
    if receipt["measurement"] != "rendered_frame_duration":
        return Outcome(
            "UNKNOWN",
            "Draw callbacks are not rendered frame times.",
            {"receipt": receipt},
        )
    frames = receipt["frame_seconds"]
    if (
        len(frames) < params["min_frames"]
        or receipt["warmup_seconds"] < params["min_warmup_seconds"]
    ):
        return Outcome(
            "UNKNOWN",
            "Benchmark duration or warm-up is insufficient.",
            {"frame_count": len(frames)},
        )
    ordered = sorted(frames)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    median = statistics.median(frames)
    rows = [
        dict(
            metric="median_fps",
            observed=1 / median,
            minimum=params["minimum_median_fps"],
            status="PASS" if 1 / median >= params["minimum_median_fps"] else "FAIL",
        ),
        dict(
            metric="p95_frame_seconds",
            observed=p95,
            maximum=params["maximum_p95_frame_seconds"],
            status="PASS" if p95 <= params["maximum_p95_frame_seconds"] else "FAIL",
        ),
    ]
    verified = caller_verified(ctx, params)
    measured_status = "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
    return Outcome(
        measured_status if verified else "UNKNOWN",
        (
            "Compared caller-verified frame times with the named viewer workload."
            if verified
            else "Frame-time arithmetic is available, but execution provenance is unverified."
        ),
        dict(
            findings=rows,
            reported_status=measured_status,
            execution_provenance="caller-verified" if verified else "unverified",
            verification=params.get("verification"),
            frame_count=len(frames),
            viewer=receipt["viewer"],
            resolution=receipt["resolution"],
            warmup_seconds=receipt["warmup_seconds"],
            method=receipt["method"],
            coverage="Receipt integrity and arithmetic, not independent execution attestation. Applies only to this scene, viewer, machine, camera path and resolution.",
        ),
    )


def engine_tests(ctx, params):
    receipt = read_receipt(ctx, params, ENGINE_RECEIPT)
    if (
        receipt["engine"] != params["engine"]
        or receipt["provider"] != params["provider"]
        or receipt["profile_id"] != params["profile_id"]
        or receipt["profile_sha256"] != params["profile_sha256"]
    ):
        raise MissingEvidence(
            "Engine, environment or profile identity differs from the requested scope"
        )
    files = {a["path"]: a for a in receipt["attachments"]}
    tests = {(r["phase"], r["id"]): r for r in receipt["tests"]}
    if len(files) != len(receipt["attachments"]) or len(tests) != len(receipt["tests"]):
        raise ContractError("Duplicate attachment or external test ID")
    for item in files.values():
        attachment(ctx, item)
    if any(set(row["evidence_paths"]) - files.keys() for row in tests.values()):
        raise ContractError("External test cites an undeclared attachment")
    verified = caller_verified(ctx, params)
    if verified:
        verification = params["verification"]
        native_name = verification["native_report"]
        if native_name not in files:
            raise ContractError(
                "Verified native report must be a hashed receipt attachment"
            )
        native_path = evidence(ctx, native_name)
        if native_path.stat().st_size > 8388608:
            raise ContractError("Native engine report exceeds 8 MiB")
        native = strict_json(native_path)
        mappings = {(r["phase"], r["id"]): r for r in verification["tests"]}
        if len(mappings) != len(verification["tests"]):
            raise ContractError("Duplicate caller-verified native test mapping")
        for expected in params["required_tests"]:
            key = (expected["phase"], expected["id"])
            if key not in mappings:
                raise MissingEvidence(
                    "Required test has no caller-verified native mapping"
                )
            if key in tests and (
                native_name not in tests[key]["evidence_paths"]
                or tests[key]["status"] != native_status(native, mappings[key])
            ):
                raise ContractError(
                    "Normalized engine result contradicts the native report: " + key[1]
                )
    rows = []
    for expected in params["required_tests"]:
        row = tests.get((expected["phase"], expected["id"]))
        rows.append(
            row
            or dict(
                **expected,
                status="UNKNOWN",
                reason="Required test was not supplied",
                evidence_paths=[],
            )
        )
    statuses = {row["status"] for row in rows}
    status = (
        "ERROR"
        if "ERROR" in statuses or receipt["execution_status"] == "failed"
        else (
            "FAIL"
            if "FAIL" in statuses
            else (
                "UNKNOWN"
                if statuses - {"PASS"} or receipt["execution_status"] != "completed"
                else "PASS"
            )
        )
    )
    return Outcome(
        status if verified else "UNKNOWN",
        (
            "Compared selected engine tests with native results from the caller-verified collection."
            if verified
            else "Engine results were supplied, but execution provenance is unverified."
        ),
        dict(
            findings=rows,
            reported_status=status,
            execution_provenance="caller-verified" if verified else "unverified",
            verification=params.get("verification"),
            provider=receipt["provider"],
            engine=receipt["engine"],
            profile_id=receipt["profile_id"],
            attachments=receipt["attachments"],
            coverage="Selected native status values under the caller's mapping. Execution provenance relies on the caller-verified collection; hashes alone do not authenticate an engine run. No complete-profile certification.",
        ),
    )


def external_pack():
    return Pack(
        "external.evidence",
        "1.1.0",
        "Viewer measurements and engine profile/runtime evidence",
        {
            "viewer_performance": CheckSpec(
                performance,
                obj(
                    {
                        "receipt": TEXT,
                        "viewer": ENGINE,
                        "resolution": PERFORMANCE["properties"]["resolution"],
                        "camera_path_sha256": HASH,
                        "min_frames": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100000,
                        },
                        "min_warmup_seconds": {"type": "number", "minimum": 0},
                        "minimum_median_fps": {"type": "number", "exclusiveMinimum": 0},
                        "maximum_p95_frame_seconds": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                        },
                        "verification": VIEWER_VERIFICATION,
                    },
                    required=[
                        "receipt",
                        "viewer",
                        "resolution",
                        "camera_path_sha256",
                        "min_frames",
                        "min_warmup_seconds",
                        "minimum_median_fps",
                        "maximum_p95_frame_seconds",
                    ],
                ),
                "Check a named viewer workload",
                "Caller-provided frame times",
                (
                    "Draw callbacks and receipts without caller-verified execution stay unknown; the harness does not render.",
                ),
            ),
            "engine_tests": CheckSpec(
                engine_tests,
                obj(
                    {
                        "receipt": TEXT,
                        "engine": ENGINE,
                        "provider": ENGINE_RECEIPT["properties"]["provider"],
                        "profile_id": TEXT,
                        "profile_sha256": HASH,
                        "required_tests": {
                            **array(
                                obj(
                                    {
                                        "id": TEXT,
                                        "phase": {"enum": ["profile", "runtime"]},
                                    }
                                ),
                                1,
                            ),
                            "uniqueItems": True,
                        },
                        "verification": ENGINE_VERIFICATION,
                    },
                    required=[
                        "receipt",
                        "engine",
                        "provider",
                        "profile_id",
                        "profile_sha256",
                        "required_tests",
                    ],
                ),
                "Import SimReady/PhysX or other engine tests",
                "Named tests, engine and profile with hashed native evidence",
                (
                    "Receipt-only results stay unknown. The trusted contract must pin a caller-verified collection and native mapping; a producer cannot attest its own receipt.",
                ),
            ),
        },
        (str(Path(__file__)),),
        (),
    )
