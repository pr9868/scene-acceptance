"""Local run history around the existing, immutable operation outputs."""

from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import tempfile
from urllib.parse import quote

from .model import ContractError


DEFAULT_RUN_ROOT = "scene-acceptance-runs"


def _write_new(path, text):
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text)
    except FileExistsError:
        pass


def start_run(operation, parameters, run_root, run_id):
    """Reserve a unique container; leave its output child for the evaluator."""
    root = Path(run_root or DEFAULT_RUN_ROOT).resolve()
    protected = [
        Path(parameters[key]).resolve()
        for key in ("bundle_root", "review_root", "preparation", "triage_run", "evaluation_run")
        if parameters.get(key)
    ]
    if parameters.get("assessment"):
        protected.append(Path(parameters["assessment"]).resolve().parent)
    if any(root == p or root.is_relative_to(p) for p in protected):
        raise ContractError(
            "Run history must be outside input folders; choose --run-root outside the delivery"
        )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _write_new(root / ".gitignore", "# Local reports may contain private inputs.\n*\n!.gitignore\n")
    _write_new(
        root / "README.md",
        "# Saved Scene Acceptance runs\n\n"
        "Each dated folder is a separate attempt. Open its `index.html` for the outcome "
        "and links to reports, or `run.json` for the invocation record. "
        "`output/` retains the evaluator's results and available model requests, responses "
        "and logs. Failed attempts are kept too. Timestamps use UTC.\n\n"
        "Nothing here approves a delivery. Reports can contain private project content; "
        "review them before sharing. Source files referenced by a run may still be needed "
        "for replay. Runs are never automatically deleted.\n",
    )
    started = datetime.now(timezone.utc)
    folder = Path(tempfile.mkdtemp(
        prefix=started.strftime("%Y%m%dT%H%M%S.%fZ-") + operation + "-", dir=root
    ))
    record = dict(
        schema_version="1.0", run_id=run_id, operation=operation,
        started_at=started.isoformat(), completed_at=None,
        parameters=parameters, envelope=None, status="running",
    )
    _store(folder, record)
    return folder, record


def storage_paths(folder):
    return dict(
        run_directory=str(folder), output_directory=str(folder / "output"),
        summary_report=str(folder / "index.html"), record=str(folder / "run.json"),
    )


def finish_run(folder, record, result):
    record = dict(record, completed_at=datetime.now(timezone.utc).isoformat(),
                  status=result["status"], envelope=result)
    _store(folder, record)


def _store(folder, record):
    # Each container has one owner. Atomic replacements also leave a useful
    # 'running' record if the process is killed before it can finish.
    target = folder / "run.json"
    temporary = folder / ".run.json.tmp"
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    envelope = record.get("envelope") or {}
    data = envelope.get("data") or {}
    rows = [
        ("Operation", record["operation"]), ("Started (UTC)", record["started_at"]),
        ("Execution", record["status"]), ("Exit code", envelope.get("exit_code")),
        ("Decision", data.get("decision")), ("Next action", data.get("next_action")),
        ("Scene", record["parameters"].get("candidate")),
        ("Bundle", record["parameters"].get("bundle_root")),
        ("Preparation", record["parameters"].get("preparation")),
        ("Assessment", record["parameters"].get("assessment")),
    ]
    cells = "".join(
        f"<tr><th>{escape(label)}</th><td>{escape(str(value))}</td></tr>"
        for label, value in rows if value is not None
    )
    reports = []
    output = folder / "output"
    if output.is_dir():
        for path in sorted(output.rglob("*.html")):
            if path.is_symlink() or not path.resolve().is_relative_to(output.resolve()):
                continue
            relative = path.relative_to(folder).as_posix()
            reports.append(f'<li><a href="{quote(relative)}">{escape(relative)}</a></li>')
    errors = "".join(
        f'<li>{escape(row["message"])}</li>' for row in envelope.get("errors", [])
    )
    risks = data.get("human_review_risk_counts")
    risk_table = (
        '<h2>Human-review levels</h2><p>Model-assisted routing, not human approval.</p><table>'
        + ''.join(f'<tr><th>{escape(level.title())}</th><td>{escape(str(risks.get(level, 0)))}</td></tr>'
                  for level in ('low', 'medium', 'high', 'unrated'))
        + '</table>'
    ) if risks is not None else ''
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Saved Scene Acceptance run</title><style>'
        'body{font:16px system-ui;max-width:960px;margin:2rem auto;padding:0 1rem;line-height:1.5}'
        'table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #ddd;'
        'text-align:left;vertical-align:top;padding:.6rem;overflow-wrap:anywhere}'
        'th{width:25%}a{overflow-wrap:anywhere}</style><main>'
        '<h1>Saved Scene Acceptance run</h1>'
        + ('<p><strong><a href="output/delivery-report/index.html">Open the combined delivery report</a></strong> — summary, checks, brief coverage, visual review and AI triage.</p>'
           if (output / 'delivery-report/index.html').is_file() else '')
        +
        '<p>Execution status and acceptance are separate. A completed check or model opinion '
        'does not grant human approval.</p>'
        f'<table>{cells}</table>{risk_table}<h2>Reports</h2><ul>{"".join(reports)}</ul>'
        + ('<p>No component report was produced.</p>' if not reports else '')
        + (f'<h2>Execution errors</h2><ul>{errors}</ul>' if errors else '')
        + '<p><a href="run.json">Full invocation record</a>'
        + (' · <a href="output/">Retained output files</a>' if output.is_dir() else '') + '</p>'
        '<p>Source files referenced by this record may still be needed for replay. '
        'Private inputs may appear in reports and model logs.</p></main></html>'
    )
    temporary = folder / ".index.html.tmp"
    temporary.write_text(page, encoding="utf-8")
    temporary.replace(folder / "index.html")
