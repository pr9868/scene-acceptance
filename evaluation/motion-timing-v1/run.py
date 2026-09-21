"""Replay frozen timing requirements and keep each structured report."""
from pathlib import Path
import argparse
import hashlib
import json

from scene_acceptance import evaluate
from scene_acceptance.report import write_report

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    out = Path(parser.parse_args().out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    fixtures = ROOT / "fixtures"
    manifest = json.loads((fixtures / "manifest.json").read_text())

    def verify():
        for name, digest in manifest["files"].items():
            assert hashlib.sha256((fixtures / name).read_bytes()).hexdigest() == digest, name

    verify()
    results = []
    for case in manifest["cases"]:
        report = evaluate("contract.json", "scene.usda", bundle_root=fixtures / case["id"])
        write_report(report, out / case["id"])
        results.append({**case, "actual": report["verdict"], "matched": report["verdict"] == case["expected"],
                        "checks": {x["id"]: x["status"] for x in report["checks"]}})
    verify()
    summary = {"cases": len(results), "matches": sum(x["matched"] for x in results), "results": results}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if all(x["matched"] for x in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
