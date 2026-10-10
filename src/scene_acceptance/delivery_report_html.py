"""Offline summary and drill-down pages for a combined delivery report."""

from html import escape
import json

NAV = [
    ("index", "Summary"),
    ("checks", "Scripted checks"),
    ("brief", "Brief & coverage"),
    ("visual", "Judge / visuals"),
    ("triage", "AI risk triage"),
    ("human", "Human decisions"),
    ("evidence", "Evidence"),
]
STYLE = """
body{margin:0;background:#f6f7f8;color:#1d2b35;font:16px/1.55 system-ui,sans-serif}
main{max-width:1200px;margin:0 auto;padding:28px 24px 48px}h1{font-size:32px;line-height:1.2;margin-bottom:12px}
h2{font-size:22px;margin-top:30px}p{max-width:95ch}nav{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 24px}
nav a{padding:7px 11px;background:white;border:1px solid #ccd4da;border-radius:5px;text-decoration:none}
nav a[aria-current]{background:#183c50;color:white}a{color:#155f8b}table{border-collapse:collapse;width:100%;background:white;font-size:14px}
th,td{text-align:left;vertical-align:top;padding:10px 12px;border-bottom:1px solid #d9dfe3;overflow-wrap:anywhere}
th{background:#eaf0f3}tr:target{background:#fff3c6}.scroll{overflow-x:auto}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.card{background:white;border:1px solid #d6dde2;border-radius:7px;padding:16px}.card strong{display:block;font-size:29px}
.status{border-left:5px solid #a7791c;background:#fff6e0;padding:14px 18px}.muted,small{color:#56666f}small{display:block}
details{margin:12px 0}summary{cursor:pointer}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}
input,select{font:inherit;padding:8px;margin:0 10px 14px 0;max-width:90%}.error,.fail{color:#9e3027}.pass{color:#216548}
footer{border-top:1px solid #d6dde2;margin-top:30px;padding-top:14px;font-size:13px}
@media(max-width:700px){main{padding:20px 12px}.cards{grid-template-columns:repeat(2,1fr)}h1{font-size:26px}}
"""


def e(value):
    return escape(str(value if value is not None else "Not recorded"), quote=True)


def label(value):
    return (
        e(value.replace("_", " ").capitalize()) if isinstance(value, str) else e(value)
    )


def detail(value, title="Recorded details"):
    return f"<details><summary>{e(title)}</summary><pre>{e(json.dumps(value, indent=2))}</pre></details>"


def table(headers, rows, *, ids=None, filterable=False):
    controls = (
        (
            '<label>Search <input id="search" type="search" placeholder="Name, area or finding"></label>'
            '<label>Show <select id="status"><option value="">All results</option>'
            "<option>PASS</option><option>FAIL</option><option>UNKNOWN</option><option>ERROR</option>"
            "<option>PASS_WITH_WARNINGS</option><option>NO_APPLICABLE_SUBJECTS</option></select></label>"
        )
        if filterable
        else ""
    )
    body = "".join(
        "<tr"
        + (f' id="{e(ids[i])}"' if ids else "")
        + ">"
        + "".join("<td>" + str(c) + "</td>" for c in row)
        + "</tr>"
        for i, row in enumerate(rows)
    )
    return (
        controls
        + '<div class="scroll"><table'
        + (' id="rows"' if filterable else "")
        + "><thead><tr>"
        + "".join('<th scope="col">' + e(h) + "</th>" for h in headers)
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )


def render_pages(folder, d):
    script, judge = d["script"], d["judge"]
    assessment, triage, prepared = (
        d.get("assessment") or {},
        d.get("triage") or {},
        d.get("prepared") or {},
    )
    context = d["context"]
    checks = script.get("checks", [])
    specs = script.get("specifications", [])
    brief_state = {True: "Yes", False: "No", None: "Not recorded"}[
        context["brief_supplied"]
    ]
    mapping = context.get("mapping_review")
    mapping_status = (
        (mapping or {}).get("status", "Not recorded")
        if isinstance(mapping, dict)
        else mapping or "Not recorded"
    )
    obligations = assessment.get("items", [])
    unresolved = [s for s in obligations if s["status"] in ("UNKNOWN", "ERROR")]
    counts = d["check_counts"]
    risks = triage.get("human_review_risk_counts", {})
    inv = d["scene"].get("inventory") or {}
    triage_status = triage.get("execution_status", "not_requested")
    visual_status = label(judge["status"])
    if judge.get("model_invoked") is False:
        visual_status += " · no model call"
    models = (
        "Text triage only"
        if triage and judge.get("model_invoked") is not True
        else (
            "Judge and text triage"
            if triage
            else "Judge review" if judge.get("model_invoked") else "None recorded"
        )
    )
    scope_rows = [
        [
            "Brief provided",
            brief_state,
            e(context.get("brief_title") or "No title recorded")
            + ' · <a href="brief.html">Requirements and sources</a>',
        ],
        [
            "Brief provenance",
            e(context.get("brief_provenance")),
            "Recorded authorship; not independently authenticated.",
        ],
        [
            "Brief source files",
            e(
                ", ".join(
                    str(
                        sum(
                            1 for s in context["brief_sources"] if s.get("role") == role
                        )
                    )
                    + " "
                    + role
                    for role in sorted(
                        {s.get("role", "unrecorded") for s in context["brief_sources"]}
                    )
                )
                or "None recorded"
            ),
            "Text and reference images describe the requested result.",
        ],
        [
            "Brief interpretation review",
            e(mapping_status),
            e((mapping or {}).get("reason", "") if isinstance(mapping, dict) else ""),
        ],
        [
            "Scene data",
            (
                "Saved USD inspected"
                if context["scene_data"]
                else "No successful scene inventory"
            ),
            e(d["scene"].get("candidate")),
        ],
        [
            "Scripted checks",
            label(context.get("script_status")),
            e(", ".join(context["packs"]) or "No content packs recorded"),
        ],
        [
            "Rendered views supplied",
            e(len(context["supplied_views"])) + " recorded views",
            "Supplied does not mean eligible for every review question.",
        ],
        [
            "Visual evidence and judge",
            visual_status,
            "Caller-supplied views are separate from reference images in a brief.",
        ],
        [
            "Text context for triage",
            (
                e(len(context["triage_evidence"])) + " selected text sources"
                if triage
                else "Not requested"
            ),
            '<a href="evidence.html">See exactly what was considered</a>',
        ],
        [
            "Producer decisions recorded",
            e(len(context["producer_decisions"])),
            "Only declared decisions in this assessment are counted.",
        ],
        [
            "Undeclared-assumption audit",
            "No audit record attached",
            "This report does not establish whether another audit ran.",
        ],
        [
            "AI use",
            models,
            "Model opinions do not replace measurements or human decisions.",
        ],
    ]
    matrix = []
    for row in script.get("matrix", []):
        if row["total"]:
            matrix.append(
                [
                    e(row["label"]),
                    e(row["total"]),
                    e(row.get("pass", 0)),
                    e(row.get("warning", 0)),
                    e(row.get("fail", 0)),
                    e(row.get("unknown", 0)),
                    e(row.get("error", 0)),
                    e(row.get("not_applicable", 0)),
                ]
            )
    attention = []
    for r in d["core_admission"]:
        if r["status"] != "PASS":
            attention.append("Input or execution check: " + r["reason"])
    attention += [
        "Scripted failure: " + r["label"] + " — " + r["reason"]
        for r in checks
        if r["status"] == "FAIL"
    ]
    attention += [
        "Scripted "
        + r["status"].lower().replace("_", " ")
        + ": "
        + r["label"]
        + " — "
        + r["reason"]
        for r in checks
        if r["status"]
        not in ("PASS", "FAIL", "NO_APPLICABLE_SUBJECTS", "NOT_APPLICABLE")
    ]
    attention += [
        "Judge "
        + r.get("assessment", "unknown")
        + ": "
        + r.get("requirement_id", "")
        + " — "
        + r.get("explanation", "")
        for r in judge.get("findings", [])
        if r.get("assessment") in ("concern", "unknown")
    ]
    attention += [
        "Evaluation error: " + str(error) for error in d.get("evaluation_errors", [])
    ]
    if mapping_status in ("pending", "rejected", "needs_review"):
        attention.append(
            "Review the brief interpretation and its chosen targets or tolerances."
        )
    if unresolved:
        attention.append(
            f"{len(unresolved)} declared requirements remain unknown or in error; inspect their evidence gaps."
        )
    if triage:
        attention.append(
            f"AI triage routes {triage.get('counts', {}).get('human_review_needed', 0)} items to human review and "
            f"{triage.get('counts', {}).get('insufficient_context', 0)} to more context."
        )
    attention += [
        r.get("reason", r.get("id", ""))
        for r in prepared.get("findings", [])
        if r.get("next_action") not in (None, "none")
    ]
    if judge.get("error"):
        attention.append("Visual review error: " + judge["error"])
    if triage.get("errors"):
        attention += triage["errors"]
    if not attention:
        attention.append(
            "No outstanding finding was recorded in the included stages. Coverage is limited to those stages."
        )
    scene_line = ", ".join(
        f"{inv[k]:,} {name}"
        for k, name in [
            ("prims", "prims"),
            ("meshes", "meshes"),
            ("materials", "materials"),
        ]
        if k in inv
    )
    summary = (
        f'<h1>{e(d["scene"].get("name") or "Delivery report")}</h1>'
        + f'<div class="status"><strong>{label(d["decision"])}</strong>'
        + (f' · Next action: {label(d["next_action"])}' if d.get("next_action") else "")
        + "</div>"
        + f'<p>{e(d["scene"].get("intended_use") or "Intended use not recorded")}</p><p>{e(scene_line)}</p>'
    )
    summary += (
        '<div class="cards">'
        + "".join(
            f'<div class="card"><strong>{n}</strong>{e(text)}</div>'
            for n, text in [
                (counts.get("PASS", 0), "Passed check rows"),
                (d["failure_count"], "Failed check rows"),
                (len(unresolved), "Unresolved declared requirements"),
                (
                    (
                        triage.get("counts", {}).get("human_review_needed", 0)
                        if triage
                        else "—"
                    ),
                    "AI-routed human-review items",
                ),
            ]
        )
        + "</div>"
    )
    summary += '<p class="muted">These categories overlap and use different units. Review items are not a count of defects or assets.</p>'
    summary += (
        "<h2>What needs attention</h2><ul>"
        + "".join("<li>" + e(s) + "</li>" for s in attention[:6])
        + "</ul>"
    )
    if len(attention) > 6:
        summary += "<p>Additional findings are retained on the detail pages.</p>"
    summary += "<h2>What was considered</h2>" + table(
        ["Input or stage", "Included status", "Context"], scope_rows
    )
    summary += "<h2>Check results</h2>" + (
        table(
            [
                "Basis",
                "Checks",
                "Pass",
                "Warning",
                "Fail",
                "Unknown",
                "Error",
                "No subjects",
            ],
            matrix,
        )
        if matrix
        else "<p>No scripted check results are attached.</p>"
    )
    summary += '<p><a href="checks.html">Inspect every check, its subjects and measurements</a>. Subject counts are kept per check and never summed into a unique-asset total.</p>'
    causes = {}
    for check in checks:
        observations = check.get("observed_values") or {}
        for finding in observations.get("findings", []):
            cause = finding.get("cause")
            if cause:
                causes.setdefault(cause, set()).add(check["id"])
    if causes:
        actions = {
            "scene_mismatch": "Repair the measured mismatch",
            "unsupported_geometry": "Choose a supported measurement or provide suitable geometry evidence",
            "numeric_uncertainty": "Review precision and the declared tolerance",
            "capacity_limit": "Adjust the caller resource budget",
            "missing_evidence": "Supply missing evidence",
        }
        summary += "<h2>Route the findings</h2>" + table(
            ["Cause", "Affected checks in displayed findings", "Next step"],
            [
                [label(c), e(len(ids)), e(actions.get(c, "Inspect the evidence"))]
                for c, ids in sorted(causes.items())
            ],
        )
        summary += "<p>Cause counts use displayed per-subject findings; the complete evidence remains in each check record. A check can have both a failure and unresolved subjects.</p>"
    summary += "<h2>AI risk triage</h2>"
    if triage:
        summary += table(
            [
                "Execution",
                "Selected items",
                "Low",
                "Medium",
                "High",
                "Unrated",
                "More context",
                "Routine",
            ],
            [
                [
                    label(triage_status),
                    e(triage["selected_items"]),
                    *[e(risks.get(k, 0)) for k in ("low", "medium", "high", "unrated")],
                    e(triage["counts"].get("insufficient_context", 0)),
                    e(triage["counts"].get("routine_handling", 0)),
                ]
            ],
        )
        summary += '<p>Low, medium and high prioritize human review; they are not verified engineering risk. <a href="triage.html">Reasons, policy overrides and evidence</a>.</p>'
    else:
        summary += "<p>Not requested in this report. Scripted findings remain available without AI triage.</p>"
    pages = {"index": summary}

    check_rows = []
    for r in checks:
        subjects = r.get("subject_counts") or {}
        count_text = "; ".join(
            k.replace("_count", "") + ": " + str(v)
            for k, v in subjects.items()
            if v is not None
        )
        check_rows.append(
            [
                e(r["label"]) + "<small>" + e(r["id"]) + "</small>",
                e(r.get("area")),
                label(r.get("basis")),
                e(r["status"]),
                "Required" if r.get("required") else "Advisory",
                e(count_text or "Provider did not report a denominator")
                + "<small>"
                + e(r.get("subject_unit"))
                + "</small>",
                e(r["reason"])
                + detail(
                    {
                        "targets": r.get("parameters"),
                        "observed": r.get("observed_values"),
                        "source": r.get("source"),
                        "evidence_pointer": r.get("evidence_pointer"),
                    },
                    "Targets, measurements and source",
                ),
            ]
        )
    pages["checks"] = (
        "<h1>Scripted checks</h1><p>Confirmed failures, warnings and missing evidence stay separate. No-applicable-subjects is not a passed test.</p>"
        + table(
            [
                "Check",
                "Area",
                "Basis",
                "Result",
                "Policy",
                "Subjects",
                "Finding and evidence",
            ],
            check_rows,
            ids=["check-" + r["id"] for r in checks],
            filterable=True,
        )
        + "<h2>Input and execution checks</h2>"
        + table(
            ["Check", "Result", "Reason"],
            [[e(r["id"]), e(r["status"]), e(r["reason"])] for r in d["core_admission"]],
        )
    )
    triage_by_id = {r["item_id"]: r for r in triage.get("items", [])}
    pages["brief"] = (
        "<h1>Brief and requirement coverage</h1><p>Brief provided: <strong>"
        + brief_state
        + "</strong>. Mapping review: "
        + e(mapping_status)
        + ".</p><p>Passing mapped checks does not prove that the whole brief was interpreted correctly. Coverage below is recorded scope, not inferred completeness.</p>"
    )
    pages["brief"] += "<p>" + e(context.get("brief_provenance")) + "</p>"
    pages["brief"] += "<h2>Source files supplied with the brief</h2>" + table(
        ["File", "Role", "Description", "Source location"],
        [
            [
                e(s.get("path")),
                label(s.get("role")),
                e(s.get("caption")),
                detail(s.get("source_location"), "PDF page or region"),
            ]
            for s in context["brief_sources"]
        ],
    )
    pages["brief"] += "<h2>Mapped requirements</h2>" + table(
        ["Requirement", "Source", "Mapped checks", "Result / coverage", "AI routing"],
        [
            [
                e(r["statement"]) + "<small>" + e(r["id"]) + "</small>",
                e((r.get("source") or {}).get("provided_by"))
                + "<small>"
                + e((r.get("source") or {}).get("reference"))
                + "</small>",
                e(", ".join(r.get("check_ids", [])) or "No scripted check"),
                e(r["status"])
                + "<p>"
                + e(r.get("coverage"))
                + "</p>"
                + detail(r.get("coverage_declaration"), "Coverage limits"),
                (
                    label(triage_by_id[r["id"]]["policy_outcome"])
                    if r["id"] in triage_by_id
                    else "Not triaged"
                ),
            ]
            for r in specs
        ],
        ids=["requirement-" + r["id"] for r in specs],
    )
    if not specs:
        pages[
            "brief"
        ] += "<p>No mapped requirement list is attached. General checks cannot establish task intent.</p>"
    pages["brief"] += "<h2>Open scope gaps</h2>" + detail(
        assessment.get("gaps", []), "Recorded gaps"
    )

    pages["visual"] = (
        "<h1>Judge and visual review</h1><p>Status: <strong>"
        + visual_status
        + "</strong>.</p>"
    )
    if judge["status"] == "not_requested":
        pages[
            "visual"
        ] += "<p>No visual judge was requested. AI text triage is not visual inspection.</p>"
    elif judge["status"] == "not_attached":
        pages[
            "visual"
        ] += "<p>No matching visual-review record is attached. This does not establish whether a separate review occurred.</p>"
    pages["visual"] += table(
        ["Criterion", "Effective opinion", "Observation", "Evidence"],
        [
            [
                e(r.get("requirement_id")),
                e(r.get("assessment")),
                e(r.get("explanation")),
                e(", ".join(r.get("evidence_ids", [])))
                + detail(r, "Opinion and evidence coverage"),
            ]
            for r in judge.get("findings", [])
        ],
    )
    pages["visual"] += "<h2>Supplied views</h2>" + table(
        ["View", "Renderer", "Time (seconds)", "Recorded evidence"],
        [
            [e(s.get("id")), e(s.get("renderer")), e(s.get("time_seconds")), detail(s)]
            for s in context["supplied_views"]
        ],
    )
    pages["visual"] += (
        "<h2>Evidence eligibility and excluded areas</h2>"
        + detail(judge.get("evidence_coverage", {}), "Eligible evidence by criterion")
        + detail(judge.get("unassessed_areas", []), "Unassessed areas")
        + detail(
            prepared.get("capture_requests", []), "Requested and supplied captures"
        )
    )

    pages["triage"] = (
        "<h1>AI risk triage</h1><p>This reviews selected declared items. It cannot turn missing evidence or a scripted failure into a pass. Low still requires review.</p>"
    )
    if not triage:
        pages["triage"] += "<p>Not requested in this report.</p>"
    else:
        pages["triage"] += (
            "<p>Execution: "
            + label(triage_status)
            + ". Model: "
            + e(triage.get("model_requested"))
            + ".</p>"
        )
        pages["triage"] += table(
            [
                "Item / original result",
                "Model recommendation",
                "Applied routing / level",
                "Reason and evidence",
                "Human decision",
            ],
            [
                [
                    e(r["statement"])
                    + "<small>"
                    + e(r["original_status"])
                    + "</small>",
                    label((r.get("model_recommendation") or {}).get("recommendation")),
                    label(r["policy_outcome"])
                    + "<p>"
                    + label(
                        r.get("review_risk")
                        or (
                            "unrated"
                            if r["policy_outcome"] == "human_review_needed"
                            else "not_applicable"
                        )
                    )
                    + "</p>",
                    e((r.get("model_recommendation") or {}).get("reason"))
                    + detail(
                        {
                            "possible_consequence": (
                                r.get("model_recommendation") or {}
                            ).get("possible_consequence"),
                            "missing_context": (
                                r.get("model_recommendation") or {}
                            ).get("missing_context"),
                            "evidence_ids": (r.get("model_recommendation") or {}).get(
                                "evidence_ids"
                            ),
                            "risk_reason": r.get("review_risk_reason"),
                            "owner_policy": r.get("policy_rule"),
                            "applied_policy_reasons": r["policy_reasons"],
                        },
                        "Consequence, missing context and policy",
                    ),
                    e(
                        (r.get("human_review") or {}).get(
                            "status", "No triage decision recorded"
                        )
                    ),
                ]
                for r in triage["items"]
            ],
            ids=["triage-" + r["item_id"] for r in triage["items"]],
        )
        pages["triage"] += "<h2>Risk definitions</h2>" + detail(
            triage.get("review_risk_rubric"), "Applied rubric"
        )
        pages["triage"] += detail(
            triage.get("unassessed_item_ids", []), "Items not triaged"
        )

    human = [
        ["Brief interpretation", e(mapping_status), detail(mapping, "Mapping review")]
    ]
    if prepared.get("approval"):
        human.append(
            [
                "Prepared scope",
                e(prepared["approval"]["status"]),
                detail(prepared["approval"]),
            ]
        )
    for r in obligations:
        if r.get("review"):
            human.append(
                [e(r["statement"]), e(r["review"].get("status")), detail(r["review"])]
            )
    for r in triage.get("items", []):
        if r.get("human_review"):
            human.append(
                [
                    e(r["statement"]),
                    e(r["human_review"].get("status")),
                    detail(r["human_review"]),
                ]
            )
    pages["human"] = (
        "<h1>Human decisions</h1><p>AI recommendations are not human decisions. Scope approval and outcome review are separate.</p>"
        + table(["Scope or item", "Recorded decision", "Record"], human)
    )
    pages[
        "human"
    ] += "<p>Absence of a review record is not approval. This report does not authenticate the reviewer or grant release.</p>"

    pages["evidence"] = "<h1>Evidence considered</h1>" + table(
        ["Input or stage", "Included status", "Context"], scope_rows
    )
    pages["evidence"] += "<h2>Recorded requirement sources</h2>" + table(
        ["Provided by", "Reference"],
        [
            [e(s.get("provided_by")), e(s.get("reference"))]
            for s in context["requirement_sources"]
        ],
    )
    pages["evidence"] += "<h2>Text sources selected for AI triage</h2>" + table(
        ["Source", "Kind", "Description"],
        [
            [e(s["id"]), e(s.get("kind")), e(s.get("description"))]
            for s in context["triage_evidence"]
        ],
    )
    pages[
        "evidence"
    ] += "<p>A source being listed does not prove its claim. Reference images in a brief describe the target; rendered views are evidence of the delivery. Formats absent from the saved record are not inferred.</p>"
    pages["evidence"] += "<h2>Producer decisions and assumptions</h2>" + detail(
        context["producer_decisions"]
    )
    pages["evidence"] += (
        "<h2>Saved records</h2><ul>"
        + "".join(
            f'<li><a href="{e(l["href"])}">{e(l["label"])}</a></li>'
            for l in d["evidence_links"]
        )
        + "</ul>"
    )
    pages["evidence"] += detail(d["scene"], "Scene structure and identity") + detail(
        d["source_outcomes"], "Original decisions"
    )
    pages[
        "evidence"
    ] += '<p><a href="combined.json">Complete combined JSON</a>. Structured snapshots remain with this report; links to original runs require those folders to remain available.</p>'
    for key, title in NAV:
        nav = (
            '<nav aria-label="Report sections">'
            + "".join(
                f'<a href="{name}.html"'
                + (' aria-current="page"' if name == key else "")
                + f">{e(text)}</a>"
                for name, text in NAV
            )
            + "</nav>"
        )
        filter_script = (
            """<script>const rows=[...document.querySelectorAll('#rows tbody tr')];function filter(){const q=document.querySelector('#search').value.toLowerCase(),s=document.querySelector('#status').value;for(const r of rows){r.hidden=!(r.textContent.toLowerCase().includes(q)&&(!s||r.cells[3].textContent===s));}}document.querySelector('#search').addEventListener('input',filter);document.querySelector('#status').addEventListener('change',filter);</script>"""
            if key == "checks"
            else ""
        )
        page = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            + f"<title>{e(title)} · Delivery report</title><style>{STYLE}</style></head><body><main>"
            + nav
            + pages[key]
            + "<footer>"
            + e(d["note"])
            + "</footer></main>"
            + filter_script
            + "</body></html>"
        )
        (folder / (key + ".html")).write_text(page, encoding="utf-8")
