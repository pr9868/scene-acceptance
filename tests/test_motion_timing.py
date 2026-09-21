"""Acceptance of clock changes, legal rescaling and incomplete timing evidence."""
from pathlib import Path
import hashlib
import json
import shutil

import pytest
from pxr import Usd, UsdGeom, Gf

from scene_acceptance import evaluate

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evaluation/motion-timing-v1/fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())


def run(bundle):
    return evaluate("contract.json", "scene.usda", bundle_root=bundle)


@pytest.mark.parametrize("case", MANIFEST["cases"], ids=lambda x: x["id"])
def test_frozen_timing_controls(case):
    report = run(FIXTURES / case["id"])
    assert report["verdict"] == case["expected"], report
    for rel, digest in MANIFEST["files"].items():
        if rel.startswith(case["id"] + "/"):
            assert hashlib.sha256((FIXTURES / rel).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("rate,start,units", [
    (24.0, 0.0, 1.0), (24.0, 120.0, 1.0), (29.97, 1001.0, 1.0),
    (2.4, 0.1, 0.01), (1.3, -0.1, 1.0), (0.3, 0.2, 1.0),
])
def test_clock_and_keyframe_rescaling_preserves_seconds(tmp_path, rate, start, units):
    bundle = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "correct", bundle)
    stage = Usd.Stage.Open(str(bundle / "scene.usda"))
    stage.SetStartTimeCode(start)
    stage.SetEndTimeCode(start + 2 * rate)
    stage.SetTimeCodesPerSecond(rate)
    UsdGeom.SetStageMetersPerUnit(stage, units)
    attr = stage.GetPrimAtPath("/World/Panel").GetAttribute("xformOp:translate")
    attr.Clear()
    for elapsed in [0, 1, 2]:
        attr.Set(Gf.Vec3d(elapsed / (2 * units), 0, 0), Usd.TimeCode(start + elapsed * rate))
    stage.GetRootLayer().Save()
    report = run(bundle)
    assert report["verdict"] == "ACCEPT_FOR_USE", report
    seconds = next(c for c in report["checks"] if c["id"] == "motion.seconds")
    findings = seconds["evidence"]["observations"]["findings"]
    assert [x["elapsed_s"] for x in findings] == [0, 1, 2]
    for item, expected in zip(findings, [0, 0.5, 1]):
        assert item["observed"] == pytest.approx([expected, 0, 0], abs=1e-6)


def test_extending_stage_range_does_not_hide_fast_motion():
    report = run(FIXTURES / "padded_fast_motion")
    checks = {x["id"]: x for x in report["checks"]}
    assert checks["motion.clock"]["status"] == "PASS"
    assert checks["motion.seconds"]["status"] == "FAIL"
    midpoint = checks["motion.seconds"]["evidence"]["observations"]["findings"][1]
    assert midpoint["elapsed_s"] == 1
    assert midpoint["time_code"] == 24
    assert midpoint["observed"] == [1, 0, 0]
    assert midpoint["expected"] == [0.5, 0, 0]


def test_wrong_duration_keeps_dependent_positions_unresolved():
    report = run(FIXTURES / "clock_rate_changed")
    checks = {x["id"]: x for x in report["checks"]}
    assert checks["motion.clock"]["status"] == "FAIL"
    assert checks["motion.seconds"]["status"] == "UNKNOWN"
    finding = checks["motion.clock"]["evidence"]["observations"]["findings"][0]
    assert finding["observed"] == pytest.approx(2 / 24)
    assert finding["expected"] == 2


def test_positions_require_clock_even_without_explicit_prerequisite(tmp_path):
    bundle = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "missing_clock", bundle)
    path = bundle / "contract.json"
    c = json.loads(path.read_text())
    c["checks"] = [c["checks"][1]]
    c["checks"][0]["after"] = []
    path.write_text(json.dumps(c))
    report = run(bundle)
    assert report["verdict"] == "INSUFFICIENT_EVIDENCE", report


def test_original_time_code_contract_keeps_its_meaning(tmp_path):
    bundle = tmp_path / "bundle"
    shutil.copytree(ROOT / "evaluation/packs-v1/fixtures/motion_correct", bundle)
    path = bundle / "scene.usda"
    path.write_text(path.read_text().replace("timeCodesPerSecond = 1\n", "timeCodesPerSecond = 24\n"))
    report = run(bundle)
    assert report["verdict"] == "ACCEPT_FOR_USE", report
    check = next(c for c in report["checks"] if c["id"] == "motion.samples")
    assert check["evidence"]["observations"]["time_codes_per_second"] == 24
    assert check["evidence"]["observations"]["time_codes"] == [0, 1, 2]


@pytest.mark.parametrize("path", ["/World/Missing", "/World/Looks"])
def test_absent_or_nontransformable_target_rejects_instead_of_crashing(tmp_path, path):
    bundle = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "correct", bundle)
    contract = bundle / "contract.json"
    c = json.loads(contract.read_text())
    c["checks"][1]["parameters"]["path"] = path
    contract.write_text(json.dumps(c))
    report = run(bundle)
    assert report["verdict"] == "REJECT", report
    seconds = next(x for x in report["checks"] if x["id"] == "motion.seconds")
    assert seconds["status"] == "FAIL"
    assert "absent" in seconds["reason"].lower()
