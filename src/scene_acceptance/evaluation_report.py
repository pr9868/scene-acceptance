"""Combined reader report: same scene, separate measured and advisory findings."""

from collections import Counter
import json
from pathlib import Path
from urllib.parse import quote
from .model import sha, validate
from .report import E, STYLE, csv_file
from .review_context import save


def table(headers, rows):
    return (
        '<div class="scroll"><table><thead><tr>'
        + "".join("<th>" + E(h) + "</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + str(c) + "</td>" for c in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def details(title, data):
    return (
        "<details><summary>"
        + E(title)
        + "</summary><pre>"
        + E(json.dumps(data, indent=2))
        + "</pre></details>"
    )


def label(value):
    return (
        "Not assessed" if value is None else str(value).replace("_", " ").capitalize()
    )


def write_evaluation(result, context, out):
    validate(result, "evaluation-v1")
    save(out / "evaluation.json", result)
    css = (
        STYLE
        + " img{max-width:100%;height:auto}.views{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}figure{margin:0}td{overflow-wrap:anywhere}@media(max-width:700px){main{padding:0 12px}.views{grid-template-columns:1fr}h1{font-size:26px}}"
    )
    body = (
        '<h1>Scene evaluation</h1><p class="scope">'
        + E(label(result["decision"]))
        + " · Mode: "
        + E(result["mode"])
        + " · Execution: "
        + E(result["execution_status"])
        + "</p>"
    )
    body += "<p>Scripted results are measurements within selected checks. Model opinions are advisory. Neither missing evidence nor a favourable opinion resolves an unmeasured requirement.</p>"
    sc = Counter(c.get("status") for c in result["script"]["checks"])
    body += table(
        ["Assessment", "Result", "Coverage"],
        [
            [
                "Scripted checks",
                E(label(result["script"]["artifact_verdict"])),
                E(
                    ", ".join(f"{v} {label(k).lower()}" for k, v in sc.items())
                    or "Content checks not run"
                ),
            ],
            [
                "Supplied brief",
                E(label(result["script"]["declared_scope_verdict"])),
                (
                    "Supplied; mapped measurements and unresolved requirements are shown below."
                    if result["brief_supplied"]
                    else "No task brief supplied; intent is not inferred."
                ),
            ],
            [
                "Model review",
                E(label(result["judge"]["status"])),
                E(
                    ", ".join(f"{v} {k}" for k, v in result["judge"]["counts"].items())
                    or "No completed advisory items"
                ),
            ],
        ],
    )
    body += '<p><a href="evaluation.json">Structured result</a> · <a href="test-catalog.json">Test catalog</a> · <a href="findings.csv">Review findings CSV</a> · <a href="manifest.json">Evidence manifest</a></p>'
    for kind in ("script", "judge"):
        item = result[kind]
        if item.get("report"):
            body += (
                '<p><a href="'
                + quote(item["report"])
                + '">'
                + E(kind.title() + " component report")
                + "</a></p>"
            )
    if result["errors"]:
        body += (
            "<h2>Execution issues</h2><ul>"
            + "".join("<li>" + E(x) + "</li>" for x in result["errors"])
            + "</ul>"
        )
    body += "<h2>Scene and assessment inputs</h2>" + details(
        "Scene identity, inventory and structure", result["scene"]
    )
    body += (
        "<p>Brief supplied: "
        + ("Yes" if result["brief_supplied"] else "No")
        + ". Input integrity: "
        + (
            "Verified unchanged"
            if result["source_unchanged"] is True
            else "Changed" if result["source_unchanged"] is False else "Not established"
        )
        + ".</p>"
    )
    if result.get("runtime_dependencies"):
        body += (
            "<h2>Renderer-provided dependency evidence</h2><p>Any accepted MDL availability here is a caller attestation for a pinned runtime. It is not a shader compilation or visual test.</p>"
            + details(
                "Policy, target environment and retained receipt",
                result["runtime_dependencies"],
            )
        )
    if context:
        brief = context["brief"]
        if brief:
            body += (
                "<p>"
                + E(brief["title"])
                + " · Source: "
                + E(brief["provenance"])
                + "</p>"
                + details("Exact mapped brief, including review gaps", brief)
            )
        else:
            body += "<p>No task brief was supplied. Review criteria are a named preset; task intent is not inferred.</p>"
        for evidence in context["evidence"]:
            if evidence.get("role") == "text":
                body += details(evidence["caption"], evidence["text"])
            elif evidence.get("role") == "reference_image":
                rel = Path(evidence["image_path"]).relative_to(out)
                body += (
                    '<figure><img src="'
                    + quote(str(rel))
                    + '" alt="'
                    + E(evidence["caption"])
                    + '"><figcaption>Supplied reference image; not a view of the delivered scene.</figcaption></figure>'
                )
        views = [e for e in context["evidence"] if e.get("role") == "scene_view"]
        body += "<h2>Scene evidence shown to the reviewer</h2><p>View metadata is caller-declared. Hashed images establish identity, not rendering fidelity. No textures or physics should be inferred from a schematic projection.</p>"
        body += '<div class="views">'
        for view in views:
            rel = Path(view["image_path"]).relative_to(out)
            body += (
                '<figure><img src="'
                + quote(str(rel))
                + '" alt="'
                + E(view["id"])
                + '"><figcaption>'
                + E(view["id"])
                + " · "
                + E(view["time_seconds"])
                + " s · "
                + E(view["camera_id"])
                + "</figcaption>"
                + details("Capabilities and limitations", view)
                + "</figure>"
            )
        body += (
            "</div>"
            if views
            else "</div><p>No scene views were supplied. Visual items remain unknown.</p>"
        )
    body += "<h2>Measured check results</h2>"
    script = result["script"]
    body += (
        "<p>Status: "
        + E(script["status"])
        + " · Artifact: "
        + E(label(script["artifact_verdict"]))
        + " · Declared scope: "
        + E(label(script["declared_scope_verdict"]))
        + "</p>"
    )
    rows = []
    for c in script["checks"]:
        rows.append(
            [
                E(c.get("id")),
                E(c.get("label", c.get("check", ""))),
                E(c.get("status")),
                E(c.get("basis", "")),
                E(c.get("reason", "")) + details("Measured coverage and evidence", c),
            ]
        )
    body += (
        table(
            ["Check", "What was tested", "Outcome", "Basis", "Coverage / evidence"],
            rows,
        )
        if rows
        else "<p>No content-check packs ran. Scene admission and inventory do not count as passing content tests.</p>"
    )
    if script.get("specifications"):
        body += details("Scripted specification coverage", script["specifications"])
    body += (
        "<h2>Model opinions and coverage</h2><p>Status: "
        + E(result["judge"]["status"])
        + " · Script evidence: "
        + E(result["judge"]["evidence_exposure"])
        + "</p>"
    )
    unassessed = result["judge"].get("unassessed_areas", [])
    if unassessed:
        body += "<h3>Areas outside the selected review scope</h3><p>These areas were not assessed and are not passes. Explicit brief requirements and custom rubric items remain required even when evidence is missing.</p>"
        body += table(
            ["Area", "Why it was not assessed"],
            [[E(row["area"]), E(row["reason"])] for row in unassessed],
        )
    body += "<p>Unknown means insufficient or unsuitable evidence. Any unsupported model opinion is retained in the raw response but excluded from effective findings. A cited source does not prove the explanation is true.</p>"
    reqs = {r["id"]: r for r in result["judge"].get("requirements", [])}
    findings = []
    rows = []
    for item in result["judge"]["findings"]:
        r = reqs.get(item["requirement_id"], {})
        coverage = item["evidence_coverage"]
        rows.append(
            [
                E(item["requirement_id"]) + "<br>" + E(r.get("statement", "")),
                E(r.get("specification_source", {}).get("provided_by", "unrecorded")),
                E(item["assessment"]),
                E(item["explanation"]) + "<br>" + E(item.get("coverage_note", "")),
                E(", ".join(item["evidence_ids"]))
                + "<br>"
                + E(coverage["reason"])
                + details("Evidence suitability", coverage),
            ]
        )
        findings.append(
            dict(
                requirement_id=item["requirement_id"],
                source=r.get("specification_source", {}).get(
                    "provided_by", "unrecorded"
                ),
                model_assessment=item["model_assessment"],
                effective_assessment=item["assessment"],
                explanation=item["explanation"],
                evidence_ids="; ".join(item["evidence_ids"]),
                coverage_note=item.get("coverage_note", ""),
                suitable_evidence_count=len(coverage["suitable_evidence_ids"]),
                unit="review items / cited evidence IDs, not measured assets",
            )
        )
    body += (
        table(
            [
                "Review item",
                "Requirement source",
                "Effective opinion",
                "Reason",
                "Evidence and gaps",
            ],
            rows,
        )
        if rows
        else "<p>No completed advisory items. Consult execution status; absence of findings is not a favourable review.</p>"
    )
    body += (
        "<h2>Counts kept in their own units</h2>"
        + details(
            "Script result counts (rules)",
            dict(Counter(c.get("status") for c in script["checks"])),
        )
        + details("Advisory item counts", result["judge"]["counts"])
    )
    if context:
        body += details(
            "Evidence inventory, not coverage",
            dict(
                scene_views=len(
                    [e for e in context["evidence"] if e.get("role") == "scene_view"]
                ),
                review_items=len(context["requirements"]),
                scene_prims=context["scene"]["inventory"]["prims"],
            ),
        )
    body += "<footer>Saved evidence and original inputs are read-only. No model opinion grants human approval or certifies engineering or physical safety.</footer>"
    (out / "report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Scene evaluation</title><style>'
        + css
        + "</style><main>"
        + body
        + "</main></html>"
    )
    csv_file(
        out / "findings.csv",
        [
            "requirement_id",
            "source",
            "model_assessment",
            "effective_assessment",
            "explanation",
            "evidence_ids",
            "coverage_note",
            "suitable_evidence_count",
            "unit",
        ],
        findings,
    )
    from .test_catalog import test_catalog

    save(out / "test-catalog.json", test_catalog())
    save(
        out / "manifest.json",
        {
            "files": {
                str(p.relative_to(out)): sha(p)
                for p in sorted(out.rglob("*"))
                if p.is_file() and p != out / "manifest.json"
            }
        },
    )
