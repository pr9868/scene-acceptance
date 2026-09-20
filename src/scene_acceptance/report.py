"""Self-contained, escaped HTML and portable machine-readable evidence."""

from pathlib import Path
import html, json
from .model import sha

STYLE = """body{font:16px/1.55 system-ui,sans-serif;color:#20303c;background:#fafbfc;margin:0}main{max-width:1050px;margin:40px auto;padding:0 20px}h1{line-height:1.2}p{max-width:80ch}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #d0d8df;text-align:left;padding:10px;vertical-align:top}th{background:#edf2f5}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.scroll{overflow:auto}details{margin:10px 0}.PASS,.ACCEPT_FOR_USE{color:#206343}.FAIL,.REJECT{color:#ad3123}.UNKNOWN,.INSUFFICIENT_EVIDENCE{color:#805916}.ERROR,.EVALUATION_ERROR{color:#9b254c}.scope{padding:16px;border-left:4px solid #3273a4;background:#edf4fa}a{color:#145e91}footer{margin-top:30px;color:#526473}"""


def write_report(report, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    (out / "result.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    e = lambda x: html.escape(str(x), quote=True)
    rows = []
    for r in report["checks"]:
        evidence = e(json.dumps(r["evidence"], indent=2, allow_nan=False))
        rows.append(
            f'<tr><td>{e(r["id"])}<br>{"Required" if r["required"] else "Advisory"}</td><td class="{e(r["status"])}">{e(r["status"])}</td><td>{e(r["reason"])}<details><summary>Evidence</summary><pre>{evidence}</pre></details></td></tr>'
        )
    pack_summary = ""
    if report["coverage"].get("by_pack"):
        counts = report["coverage"]["by_pack"]
        pack_rows = "".join(
            f"<tr><td>{e(name)}</td>"
            + "".join(
                f"<td>{v[s]}</td>"
                for s in ["PASS", "FAIL", "UNKNOWN", "ERROR", "NOT_APPLICABLE"]
            )
            + "</tr>"
            for name, v in counts.items()
        )
        pack_summary = f'<h2>Results by evaluation pack</h2><p>Counts describe selected checks, including advisory findings. They are not comparable quality scores.</p><div class="scroll"><table><thead><tr><th>Pack</th><th>Pass</th><th>Fail</th><th>Unknown</th><th>Error</th><th>N/A</th></tr></thead><tbody>{pack_rows}</tbody></table></div>'
        pack_summary += f"<details><summary>Selected profile, requirements and execution plan</summary><pre>{e(json.dumps(report['coverage'], indent=2))}</pre></details>"
    execution_note = (
        "Selected packs ran as trusted local functions. The caller owns provider approval and process isolation."
        if report["runtime"].get("execution_mode")
        else "Checks ran locally without model calls. Separate processes and access control are still needed in an application."
    )
    text = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>3D acceptance: {e(report["verdict"])}</title><style>{STYLE}</style></head><body><main>
<h1>3D content acceptance</h1><h2 class="{e(report["verdict"])}">{e(report["verdict"])}</h2>
<p>Intended use: <strong>{e(report["intended_use"])}</strong> · Contract: {e(report["contract_id"])} · Required evidence complete: {str(report["complete"]).lower()}</p>
<p class="scope">This result applies only to the named use, supported representation and recorded revisions. It does not certify a plant, physical prediction, robot policy or every claim in a report.</p>
{pack_summary}
<div class="scroll" tabindex="0" role="region" aria-label="Check results"><table><thead><tr><th>Check</th><th>Result</th><th>Reason and evidence</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<h2>Scope that remains unchecked</h2><ul>{"".join("<li>" + e(x) + "</li>" for x in report["coverage"]["unchecked"])}</ul>
<details><summary>Exact inputs and checker identity</summary><pre>{e(json.dumps(report["identity"], indent=2))}</pre></details>
<p><a href="result.json">Machine-readable result</a> · <a href="manifest.json">Report file hashes</a></p>
<footer>Checker {e(report["checker_version"])}; OpenUSD {e(report["runtime"]["usd"])}. {execution_note}</footer></main></body></html>'''
    (out / "report.html").write_text(text)
    (out / "manifest.json").write_text(
        json.dumps(
            {"files": {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}},
            indent=2,
        )
        + "\n"
    )
