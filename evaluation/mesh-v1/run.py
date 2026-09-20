"""Replay the frozen mesh extension with no model calls or content repairs."""

from pathlib import Path
import argparse, collections, html, json
from scene_acceptance import evaluate
from scene_acceptance.engine import implementation_digest
from scene_acceptance.model import sha
from scene_acceptance.report import write_report, STYLE

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    f = ROOT / "fixtures"
    manifest = json.loads((f / "manifest.json").read_text())
    assert sha(ROOT / "PROTOCOL.md") == manifest["protocol_sha256"]

    def verify():
        for n, h in manifest["files"].items():
            assert sha(f / n) == h, n

    verify()
    rows = []
    for case in manifest["cases"]:
        d = f / case["id"]
        r = evaluate(
            "contract.json",
            "scene.usda",
            bundle_root=d,
            baseline_path="baseline.usda" if (d / "baseline.usda").exists() else None,
            claims_path="claims.json" if (d / "claims.json").exists() else None,
        )
        write_report(r, out / case["id"])
        rows.append(
            {
                **case,
                "actual": r["verdict"],
                "match": r["verdict"] == case["expected"],
                "checks": {c["id"]: c["status"] for c in r["checks"]},
                "elapsed_ms": r["runtime"]["elapsed_ms"],
            }
        )
    verify()
    summary = dict(
        cases=len(rows),
        matches=sum(r["match"] for r in rows),
        verdicts=dict(collections.Counter(r["actual"] for r in rows)),
        checker_sha256=implementation_digest(),
        scope="Same-assistant frozen development cases, including labeled derivatives of retained model evidence. No new model calls, independent validation or model reliability rate.",
    )
    (out / "summary.json").write_text(
        json.dumps(dict(summary=summary, cases=rows), indent=2) + "\n"
    )
    esc = lambda x: html.escape(str(x))
    table = "".join(
        f'<tr><td><a href="{r["id"]}/report.html">{esc(r["id"])}</a></td><td>{esc(r["expected"])}</td><td>{esc(r["actual"])}</td><td>{esc(r["provenance"])}</td></tr>'
        for r in rows
    )
    (out / "index.html").write_text(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Boxes and polygon meshes: evaluation</title><style>{STYLE}</style></head><body><main><h1>Boxes and polygon meshes</h1><p>{summary["matches"]}/{summary["cases"]} expected outcomes matched.</p><p>{esc(summary["scope"])}</p><p>The contract can require shape preservation: an unchanged outer box is insufficient when interior geometry changes. Mesh closure is optional and checks edge incidence only. Collision, rendering and physical fitness remain separate.</p><div class="scroll" tabindex="0" role="region" aria-label="Cases"><table><thead><tr><th>Case</th><th>Expected</th><th>Observed</th><th>Provenance</th></tr></thead><tbody>{table}</tbody></table></div><p><a href="summary.json">Structured summary</a></p></main></body></html>'
    )
    print(json.dumps(summary, indent=2))
    if summary["matches"] != summary["cases"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
