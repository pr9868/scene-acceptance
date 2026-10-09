"""Run local saved deliveries and build an index without pooling incompatible counts."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys
from .model import strict_json, sha
from .report import E, STYLE, csv_file


def write_index(out, records):
    out = Path(out)
    flat = []
    table = []
    for record in records:
        id = record["id"]
        dest = out / id / "result.json"
        try:
            result = json.loads(dest.read_text()) if dest.is_file() else None
            if result is not None and not all(
                k in result for k in ("verdict", "coverage")
            ):
                raise ValueError("Incomplete result document")
        except (ValueError, OSError) as exc:
            result = None
            record["error"] = "No complete machine-readable result: " + str(exc)
        record["result_sha256"] = sha(dest) if result else None
        record["verdict"] = (
            result["verdict"]
            if result and record.get("exit_code") in (0, 2, 3)
            else "EVALUATION_ERROR"
        )
        inv = result["coverage"].get("inventory") or {} if result else {}
        rows = result["coverage"].get("audit", {}).get("rows", []) if result else []
        for r in rows:
            flat.append(dict(scene=id, **r, **(r.get("counts") or {})))

        def counts(check):
            return next((r["counts"] for r in rows if r["id"] == check), None) or {}

        tex = counts("audit.textures")
        motion = counts("audit.authored_motion")

        def summary(c):
            if not c:
                return "Unknown"
            if not c.get("candidate_count"):
                return "No applicable subjects"
            return f"{c['pass_count']} pass / {c['assessed_count']} assessed; {c['fail_count']} fail; {c['unknown_count']} unknown; {c['skipped_count']} skipped"

        record["inventory"] = inv
        record["textures"] = tex
        record["authored_motion"] = motion
        label = E(record.get("label", id))
        link = (
            f'<a href="{id}/delivery-report/index.html">{label}</a>'
            if (out / id / "delivery-report/index.html").is_file()
            else label
            + "<small>"
            + E(record.get("error", "No complete report; inspect the process log"))
            + "</small>"
        )
        table.append(
            f'<tr><td>{link}</td><td>{E(record["verdict"])}</td><td>{inv.get("meshes","—")}</td><td>{E(summary(tex))}</td><td>{E(summary(motion))}</td><td>{len(rows)}</td></tr>'
        )
    csv_file(
        out / "checks.csv",
        [
            "scene",
            "id",
            "pack",
            "check",
            "status",
            "contract_status",
            "unit",
            "candidate_count",
            "assessed_count",
            "pass_count",
            "fail_count",
            "warning_count",
            "unknown_count",
            "error_count",
            "skipped_count",
            "reason",
            "evidence_pointer",
        ],
        flat,
    )
    (out / "results.json").write_text(json.dumps(records, indent=2) + "\n")
    text = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Harness delivery audit</title><style>{STYLE}</style></head><body><main><h1>Harness delivery audit</h1><p>{len(records)} saved deliveries. Open a scene for the checks, object counts, findings and coverage gaps.</p><p class="scope">Counts are per delivery and per check. Shared assets may occur in several exports. Authored-transform data checks do not establish intended motion. The baseline does not run task-specific connection checks, simulation or appearance comparisons.</p><div class="scroll"><table><thead><tr><th>Delivery</th><th>Contract result</th><th>Mesh inventory</th><th>Image files</th><th>Authored motion prims</th><th>Selected checks</th></tr></thead><tbody>{''.join(table)}</tbody></table></div><p><a href="checks.csv">All checks as CSV</a> · <a href="results.json">Run records</a> · <a href="manifest.json">File hashes</a></p></main></body></html>"""
    (out / "report.html").write_text(text)
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "files": {
                    p.name: sha(p)
                    for p in sorted(out.iterdir())
                    if p.is_file() and p.name != "manifest.json"
                }
            },
            indent=2,
        )
        + "\n"
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--manifest",
        required=True,
        help="JSON list of id, label, bundle_root, candidate; optional contract",
    )
    p.add_argument("--out", required=True)
    p.add_argument("--max-dependency-files", type=int, default=64)
    p.add_argument("--timeout-seconds", type=int, default=600)
    p.add_argument("--workers", type=int, choices=(1, 2), default=1)
    a = p.parse_args(argv)
    if not 1 <= a.max_dependency_files <= 1024 or not 1 <= a.timeout_seconds <= 3600:
        p.error("Invalid resource limit")
    cases = strict_json(a.manifest)
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        p.error("Manifest must list 1 to 100 deliveries")
    ids = set()
    out = Path(a.out).resolve()
    for c in cases:
        if (
            not isinstance(c, dict)
            or not {"id", "bundle_root", "candidate"} <= c.keys()
            or set(c) - {"id", "label", "bundle_root", "candidate", "contract"}
        ):
            p.error("Invalid manifest entry")
        if any(not isinstance(v, str) or not v for v in c.values()):
            p.error("Manifest values must be nonempty strings")
        if not re.fullmatch("[a-z0-9][a-z0-9_-]{0,79}", c["id"]) or c["id"] in ids:
            p.error("Invalid or duplicate id")
        ids.add(c["id"])
        root = Path(c["bundle_root"]).resolve()
        if out.is_relative_to(root) or root.is_relative_to(out):
            p.error("Output must be outside every input bundle and its ancestors")
    if out.exists():
        p.error("Output directory already exists")
    out.mkdir(parents=True)
    (out / "inputs.json").write_text(json.dumps(cases, indent=2) + "\n")

    def run(c):
        cmd = [
            sys.executable,
            "-m",
            "scene_acceptance.cli",
            "--candidate",
            c["candidate"],
            "--bundle-root",
            str(Path(c["bundle_root"]).resolve()),
            "--out",
            str(out / c["id"]),
            "--max-dependency-files",
            str(a.max_dependency_files),
        ]
        cmd += (
            ["--contract", c["contract"]]
            if c.get("contract")
            else ["--profile", "usd-delivery-baseline"]
        )
        with (out / (c["id"] + ".log")).open("w") as log:
            try:
                r = subprocess.run(
                    cmd, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout_seconds
                )
                record = {**c, "command": cmd, "exit_code": r.returncode}
            except subprocess.TimeoutExpired:
                record = {
                    **c,
                    "command": cmd,
                    "exit_code": None,
                    "error": "Caller process deadline exceeded",
                }
        print(json.dumps({"id": c["id"], "exit_code": record["exit_code"]}), flush=True)
        return record

    records = []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = [pool.submit(run, c) for c in cases]
        for f in as_completed(futures):
            records.append(f.result())
    records.sort(
        key=lambda r: next(i for i, c in enumerate(cases) if c["id"] == r["id"])
    )
    write_index(out, records)
    return 4 if any(r["exit_code"] not in (0, 2, 3) for r in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
