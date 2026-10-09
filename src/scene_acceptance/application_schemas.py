"""Schemas for the application protocol and durable preparation artifacts."""

from copy import deepcopy
from .review.schemas import obj, array, TEXT, HASH, nullable
from .preparation import CAPTURE, CAPABILITIES_SCHEMA
from .scope import APPROVAL_SCHEMA, SCOPE_SCHEMA, JUDGE_COVERAGE_DRIFT_SCHEMA
from .review_context import RUBRIC_SCHEMA

COUNT = {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}}
FILES = {"type": "object", "additionalProperties": HASH}
CAPTURE_REQUIREMENT = deepcopy(CAPTURE)
CAPTURE_REQUIREMENT["properties"].update(
    requirement_ids=array(TEXT, 1),
    evidence_kind={"enum": ["scene_view", "textured_view", "motion_frames"]},
)
CAPTURE_REQUIREMENT["required"] += ["requirement_ids", "evidence_kind"]
PLANNED_CAPTURE = deepcopy(CAPTURE_REQUIREMENT)
PLANNED_CAPTURE["properties"]["feasibility_gaps"] = array(TEXT)
PLANNED_CAPTURE["required"] += ["feasibility_gaps"]
CAPTURE_PLAN_SCHEMA = obj(
    {
        "schema_version": {"const": "1.0"},
        "scene_sha256": HASH,
        "requests": array(PLANNED_CAPTURE),
        "capabilities": CAPABILITIES_SCHEMA,
        "image_budget_after_references": {
            "type": "integer",
            "minimum": 0,
            "maximum": 12,
        },
        "note": TEXT,
    }
)
ENVIRONMENT = obj(
    {
        "python": TEXT,
        "platform": TEXT,
        "dependencies": {
            "type": "object",
            "additionalProperties": nullable(
                obj({"version": TEXT, "record_sha256": HASH})
            ),
        },
    }
)
PLAN_SCHEMA = obj(
    {
        "schema_version": {"const": "1.0"},
        "kind": {"const": "scene-preparation"},
        "runtime_sha256": HASH,
        "scope_sha256": HASH,
        "environment": ENVIRONMENT,
        "max_dependency_files": {"type": "integer", "minimum": 1, "maximum": 1024},
        "mapping_adapter_version": TEXT,
        "review_profile": {"enum": ["general", "static-visual", "animated-visual"]},
        "scene_sha256": HASH,
        "scene_identity": {"type": "object"},
        "bundle": TEXT,
        "candidate": TEXT,
        "brief": nullable(TEXT),
        "files": FILES,
        "request_sha256": HASH,
        "mapping_review": {"enum": ["pending", "not_applicable"]},
        "routes": COUNT,
        "limitations": array(TEXT),
        "plan_sha256": HASH,
    }
)
PLAN_SCHEMA["properties"].update(
    previous_plan_sha256=HASH,
    binding=obj(
        {
            "scope_unchanged": {"type": "boolean"},
            "model_calls": {"const": 0},
            "previous_scene_sha256": HASH,
            "previous_scope_sha256": HASH,
            "evaluation_policy_changed": {"type": "boolean"},
            "requires_scope_approval": {"type": "boolean"},
            "policy_changes": {"type": "object"},
            "runtime_migration": {"type": "boolean"},
            "reviewer": nullable(TEXT),
            "reason": nullable(TEXT),
            "previous_environment": nullable(ENVIRONMENT),
            "previous_runtime_sha256": HASH,
        }
    ),
)
PLAN_SCHEMA["properties"]["binding"]["properties"][
    "judge_coverage_drift"
] = JUDGE_COVERAGE_DRIFT_SCHEMA
SCOPE_SCHEMA = deepcopy(SCOPE_SCHEMA)
from .briefs import BRIEF_SCHEMA

brief = deepcopy(BRIEF_SCHEMA)
brief["properties"].pop("mapping_review")
brief["required"].remove("mapping_review")
SCOPE_SCHEMA["properties"].update(
    brief=nullable(brief),
    rubric=RUBRIC_SCHEMA,
    capture_requirements=array(CAPTURE_REQUIREMENT),
)
CAPTURE_ROW = obj(
    {
        "request_id": TEXT,
        "requirement_ids": array(TEXT),
        "purpose": TEXT,
        "targets": array(TEXT),
        "times_seconds": array({"type": "number"}),
        "status": {"enum": ["supplied", "missing", "invalid"]},
        "gaps": array(TEXT),
        "view_ids": array(TEXT),
    }
)
CAPTURE_ROW["properties"].update(
    view_role=TEXT,
    camera_guidance=nullable(TEXT),
    camera_id=nullable(TEXT),
    projection=nullable(TEXT),
    sharing_group=nullable(TEXT),
    eligible_view_ids=array(TEXT),
    caller_reason=nullable(TEXT),
)
PREPARED_RESULT_SCHEMA = obj(
    {
        "schema_version": {"const": "1.0"},
        "plan_sha256": HASH,
        "scene_sha256": HASH,
        "candidate": TEXT,
        "mode": {"enum": ["checks", "judge", "both"]},
        "mapping_review": {"enum": ["reviewed", "pending", "not_applicable"]},
        "scope_sha256": HASH,
        "approval": nullable(APPROVAL_SCHEMA),
        "execution_status": {"enum": ["completed", "partial", "failed"]},
        "errors": array(TEXT),
        "routes": COUNT,
        "decision": TEXT,
        "exit_code": {"enum": [0, 2, 3, 4]},
        "unchanged": {"type": "boolean"},
        "capture_counts": COUNT,
        "capture_requests": array(CAPTURE_ROW),
        "evidence_policy": {"type": ["object", "null"]},
        "evaluation_report": TEXT,
        "script_verdict": nullable(TEXT),
        "scope_verdict": nullable(TEXT),
        "judge_counts": COUNT,
        "limitations": array(TEXT),
        "findings": array({"type": "object"}),
        "comparison": {"type": ["object", "null"]},
    }
)
PREPARED_RESULT_SCHEMA["properties"]["next_action"] = {
    "enum": [
        "none",
        "review_specification",
        "repair_scene",
        "provide_evidence",
        "review_finding",
        "fix_environment",
    ]
}
PREPARED_RESULT_SCHEMA["properties"][
    "judge_coverage_drift"
] = JUDGE_COVERAGE_DRIFT_SCHEMA
EVIDENCE_RESULT_SCHEMA = obj(
    {
        "schema_version": {"const": "1.0"},
        "plan_sha256": HASH,
        "scene_sha256": HASH,
        "capture_requests": array(CAPTURE_ROW),
        "evidence_policy": {"type": "object"},
        "model_calls": {"const": 0},
        "errors": array(TEXT),
        "execution_status": {"enum": ["completed", "failed"]},
        "exit_code": {"enum": [0, 3, 4]},
    }
)
ENVELOPE_SCHEMA = obj(
    {
        "schema_version": {"const": "1.0"},
        "operation": {
            "enum": [
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
                "parse",
            ]
        },
        "run_id": TEXT,
        "status": {
            "enum": ["completed", "partial", "failed", "cancelled", "timed_out"]
        },
        "exit_code": {"enum": [0, 2, 3, 4]},
        "reused": {"type": "boolean"},
        "data": {"type": ["object", "null"]},
        "errors": array(
            obj(
                {
                    "code": TEXT,
                    "phase": TEXT,
                    "message": TEXT,
                    "retryable": {"type": "boolean"},
                }
            )
        ),
        "events": array({"type": "object"}),
    }
)
from .accounting import METRICS_SCHEMA

ENVELOPE_SCHEMA["properties"]["metrics"] = METRICS_SCHEMA
ENVELOPE_SCHEMA["properties"]["isolation"] = {"type": "object"}
# Progress and result counts can exceed the review item limit; they are not model prompts.
for schema, key in ((ENVELOPE_SCHEMA, "events"), (PREPARED_RESULT_SCHEMA, "findings")):
    schema["properties"][key].pop("maxItems", None)

SCHEMAS = {
    "application-envelope-v1": ENVELOPE_SCHEMA,
    "preparation-plan-v1": PLAN_SCHEMA,
    "capture-plan-v1": CAPTURE_PLAN_SCHEMA,
    "scope-v1": SCOPE_SCHEMA,
    "scope-approval-v1": APPROVAL_SCHEMA,
    "prepared-result-v1": PREPARED_RESULT_SCHEMA,
    "evidence-result-v1": EVIDENCE_RESULT_SCHEMA,
}

from .runtime_dependencies import RUNTIME_DEPENDENCY_RECEIPT_SCHEMA

SCHEMAS["runtime-dependency-receipt-v1"] = RUNTIME_DEPENDENCY_RECEIPT_SCHEMA

from .triage import (
    POLICY_SCHEMA as TRIAGE_POLICY_SCHEMA,
    LEGACY_RESPONSE_SCHEMA as TRIAGE_LEGACY_RESPONSE_SCHEMA,
    RESPONSE_SCHEMA as TRIAGE_RESPONSE_SCHEMA,
    RESULT_SCHEMA as TRIAGE_RESULT_SCHEMA,
    LEGACY_RESULT_SCHEMA as TRIAGE_LEGACY_RESULT_SCHEMA,
)

SCHEMAS["triage-policy-v1"] = TRIAGE_POLICY_SCHEMA
SCHEMAS["triage-response-v1"] = TRIAGE_LEGACY_RESPONSE_SCHEMA
SCHEMAS["triage-response-v1.1"] = TRIAGE_RESPONSE_SCHEMA
SCHEMAS["triage-result-v1"] = TRIAGE_LEGACY_RESULT_SCHEMA
SCHEMAS["triage-result-v1.1"] = TRIAGE_RESULT_SCHEMA

from .accounting import COST_CONTEXT_SCHEMA

SCHEMAS["cost-context-v1"] = COST_CONTEXT_SCHEMA

SCHEMAS["invocation-metrics-v1"] = METRICS_SCHEMA
from .assumption_audit import (
    RESPONSE_SCHEMA as AUDIT_RESPONSE_SCHEMA,
    DECLARATIONS_SCHEMA,
)
from .external_evidence import PERFORMANCE, ENGINE_RECEIPT
from .preparation import RAW_BRIEF_SCHEMA

SCHEMAS["audit-response-v1"] = AUDIT_RESPONSE_SCHEMA
SCHEMAS["audit-declarations-v1"] = DECLARATIONS_SCHEMA
SCHEMAS["viewer-performance-v1"] = PERFORMANCE
SCHEMAS["external-engine-receipt-v1"] = ENGINE_RECEIPT
SCHEMAS["raw-brief-v1"] = RAW_BRIEF_SCHEMA
from .engine_adapter import CONFIG as ENGINE_ADAPTER_SCHEMA

SCHEMAS["engine-adapter-v1"] = ENGINE_ADAPTER_SCHEMA
