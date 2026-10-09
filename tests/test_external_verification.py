"""Hashes cannot turn a producer claim into proof of execution."""

import pytest
from jsonschema import ValidationError
from scene_acceptance import evaluate
from scene_acceptance.external_evidence import engine_tests, ENGINE_RECEIPT
from scene_acceptance.packs import default_registry
from scene_acceptance.model import ContractError, MissingEvidence, sha
from test_extensions_evidence import receipts
from test_review import save


def engine_case(tmp_path, native="PASS", normalized="PASS"):
    ctx, engine, _ = receipts(tmp_path)
    save(tmp_path / "native.json", {"status": native})
    receipt = dict(
        schema_version="1.0",
        scene_sha256=ctx.artifact.artifact_set_sha256,
        engine=engine,
        provider="other",
        profile_id="test",
        profile_sha256="b" * 64,
        execution_status="completed",
        producer="synthetic fixture",
        limitations=["No real engine"],
        attachments=[
            dict(
                path="native.json",
                sha256=sha(tmp_path / "native.json"),
                description="Native control",
            )
        ],
        tests=[
            dict(
                id="contact",
                phase="runtime",
                status=normalized,
                reason="Control",
                evidence_paths=["native.json"],
            )
        ],
    )
    save(tmp_path / "receipt.json", receipt)
    params = dict(
        receipt="receipt.json",
        engine=engine,
        provider="other",
        profile_id="test",
        profile_sha256="b" * 64,
        required_tests=[dict(id="contact", phase="runtime")],
    )
    verification = dict(
        receipt_sha256=sha(tmp_path / "receipt.json"),
        basis="Synthetic caller-owned collection",
        native_report="native.json",
        tests=[
            dict(
                id="contact",
                phase="runtime",
                status_pointer="/status",
                status_mapping={"PASS": "PASS", "FAIL": "FAIL"},
            )
        ],
    )
    return ctx, params, verification, receipt


def evaluate_external(tmp_path, params):
    pack = default_registry().get("external.evidence").describe()
    contract = dict(
        schema_version="2.0",
        id="receipt-control",
        intended_use="Synthetic control",
        profile=dict(id="test", version="1.0.0"),
        artifact_format="usd-local-v1",
        allowed_dependencies=[],
        evidence_sources=["receipt.json", "native.json"],
        packs={
            "external.evidence": dict(
                version=pack["version"], sha256=pack["implementation_sha256"]
            )
        },
        checks=[
            dict(
                id="engine",
                pack="external.evidence",
                check="engine_tests",
                parameters=params,
                required=True,
            )
        ],
    )
    save(tmp_path / "contract.json", contract)
    return evaluate("contract.json", "scene.usda", bundle_root=tmp_path)


def test_forged_pass_with_correct_native_hash_cannot_accept(tmp_path):
    _, params, _, _ = engine_case(tmp_path, native="FAIL", normalized="PASS")
    result = evaluate_external(tmp_path, params)
    row = next(r for r in result["checks"] if r["id"] == "engine")
    assert row["status"] == "UNKNOWN", result
    assert row["evidence"]["observations"]["execution_provenance"] == "unverified"
    assert result["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_even_a_pinned_receipt_cannot_contradict_native_status(tmp_path):
    _, params, verification, _ = engine_case(tmp_path, native="FAIL", normalized="PASS")
    result = evaluate_external(tmp_path, dict(params, verification=verification))
    row = next(r for r in result["checks"] if r["id"] == "engine")
    assert row["status"] == "ERROR" and "contradicts" in row["reason"], result
    assert result["verdict"] != "ACCEPT_FOR_USE"


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "missing-mapping",
        "duplicate-mapping",
        "native-path",
        "unknown-native-status",
    ],
)
def test_verification_cannot_silently_change_scope(tmp_path, change):
    ctx, params, verification, _ = engine_case(tmp_path)
    if change == "hash":
        verification["receipt_sha256"] = "0" * 64
    elif change == "missing-mapping":
        verification["tests"][0]["id"] = "different"
    elif change == "duplicate-mapping":
        verification["tests"] *= 2
    elif change == "native-path":
        verification["native_report"] = "another.json"
    else:
        verification["tests"][0]["status_mapping"] = {"other": "PASS"}
    with pytest.raises((MissingEvidence, ContractError)):
        engine_tests(ctx, dict(params, verification=verification))


def test_receipt_cannot_self_attest(tmp_path):
    from jsonschema import Draft202012Validator

    _, _, verification, receipt = engine_case(tmp_path)
    receipt["verification"] = verification
    with pytest.raises(ValidationError):
        Draft202012Validator(ENGINE_RECEIPT).validate(receipt)


def test_caller_verified_receipt_passes_public_contract(tmp_path):
    _, params, verification, _ = engine_case(tmp_path)
    result = evaluate_external(tmp_path, dict(params, verification=verification))
    assert result["verdict"] == "ACCEPT_FOR_USE", result


@pytest.mark.parametrize("role", ["triage", "audit"])
@pytest.mark.parametrize("symlink", [False, True])
def test_producer_cannot_supply_model_execution_config(tmp_path, role, symlink):
    from scene_acceptance.assumption_audit import run_audit
    from scene_acceptance.triage import run_triage

    root = tmp_path / "bundle"
    root.mkdir()
    config = root / "config.json"
    save(config, {})
    if symlink:
        link = tmp_path / "caller.json"
        link.symlink_to(config)
        config = link
    with pytest.raises(ContractError, match="outside the producer"):
        if role == "audit":
            run_audit(
                bundle_root=root,
                candidate="scene.usda",
                out=tmp_path / "out",
                audit_config=config,
            )
        else:
            run_triage(
                bundle_root=root,
                review_root=tmp_path / "review",
                assessment=tmp_path / "assessment" / "a.json",
                expected_assessment_sha256="a" * 64,
                policy=tmp_path / "policy.json",
                expected_policy_sha256="b" * 64,
                triage_config=config,
                out=tmp_path / "out",
            )


@pytest.mark.parametrize("field", ["id", "status_pointer"])
def test_shared_native_mapping_preserves_nonblank_validation(field):
    from jsonschema import Draft202012Validator
    from scene_acceptance.engine_adapter import CONFIG

    row = dict(
        id="contact",
        phase="runtime",
        status_pointer="/status",
        status_mapping={"PASS": "PASS"},
    )
    row[field] = "  "
    with pytest.raises(ValidationError):
        Draft202012Validator(CONFIG["properties"]["tests"]).validate([row])
