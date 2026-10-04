from pathlib import Path
import json, math, shutil, subprocess
import pytest
from pxr import Usd, UsdGeom, Gf
from scene_acceptance import evaluate
from scene_acceptance.checks import REGISTRY
from scene_acceptance.model import check, reduce_results, sha

FIXTURES = Path(__file__).resolve().parents[1] / "evaluation/fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def run(d, **kwargs):
    return evaluate(
        d / "contract.json",
        d / "scene.usda",
        bundle_root=d,
        baseline_path=d / "baseline.usda",
        claims_path=d / "claims.json" if (d / "claims.json").exists() else None,
        **kwargs,
    )


@pytest.fixture
def case(tmp_path):
    d = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "valid_edit", d)
    return d


def changed_contract(d, fn):
    c = json.loads((d / "contract.json").read_text())
    fn(c)
    write(d / "contract.json", c)


def change_y(path, y):
    s = Usd.Stage.Open(str(path))
    s.GetPrimAtPath("/World/Equipment/Pallet/Deck").GetAttribute(
        "xformOp:translate"
    ).Set(Gf.Vec3d(3, y, 0.1))
    s.GetRootLayer().Save()


@pytest.mark.parametrize("item", MANIFEST["cases"], ids=lambda x: x["id"])
def test_frozen_cases(item):
    d = FIXTURES / item["id"]
    before = {str(p): sha(p) for p in d.iterdir() if p.is_file()}
    r = run(d)
    assert r["verdict"] == item["expected"]
    assert before == {str(p): sha(p) for p in d.iterdir() if p.is_file()}
    assert r["checks"]


@pytest.mark.parametrize(
    "statuses,expected,complete",
    [
        (["PASS"], "ACCEPT_FOR_USE", True),
        (["FAIL"], "REJECT", True),
        (["UNKNOWN"], "INSUFFICIENT_EVIDENCE", False),
        (["ERROR"], "EVALUATION_ERROR", False),
        (["NOT_APPLICABLE"], "EVALUATION_ERROR", False),
        (["FAIL", "ERROR"], "REJECT", False),
        (["FAIL", "UNKNOWN"], "REJECT", False),
        (["PASS", "ERROR"], "EVALUATION_ERROR", False),
        (["PASS", "UNKNOWN"], "INSUFFICIENT_EVIDENCE", False),
        ([], "EVALUATION_ERROR", False),
    ],
)
def test_decision_policy(statuses, expected, complete):
    assert reduce_results(
        [check(str(i), s, "test") for i, s in enumerate(statuses)]
    ) == (expected, complete)


def test_optional_unknown_does_not_block():
    assert reduce_results(
        [check("a", "PASS", "known"), check("b", "UNKNOWN", "optional", required=False)]
    ) == ("ACCEPT_FOR_USE", True)


@pytest.mark.parametrize(
    "failure", ["exception", "missing", "malformed", "not_applicable", "nan"]
)
def test_checker_failure_never_passes(case, failure):
    providers = dict(REGISTRY)
    if failure == "exception":

        def fail(ctx):
            raise RuntimeError("injected provider failure")

        providers["target"] = fail
    elif failure == "missing":
        providers.pop("target")
    elif failure == "malformed":
        providers["target"] = lambda ctx: {"id": "target", "status": "PASS"}
    elif failure == "not_applicable":
        providers["target"] = lambda ctx: check(
            "target", "NOT_APPLICABLE", "Cannot skip a required edit check"
        )
    else:
        providers["target"] = lambda ctx: check(
            "target", "PASS", "Bad provider data", {"value": float("nan")}
        )
    result = run(case, registry=providers)
    assert result["verdict"] == "EVALUATION_ERROR"
    assert len(result["checks"]) == 6
    json.dumps(result, allow_nan=False)


def test_violation_retained_when_another_check_errors(case):
    change_y(case / "scene.usda", 1.4)
    providers = dict(REGISTRY)
    providers["preserved"] = lambda ctx: (_ for _ in ()).throw(
        RuntimeError("unavailable")
    )
    r = run(case, registry=providers)
    assert r["verdict"] == "REJECT" and not r["complete"]
    assert {x["id"]: x["status"] for x in r["checks"]}["preserved"] == "ERROR"


def test_inputs_changed_during_run_blocks_acceptance(case):
    providers = dict(REGISTRY)

    def mutate(ctx):
        result = REGISTRY["target"](ctx)
        (case / "scene.usda").write_text(
            (case / "scene.usda").read_text() + "\n# changed during checks\n"
        )
        return result

    providers["target"] = mutate
    assert run(case, registry=providers)["verdict"] == "EVALUATION_ERROR"


def test_pinned_contract_rejects_changed_requirements(case):
    h = sha(case / "contract.json")
    changed_contract(case, lambda c: c["target"].update(center_m=[3, 1.9, 0.1]))
    assert run(case, expected_contract_sha256=h)["verdict"] == "EVALUATION_ERROR"


def test_stale_in_memory_layer_does_not_hide_changed_file(case):
    assert run(case)["verdict"] == "ACCEPT_FOR_USE"
    text = (case / "scene.usda").read_text().replace("(3, 1.75, 0.1)", "(3, 1.4, 0.1)")
    assert text != (case / "scene.usda").read_text()
    (case / "scene.usda").write_text(text)
    assert run(case)["verdict"] == "REJECT"


@pytest.mark.parametrize(
    "change", ["candidate", "contract", "baseline", "dependency", "checker"]
)
def test_receipt_binds_every_revision(tmp_path, change, monkeypatch):
    import scene_acceptance.engine as engine

    d = tmp_path / "bundle"
    shutil.copytree(
        FIXTURES / "declared_local_reference"
        if change == "dependency"
        else FIXTURES / "valid_edit",
        d,
    )
    changed_contract(d, lambda c: c["checks"]["required"].append("freshness"))
    first = run(d)
    assert first["verdict"] == "INSUFFICIENT_EVIDENCE"
    receipt = d / "receipt.json"
    write(receipt, first)
    assert run(d, receipt_path=receipt)["verdict"] == "ACCEPT_FOR_USE"
    if change == "contract":
        changed_contract(d, lambda c: c.update(id="revised-brief"))
    elif change == "checker":
        monkeypatch.setattr(engine, "implementation_digest", lambda: "0" * 64)
    else:
        path = (
            d
            / (
                {
                    "candidate": "scene.usda",
                    "baseline": "baseline.usda",
                    "dependency": "part.usda",
                }[change]
            )
        )
        path.write_text(path.read_text() + "\n# revision changed\n")
    result = run(d, receipt_path=receipt)
    assert result["verdict"] == "REJECT"
    assert (
        next(x for x in result["checks"] if x["id"] == "freshness")["status"] == "FAIL"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "nonfinite",
        "overflow",
        "required_advisory_overlap",
        "empty",
        "unknown_field",
    ],
)
def test_strict_contracts(case, mutation):
    p = case / "contract.json"
    c = json.loads(p.read_text())
    if mutation == "duplicate":
        p.write_text(
            p.read_text().replace(
                '"schema_version": "1.0"',
                '"schema_version": "1.0", "schema_version": "1.0"',
            )
        )
    elif mutation == "nonfinite":
        p.write_text(p.read_text().replace("1e-06", "NaN"))
    elif mutation == "overflow":
        p.write_text(p.read_text().replace("1e-06", "1e999"))
    elif mutation == "required_advisory_overlap":
        c["checks"]["advisory"].append("target")
        write(p, c)
    elif mutation == "empty":
        p.write_text("{}")
    else:
        c["typo"] = 1
        write(p, c)
    r = run(case)
    assert r["verdict"] == "EVALUATION_ERROR"
    assert r["identity"].get("contract_sha256") == sha(p)


@pytest.mark.parametrize("angle", [-120, -45, 0, 30, 90, 225])
def test_transforms_against_analytic_corner_extreme(case, angle):
    s = Usd.Stage.Open(str(case / "scene.usda"))
    p = UsdGeom.Xform(s.GetPrimAtPath("/World/Equipment/Pallet"))
    p.AddTranslateOp().Set(Gf.Vec3d(3, 2.5, 0.1))
    p.AddRotateZOp().Set(angle)
    s.GetPrimAtPath("/World/Equipment/Pallet/Deck").GetAttribute(
        "xformOp:translate"
    ).Set(Gf.Vec3d(0, 0, 0))
    s.GetRootLayer().Save()
    changed_contract(case, lambda c: c["target"].update(center_m=[3, 2.5, 0.1]))
    r = run(case)
    assert r["verdict"] == "ACCEPT_FOR_USE"
    actual = next(x for x in r["checks"] if x["id"] == "layout")["evidence"]["bounds"][
        "/World/Equipment/Pallet/Deck"
    ]["min"][1]
    expected = (
        2.5
        - (
            abs(math.sin(math.radians(angle))) * 1.2
            + abs(math.cos(math.radians(angle)))
        )
        / 2
    )
    # Authored xformOp:scale is float3. Allow its float32 rounding,
    # while remaining tighter than the 1e-6 metre contract tolerance.
    assert actual == pytest.approx(expected, abs=5e-8, rel=0)


def test_degenerate_cube_is_not_supported(case):
    s = Usd.Stage.Open(str(case / "scene.usda"))
    s.GetPrimAtPath("/World/Equipment/Pallet/Deck").GetAttribute("xformOp:scale").Set(
        Gf.Vec3d(0, 1, 0.2)
    )
    s.GetRootLayer().Save()
    assert run(case)["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_symlink_outside_bundle_is_not_read(case, tmp_path):
    outside = tmp_path / "external.usda"
    shutil.copy2(case / "scene.usda", outside)
    (case / "scene.usda").unlink()
    (case / "scene.usda").symlink_to(outside)
    assert run(case)["verdict"] == "EVALUATION_ERROR"


def test_remote_reference_blocked_before_stage_open(monkeypatch):
    d = FIXTURES / "remote_reference"

    def forbidden(*args, **kwargs):
        raise AssertionError("Stage composition must not be attempted")

    monkeypatch.setattr(Usd.Stage, "Open", forbidden)
    r = run(d)
    assert r["verdict"] == "EVALUATION_ERROR"
    assert (
        "URI" in r["checks"][0]["reason"]
        or "Only ordinary local paths" in r["checks"][0]["reason"]
    )


def test_current_verdict_recomputed_even_if_receipt_says_pass(case):
    changed_contract(case, lambda c: c["checks"]["required"].append("freshness"))
    change_y(case / "scene.usda", 1.4)
    r = run(case)
    r["verdict"] = "ACCEPT_FOR_USE"
    write(case / "receipt.json", r)
    assert run(case, receipt_path=case / "receipt.json")["verdict"] == "REJECT"


@pytest.mark.parametrize(
    "fixture,exit_code",
    [
        ("valid_edit", 0),
        ("wrong_but_clear", 2),
        ("missing_friction_required", 3),
        ("malformed_scene", 4),
    ],
)
def test_cli_reports_and_exit_codes(tmp_path, fixture, exit_code):
    import sys

    d = FIXTURES / fixture
    out = tmp_path / "report"
    cmd = [
        sys.executable,
        "-m",
        "scene_acceptance.cli",
        "--contract",
        str(d / "contract.json"),
        "--candidate",
        str(d / "scene.usda"),
        "--baseline",
        str(d / "baseline.usda"),
        "--bundle-root",
        str(d),
        "--out",
        str(out),
    ]
    if (d / "claims.json").exists():
        cmd += ["--claims", str(d / "claims.json")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == exit_code, r.stderr
    assert (out / "report.html").is_file()
    manifest = json.loads((out / "manifest.json").read_text())
    assert all(sha(out / k) == v for k, v in manifest["files"].items())
    again = subprocess.run(cmd, capture_output=True, text=True)
    assert again.returncode == 4 and "must be a new directory" in again.stderr


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("missing", "INSUFFICIENT_EVIDENCE"),
        ("metric", "REJECT"),
        ("path", "REJECT"),
        ("unit", "EVALUATION_ERROR"),
        ("basis", "REJECT"),
        ("match", "ACCEPT_FOR_USE"),
    ],
)
def test_required_claim_cannot_be_omitted_or_substituted(tmp_path, mutation, expected):
    d = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "claim_geometry_supported", d)
    claim = json.loads((d / "claims.json").read_text())["claims"][0]
    required = {k: claim[k] for k in ["id", "path", "metric", "unit", "basis"]}
    if mutation == "missing":
        required["id"] = "another-required-property"
    elif mutation == "metric":
        required["metric"] = "mass"
        required["unit"] = "kg"
    elif mutation == "path":
        required["path"] = "/World/Equipment/Fixed/Block"
    elif mutation == "unit":
        data = json.loads((d / "claims.json").read_text())
        data["claims"][0]["unit"] = "kg"
        write(d / "claims.json", data)
    elif mutation == "basis":
        required["basis"] = "measured"
    changed_contract(d, lambda c: c.update(required_claims=[required]))
    assert run(d)["verdict"] == expected


def test_required_claims_cannot_be_advisory(case):
    changed_contract(
        case,
        lambda c: c.update(
            required_claims=[
                {"id": "x", "path": "/World/A", "metric": "mass", "unit": "kg"}
            ]
        ),
    )
    assert run(case)["verdict"] == "EVALUATION_ERROR"


def test_nonfinite_geometry_cannot_pass(case):
    s = Usd.Stage.Open(str(case / "scene.usda"))
    s.GetPrimAtPath("/World/Equipment/Pallet/Deck").GetAttribute("xformOp:scale").Set(
        Gf.Vec3d(float("nan"), 1, 0.2)
    )
    s.GetRootLayer().Save()
    assert run(case)["verdict"] in ["INSUFFICIENT_EVIDENCE", "EVALUATION_ERROR"]


def test_report_html_escapes_untrusted_text(case, tmp_path):
    from scene_acceptance.report import write_report

    changed_contract(case, lambda c: c.update(id="<script>alert(1)</script>"))
    r = run(case)
    out = tmp_path / "report"
    write_report(r, out)
    rendered = (out / "report.html").read_text()
    assert "<script>alert(1)</script>" not in rendered
    assert "&lt;script&gt;" in rendered


@pytest.mark.parametrize("field", ["id", "intended_use"])
def test_invalid_display_field_still_returns_a_structured_error(case, field):
    changed_contract(case, lambda c: c.update({field: 5}))
    result = run(case)
    assert result["verdict"] == "EVALUATION_ERROR"
    assert result["identity"]["contract_sha256"] == sha(case / "contract.json")
    json.dumps(result, allow_nan=False)
