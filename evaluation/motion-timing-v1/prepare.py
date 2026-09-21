"""Build bounded clock/seconds controls without running the evaluator."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "packs-v1/fixtures/motion_correct"


def main():
    fixtures = ROOT / "fixtures"
    fixtures.mkdir(exist_ok=False)
    base = (SOURCE / "scene.usda").read_text()
    cases = []
    definitions = [
        ("correct", "ACCEPT_FOR_USE", []),
        ("clock_rate_changed", "REJECT", [("timeCodesPerSecond = 1\n", "timeCodesPerSecond = 24\n")]),
        ("rescaled_24", "ACCEPT_FOR_USE", [("timeCodesPerSecond = 1\n", "timeCodesPerSecond = 24\n"), ("endTimeCode = 2\n", "endTimeCode = 48\n"), ("            1:", "            24:"), ("            2:", "            48:")]),
        ("shifted_start", "ACCEPT_FOR_USE", [("timeCodesPerSecond = 1\n", "timeCodesPerSecond = 24\n"), ("startTimeCode = 0\n", "startTimeCode = 120\n"), ("endTimeCode = 2\n", "endTimeCode = 168\n"), ("            0:", "            120:"), ("            1:", "            144:"), ("            2:", "            168:")]),
        ("padded_fast_motion", "REJECT", [("timeCodesPerSecond = 1\n", "timeCodesPerSecond = 24\n"), ("endTimeCode = 2\n", "endTimeCode = 48\n")]),
        ("missing_clock", "INSUFFICIENT_EVIDENCE", [("    timeCodesPerSecond = 1\n", "")]),
        ("zero_clock", "INSUFFICIENT_EVIDENCE", [("timeCodesPerSecond = 1\n", "timeCodesPerSecond = 0\n")]),
        ("negative_clock", "INSUFFICIENT_EVIDENCE", [("timeCodesPerSecond = 1\n", "timeCodesPerSecond = -24\n")]),
        ("missing_range", "INSUFFICIENT_EVIDENCE", [("    endTimeCode = 2\n", "")]),
        ("reversed_range", "INSUFFICIENT_EVIDENCE", [("startTimeCode = 0\n", "startTimeCode = 3\n")]),
        ("wrong_duration", "REJECT", [("endTimeCode = 2\n", "endTimeCode = 3\n")]),
        ("wrong_position", "REJECT", [("1: (0.5, 0, 0)", "1: (0.8, 0, 0)")]),
        ("required_rate_changed", "REJECT", [("timeCodesPerSecond = 1\n", "timeCodesPerSecond = 24\n"), ("endTimeCode = 2\n", "endTimeCode = 48\n"), ("            1:", "            24:"), ("            2:", "            48:")]),
        ("missing_units", "INSUFFICIENT_EVIDENCE", [("    metersPerUnit = 1\n", "")]),
        ("sample_outside_interval", "INSUFFICIENT_EVIDENCE", []),
        ("unordered_samples", "EVALUATION_ERROR", []),
        ("negative_sample", "EVALUATION_ERROR", []),
    ]
    for name, expected, substitutions in definitions:
        dest = fixtures / name
        dest.mkdir()
        text = base
        for old, new in substitutions:
            assert text.count(old) == 1, (name, old)
            text = text.replace(old, new)
        (dest / "scene.usda").write_text(text)
        shutil.copy2(SOURCE / "pixel.png", dest / "pixel.png")
        c = {
            "schema_version": "2.0", "id": "panel-two-second-motion",
            "intended_use": "Check stage duration and panel origins at elapsed seconds; no continuous-path claim",
            "profile": {"id": "panel-seconds", "version": "1.0.0"},
            "artifact_format": "usd-local-v1", "allowed_dependencies": ["pixel.png"], "evidence_sources": [],
            "packs": {"motion.timing": {"version": "1.0.0"}},
            "checks": [
                {"id": "motion.clock", "pack": "motion.timing", "check": "clock", "required": True,
                 "parameters": {"duration_s": 2, "tolerance_s": 1e-9}},
                {"id": "motion.seconds", "pack": "motion.timing", "check": "positions", "required": True,
                 "after": ["motion.clock"], "parameters": {
                     "path": "/World/Panel", "tolerance_m": 1e-6,
                     "samples": [{"elapsed_s": t, "world_origin_m": [t / 2, 0, 0]} for t in [0, 1, 2]],
                 }},
            ],
        }
        if name == "required_rate_changed":
            c["checks"][0]["parameters"]["time_codes_per_second"] = 1
        samples = c["checks"][1]["parameters"]["samples"]
        if name == "sample_outside_interval":
            samples[-1]["elapsed_s"] = 3
        elif name == "unordered_samples":
            samples.reverse()
        elif name == "negative_sample":
            samples[0]["elapsed_s"] = -1
        (dest / "contract.json").write_text(json.dumps(c, indent=2) + "\n")
        cases.append({"id": name, "expected": expected})
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {
        "scope": "Constructed development controls; no model trials or independent assessment",
        "source_sha256": {p.name: sha(p) for p in SOURCE.iterdir() if p.is_file()},
        "cases": cases,
        "files": {str(p.relative_to(fixtures)): sha(p) for p in sorted(fixtures.rglob("*")) if p.is_file()},
    }
    (fixtures / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
