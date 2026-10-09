"""Local command line and an escaped, self-contained review report."""

import argparse
from html import escape
import json
import re
import sys
from pathlib import Path
from . import assess
from .schemas import LAYERS
from scene_acceptance.model import sha
from scene_acceptance.report import csv_file, write_report as write_artifact_report
from scene_acceptance.reader_report import (
    build_overview,
    render_overview,
    markdown_overview,
    write_overview,
    STYLE as READER_STYLE,
)

LABELS = {
    "explicit": "Explicit requirements",
    "inferred": "Inferred necessities",
    "decisions": "Design decisions",
    "delivery": "Delivery integration",
    "use_evidence": "Evidence for intended use",
}


def render(report):
    esc = lambda value: escape(str(value))
    sections = []
    for layer in LAYERS:
        declared = report["layers"].get(layer, {})
        rows = []
        for item in report["items"]:
            if item["layer"] != layer:
                continue
            details = "".join(
                f'<li>{esc(x["status"])}: {esc(x["reason"])}</li>'
                for x in item["observations"]
            )
            records = {
                k: item[k]
                for k in ("inference_authorization", "producer_decision", "review")
                if item[k] is not None
            }
            extra = (
                f"<details><summary>Supporting records</summary><pre>{esc(json.dumps(records, indent=2))}</pre></details>"
                if records
                else ""
            )
            rows.append(
                f'<tr><td><strong>{esc(item["statement"])}</strong><p>{esc(item["basis"])}</p></td>'
                f'<td>{"Required" if item["required"] else "Advisory"}<br><strong>{esc(item["status"])}</strong>'
                f"<ul>{details}</ul>{extra}</td></tr>"
            )
        sections.append(
            f'<section><h2>{esc(LABELS[layer])}</h2><p>{esc(declared.get("coverage", "NOT_ASSESSED"))}: '
            f'{esc(declared.get("reason", "No completed assessment"))}</p>'
            + (
                '<table><thead><tr><th scope="col">Obligation and basis</th><th scope="col">Assessment</th></tr></thead><tbody>'
                + "".join(rows)
                + "</tbody></table>"
                if rows
                else ""
            )
            + "</section>"
        )
    gaps = "".join(f"<li>{esc(x)}</li>" for x in report["gaps"] + report["errors"])
    limits = "".join(f"<li>{esc(x)}</li>" for x in report["limitations"])
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Requirements and decisions review</title><style>
body{{font:17px/1.55 system-ui,sans-serif;max-width:1060px;margin:36px auto;padding:0 20px;color:#17202b;background:#fafaf8}}
h1{{font-size:34px;line-height:1.2}}h2{{font-size:23px;margin-top:30px}}p{{margin:10px 0}}.outcome{{padding:18px;background:#eaf0f5;border-left:4px solid #35638a}}
table{{width:100%;border-collapse:collapse;table-layout:fixed}}th,td{{text-align:left;vertical-align:top;padding:14px;border:1px solid #cad1d8;overflow-wrap:anywhere}}th:first-child{{width:39%}}.scroll{{overflow:auto}}table.obligation-counts{{table-layout:auto}}table.obligation-counts th:first-child{{width:auto;min-width:0}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 monospace}}ul{{padding-left:20px}}small,code{{overflow-wrap:anywhere}}a{{color:#175488}}
@media(max-width:600px){{body{{font-size:15px;padding:0 14px;margin:20px auto}}h1{{font-size:28px}}th,td{{padding:8px}}}}
</style><main><p>Scene Acceptance · private development review</p><h1>Requirements and decisions</h1>
<p>{esc(report["intended_use"])}</p><div class="outcome"><p>Artifact checks: <strong>{esc(report["core_verdict"])}</strong></p>
<p>Declared scope: <strong>{esc(report["assessment_verdict"])}</strong></p><p>{esc(report["scope"])}</p></div>
<p><a href="assessment.json">Full assessment JSON</a> · <a href="core-result.json">Original core result</a></p>
<ul>{gaps}</ul><!--READER_OVERVIEW--><details><summary>Detailed requirement and review records</summary>{''.join(sections)}</details><details><summary>What this result does not establish</summary><ul>{limits}</ul></details>
<p><small>Snapshot: {esc(report["snapshot_sha256"])}</small></p></main></html>"""


def write_report(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    for filename, data in (
        ("assessment.json", report),
        ("core-result.json", report["core_report"]),
    ):
        (directory / filename).write_text(
            json.dumps(data, indent=2, allow_nan=False) + "\n"
        )
    document = render(report)
    reader = build_overview(report["core_report"], report)
    write_overview(reader, directory, csv_file, core_file="core-result.json")
    document = document.replace("</style>", READER_STYLE + "</style>", 1)
    summary = report.get("coverage_summary", {})
    overview = '<h2>Declared obligations</h2><div class="scroll"><table class="obligation-counts"><thead><tr><th>Scope</th><th>Pass</th><th>Fail</th><th>Unknown</th><th>Error</th></tr></thead><tbody>'
    for label in ("required", "advisory"):
        counts = summary.get(label, {})
        overview += (
            "<tr><th>"
            + label.title()
            + "</th>"
            + "".join(
                "<td>" + str(counts.get(s, 0)) + "</td>"
                for s in ("PASS", "FAIL", "UNKNOWN", "ERROR")
            )
            + "</tr>"
        )
    overview += "</tbody></table></div><p>" + escape(summary.get("note", "")) + "</p>"
    overview += '<p><a href="obligations.csv">Requirement table</a> · <a href="summary.md">Readable summary</a> · <a href="manifest.json">File hashes</a></p>'
    document = document.replace(
        "<!--READER_OVERVIEW-->",
        render_overview(reader)
        + "<details><summary>Required and advisory obligation totals</summary>"
        + overview
        + "</details>",
    )
    csv_file(
        directory / "obligations.csv",
        [
            "id",
            "layer",
            "statement",
            "required",
            "status",
            "check_ids",
            "review_required",
            "evidence_pointer",
        ],
        [
            dict(x, check_ids=", ".join(x["check_ids"]), evidence_pointer=f"/items/{i}")
            for i, x in enumerate(report["items"])
        ],
    )
    md = [
        f"# Declared scope: {report['assessment_verdict']}",
        "",
        f"Artifact verdict: {report['core_verdict']}",
        "",
        markdown_overview(reader),
        "",
        "| Obligation | Layer | Required | Result | Evidence checks |",
        "|---|---|---|---|---|",
    ]

    def safe(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    md += [
        "| "
        + " | ".join(
            safe(v)
            for v in (
                x["statement"],
                x["layer"],
                x["required"],
                x["status"],
                ", ".join(x["check_ids"]),
            )
        )
        + " |"
        for x in report["items"]
    ]
    md += [
        "",
        "Gaps: " + "; ".join(report["gaps"] + report["errors"]),
        "",
        *report["limitations"],
        "",
    ]
    if report["core_report"] is not None:
        write_artifact_report(
            report["core_report"], directory / "artifact", include_overview=False
        )
        artifact = (directory / "artifact/report.html").read_text()
        style = artifact.split("<style>", 1)[1].split("</style>", 1)[0]
        body = artifact.split("<main>", 1)[1].split("</main>", 1)[0]
        body = re.sub(r'href="([^"#:]+)"', r'href="artifact/\1"', body)
        script = artifact.split("<script>", 1)[1].split("</script>", 1)[0]
        document = document.replace(
            "</style>",
            style
            + "#artifact-measurements table{table-layout:auto}#artifact-measurements th:first-child{width:auto}</style>",
            1,
        )
        document = document.replace(
            "</main>",
            '<hr><section id="artifact-measurements">'
            + body
            + "</section></main><script>"
            + script
            + "</script>",
        )
        artifact_md = (directory / "artifact/summary.md").read_text()
        artifact_md = re.sub(r"\]\(([^)#:]+)\)", r"](artifact/\1)", artifact_md)
        md += [artifact_md]
    (directory / "summary.md").write_text("\n".join(md) + "\n")
    (directory / "report.html").write_text(document)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "files": {
                    str(p.relative_to(directory)): sha(p)
                    for p in sorted(directory.rglob("*"))
                    if p.is_file()
                }
            },
            indent=2,
        )
        + "\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Review declared scope alongside current artifact checks"
    )
    parser.add_argument("plan")
    parser.add_argument("--review-root", required=True)
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument(
        "--decisions", help="Relative producer decision JSON, inside bundle"
    )
    parser.add_argument(
        "--reviews", help="Relative caller-selected reviewer JSON, inside review root"
    )
    parser.add_argument("--approve-pack", action="append", default=[])
    parser.add_argument("--max-dependency-files", type=int, default=64)
    parser.add_argument(
        "--out",
        required=True,
        help="New directory; existing evidence is never overwritten",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.max_dependency_files <= 1024:
        parser.error("--max-dependency-files must be from 1 to 1024")
    out = Path(args.out).resolve()
    roots = [Path(args.bundle_root).resolve(), Path(args.review_root).resolve()]
    if out.exists() or any(
        out.is_relative_to(r) or r.is_relative_to(out) for r in roots
    ):
        parser.error(
            "--out must be a new directory outside both input roots and their ancestors"
        )
    report = assess(
        args.plan,
        review_root=args.review_root,
        bundle_root=args.bundle_root,
        expected_plan_sha256=args.plan_sha256,
        decision_record=args.decisions,
        review_record=args.reviews,
        approved_packs=args.approve_pack,
        max_dependency_files=args.max_dependency_files,
    )
    try:
        write_report(report, args.out)
    except (OSError, ValueError) as exc:
        print("Cannot save a complete report: " + str(exc), file=sys.stderr)
        return 3
    print(
        json.dumps(
            {
                "core_verdict": report["core_verdict"],
                "assessment_verdict": report["assessment_verdict"],
                "snapshot_sha256": report["snapshot_sha256"],
            }
        )
    )
    return {
        "ACCEPT_FOR_DECLARED_SCOPE": 0,
        "REJECT": 1,
        "NEEDS_REVIEW": 2,
        "EVALUATION_ERROR": 3,
    }[report["assessment_verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
