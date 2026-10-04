"""Replay the frozen pack cases, retaining every mismatch and per-check outcome."""

from pathlib import Path
import argparse
import collections
import html
import json
from scene_acceptance import evaluate
from scene_acceptance.contract_upgrade import copy_replay_bundle
from scene_acceptance.model import sha
from scene_acceptance.report import write_report, STYLE

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    out = Path(parser.parse_args().out)
    out.mkdir(parents=True, exist_ok=False)
    fixtures = ROOT / "fixtures"
    manifest = json.loads((fixtures / "manifest.json").read_text())

    def verify():
        for path, digest in manifest["files"].items():
            assert sha(fixtures / path) == digest, path

    verify()
    rows = []
    for case in manifest["cases"]:
        d = copy_replay_bundle(fixtures / case["id"], out / "inputs" / case["id"])
        report = evaluate(
            "contract.json",
            "scene.usda",
            bundle_root=d,
            baseline_path="baseline.usda" if (d / "baseline.usda").exists() else None,
            approved_packs=case["approved_packs"],
        )
        write_report(report, out / case["id"])
        rows.append(
            {
                **case,
                "actual": report["verdict"],
                "complete": report["complete"],
                "match": report["verdict"] == case["expected"],
                "checks": {x["id"]: x["status"] for x in report["checks"]},
            }
        )
    verify()
    summary = {
        "cases": len(rows),
        "matches": sum(r["match"] for r in rows),
        "verdicts": dict(collections.Counter(r["actual"] for r in rows)),
        "scope": "Constructed development cases and a saved prior fixture; no new model call, independent validation or simulator execution.",
    }
    (out / "summary.json").write_text(
        json.dumps({"summary": summary, "cases": rows}, indent=2) + "\n"
    )
    esc = html.escape
    table = "".join(
        f'<tr><td><a href="{r["id"]}/report.html">{esc(r["id"])}</a></td><td>{r["expected"]}</td><td>{r["actual"]}</td><td>{str(r["complete"]).lower()}</td></tr>'
        for r in rows
    )
    (out / "index.html").write_text(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Evaluation packs: replay</title><style>{STYLE}</style></head><body><main><h1>Evaluation packs: recorded results</h1><p>{summary["matches"]}/{summary["cases"]} expected decisions matched.</p><p>{esc(summary["scope"])}</p><p>A required failure rejects the candidate; required errors and unknowns remain visible. An advisory failure does not authorize a claim that its requirement was met.</p><div class="scroll"><table><thead><tr><th>Case</th><th>Expected</th><th>Observed</th><th>Required evidence complete</th></tr></thead><tbody>{table}</tbody></table></div><p><a href="summary.json">Structured summary</a></p></main></body></html>'
    )
    print(json.dumps(summary, indent=2))
    for r in rows:
        if not r["match"]:
            print("MISMATCH", r["id"], r["actual"], r["expected"])
    return 0 if summary["matches"] == summary["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
