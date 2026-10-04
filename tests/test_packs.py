"""Extension conformance, trust boundaries and consumer-specific acceptance."""

from pathlib import Path
import json
import shutil
import pytest
from pxr import Usd, Sdf
from scene_acceptance import evaluate
from scene_acceptance.contract_upgrade import copy_replay_bundle, upgrade_copied_contracts
from scene_acceptance.model import sha, ContractError, MissingEvidence
from scene_acceptance.packs import (
    Pack,
    CheckSpec,
    Outcome,
    default_registry,
    PackRegistry,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evaluation/packs-v1/fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())


def run(d, **kwargs):
    return evaluate(
        "contract.json",
        "scene.usda",
        bundle_root=d,
        baseline_path="baseline.usda" if (d / "baseline.usda").exists() else None,
        **kwargs,
    )


@pytest.mark.parametrize("case", MANIFEST["cases"], ids=lambda x: x["id"])
def test_frozen_cases(case, tmp_path):
    d = copy_replay_bundle(FIXTURES / case["id"], tmp_path / "bundle")
    if any(
        x["pack"] == "nvidia.asset-validator"
        for x in json.loads((d / "contract.json").read_text())["checks"]
    ):
        pytest.importorskip("usd_validation_nvidia")
    if case["approved_packs"]:
        pytest.importorskip("studio_mesh_pack")
    r = run(d, approved_packs=case["approved_packs"])
    assert r["verdict"] == case["expected"], r
    for path, digest in MANIFEST["files"].items():
        if path.startswith(case["id"] + "/"):
            assert sha(FIXTURES / path) == digest


@pytest.fixture
def bundle(tmp_path):
    d = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "material_correct", d)
    upgrade_copied_contracts(d)
    return d


def edit(d, fn):
    p = d / "contract.json"
    c = json.loads(p.read_text())
    fn(c)
    p.write_text(json.dumps(c))


def custom(d, fn):
    spec = CheckSpec(
        fn,
        {"type": "object", "additionalProperties": False},
        "Test provider",
        "Explicit test coverage",
    )
    pack = Pack(
        "test.provider",
        "1.0.0",
        "Conformance tests",
        {"check": spec},
        (str(Path(__file__)),),
    )
    registry = default_registry()
    registry.add(pack)

    def add(c):
        c["packs"]["test.provider"] = {"version": "1.0.0"}
        c["checks"].append(
            {
                "id": "custom",
                "pack": "test.provider",
                "check": "check",
                "parameters": {},
                "required": True,
            }
        )

    edit(d, add)
    return registry


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        Outcome("BOGUS", "bad"),
        Outcome("PASS", "", {}),
        Outcome("PASS", "bad", {"value": float("nan")}),
        Outcome("NOT_APPLICABLE", "not applicable"),
    ],
)
def test_bad_provider_cannot_accept(bundle, value):
    r = run(bundle, pack_registry=custom(bundle, lambda *_: value))
    assert r["verdict"] == "EVALUATION_ERROR", r


@pytest.mark.parametrize(
    "exc", [RuntimeError("crashed"), MissingEvidence("reference absent")]
)
def test_provider_error_or_unknown_does_not_disappear(bundle, exc):
    def fail(*_):
        raise exc

    r = run(bundle, pack_registry=custom(bundle, fail))
    assert r["verdict"] == (
        "INSUFFICIENT_EVIDENCE"
        if isinstance(exc, MissingEvidence)
        else "EVALUATION_ERROR"
    )
    assert len(r["checks"]) == 4


@pytest.mark.parametrize(
    "mutation", ["file", "memory", "file_then_rerecord", "source", "pack_source"]
)
def test_mutations_invalidate_run(bundle, mutation, tmp_path):
    source = tmp_path / "provider.py"
    source.write_text("# original\n")
    if mutation == "source":
        (bundle / "reference.json").write_text("{}")
        edit(bundle, lambda c: c["evidence_sources"].append("reference.json"))

    def change(ctx, p):
        if mutation == "memory":
            ctx.artifact.stage.DefinePrim("/Injected", "Xform")
        elif mutation == "pack_source":
            source.write_text("# modified\n")
        elif mutation == "source":
            (ctx.bundle.root / "reference.json").write_text('{"changed":true}')
        else:
            with ctx.artifact.root.open("a") as f:
                f.write("\n# changed\n")
            if mutation == "file_then_rerecord":
                ctx.bundle.record(ctx.artifact.root)
        return Outcome("PASS", "Attempted misleading pass")

    registry = custom(bundle, change)
    if mutation == "pack_source":
        registry._packs["test.provider"] = Pack(
            "test.provider",
            "1.0.0",
            "Source mutation test",
            {"check": CheckSpec(change, {"type": "object"}, "Change", "Test")},
            (str(source),),
        )
    r = run(bundle, pack_registry=registry)
    assert r["verdict"] == "EVALUATION_ERROR", r


def test_parameter_mutation_does_not_change_contract(bundle):
    def modify(ctx, p):
        p["extra"] = "injected"
        return Outcome("PASS", "Test complete")

    registry = custom(bundle, modify)
    before = sha(bundle / "contract.json")
    r = run(bundle, pack_registry=registry)
    assert r["verdict"] == "ACCEPT_FOR_USE"
    assert r["coverage"]["planned"][-1]["parameters"] == {}
    assert sha(bundle / "contract.json") == before


@pytest.mark.parametrize(
    "kind",
    [
        "all_advisory",
        "duplicate_id",
        "cycle",
        "unknown_prerequisite",
        "undeclared_pack",
        "unknown_parameter",
        "reserved_id",
        "wrong_id_type",
        "bad_pack_version",
    ],
)
def test_contract_errors_are_structured(bundle, kind):
    def corrupt(c):
        a, b = c["checks"]
        if kind == "all_advisory":
            a["required"] = b["required"] = False
        elif kind == "duplicate_id":
            b["id"] = a["id"]
        elif kind == "cycle":
            a["after"] = [b["id"]]
            b["after"] = [a["id"]]
        elif kind == "unknown_prerequisite":
            a["after"] = ["absent"]
        elif kind == "undeclared_pack":
            c["packs"]["unused"] = {"version": "1.0.0"}
        elif kind == "unknown_parameter":
            a["parameters"]["typo"] = True
        elif kind == "reserved_id":
            a["id"] = "core.fake"
        elif kind == "wrong_id_type":
            c["id"] = 12
        else:
            c["packs"]["openusd"]["version"] = "latest"

    edit(bundle, corrupt)
    assert run(bundle)["verdict"] == "EVALUATION_ERROR"


def test_required_missing_dependency_is_error(bundle, monkeypatch):
    from scene_acceptance import packs

    original = packs.metadata.distribution

    def unavailable(name):
        if name == "usd-validation-nvidia":
            raise packs.metadata.PackageNotFoundError(name)
        return original(name)

    monkeypatch.setattr(packs.metadata, "distribution", unavailable)
    d = FIXTURES / "nvidia_correct"
    r = run(d)
    assert r["verdict"] == "EVALUATION_ERROR"
    assert r["checks"][-1]["status"] == "ERROR"
    # Unselected NVIDIA dependency does not block the material profile.
    assert run(bundle)["verdict"] == "ACCEPT_FOR_USE"


def test_registry_rejects_duplicates_and_incompatible_api():
    p = default_registry().get("materials")
    with pytest.raises(ContractError):
        PackRegistry([p, p])
    with pytest.raises(ContractError):
        Pack(
            "new", "1.0.0", "invalid", dict(p.checks), p.source_files, api_version="2.0"
        )


def test_discovery_does_not_import_plugins(monkeypatch):
    from scene_acceptance import packs

    class EP:
        name = "untrusted.sample"

        def load(self):
            raise AssertionError("Discovery imported a plugin")

    monkeypatch.setattr(packs.metadata, "entry_points", lambda **_: [EP()])
    assert packs.installed_pack_names() == ["untrusted.sample"]
    assert default_registry().get("materials")


@pytest.mark.parametrize(
    "value", ["https://example.invalid/a.png", "../outside.png", "tile.<UDIM>.png"]
)
def test_asset_path_admission_before_stage_open(bundle, value, monkeypatch):
    p = bundle / "scene.usda"
    p.write_text(p.read_text().replace("pixel.png", value))

    def forbidden(*a, **k):
        raise AssertionError("Stage must not open before dependency admission")

    monkeypatch.setattr(Usd.Stage, "Open", forbidden)
    r = run(bundle)
    assert r["verdict"] == "EVALUATION_ERROR", r
    assert not any("AssertionError" in x["reason"] for x in r["checks"])


def test_time_sampled_asset_dependency_is_recorded(bundle):
    s = Usd.Stage.Open(str(bundle / "scene.usda"))
    a = s.GetAttributeAtPath("/World/Looks/Coating/Texture.inputs:file")
    a.Set(Sdf.AssetPath("second.png"), 1)
    s.GetRootLayer().Save()
    edit(bundle, lambda c: c["allowed_dependencies"].append("second.png"))
    r = run(bundle)
    assert r["verdict"] == "REJECT"
    assert "second.png" in r["identity"]["missing_files"]


def test_pack_version_and_parameters_survive_in_report(bundle):
    r = run(bundle)
    assert r["identity"]["packs"]["materials"]["version"] == default_registry().get("materials").version
    assert len(r["identity"]["packs"]["materials"]["implementation_sha256"]) == 64
    assert r["coverage"]["by_pack"]["materials"]["PASS"] == 1
    assert r["coverage"]["planned"][1]["parameters"]["bindings"] == {
        "/World/Panel": "/World/Looks/Coating"
    }


def test_contract_pin_blocks_changed_requirements(bundle):
    digest = sha(bundle / "contract.json")
    edit(bundle, lambda c: c.update(intended_use="Different purpose"))
    assert run(bundle, expected_contract_sha256=digest)["verdict"] == "EVALUATION_ERROR"


def test_prerequisite_failure_keeps_unknown_visible(tmp_path):
    d = copy_replay_bundle(FIXTURES / "failed_prerequisite", tmp_path / "bundle")
    r = run(d)
    assert r["verdict"] == "REJECT" and r["complete"] is False
    assert {x["id"]: x["status"] for x in r["checks"]}["motion.samples"] == "UNKNOWN"


def test_independent_checks_continue_after_provider_failure(bundle):
    def fail(*_):
        raise RuntimeError("Provider crashed")

    registry = custom(bundle, fail)
    edit(bundle, lambda c: c["checks"].insert(0, c["checks"].pop()))
    r = run(bundle, pack_registry=registry)
    assert [x["status"] for x in r["checks"]] == ["PASS", "ERROR", "PASS", "PASS"]


def test_legacy_extra_inputs_on_v2_return_structured_error(bundle):
    assert run(bundle, claims_path="claims.json")["verdict"] == "EVALUATION_ERROR"


def test_motion_does_not_accept_outside_authored_range(tmp_path):
    d = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "motion_correct", d)
    upgrade_copied_contracts(d)
    edit(d, lambda c: c["checks"][1]["parameters"]["samples"][-1].update(time_code=10))
    assert run(d)["verdict"] == "INSUFFICIENT_EVIDENCE"
