# Run checks, model review, or both

The CLI supports `--mode checks`, `--mode judge`, and `--mode both`. Each accepts the same saved USD scene and an optional mapped brief. Model review requires a caller-configured CLI and is never enabled implicitly. These modes ship in release 0.5.0. They run through the CLI or library; no HTTP service is implemented.

| Mode | What runs | Result |
|---|---|---|
| `checks` | Existing general baseline, plus mapped requirements when a brief is supplied | Measured artifact and declared-scope verdicts |
| `judge` | Input admission/inventory and optional-brief advisory review | Script checks unassessed; opinions cannot establish acceptance |
| `both` | Scripted evaluation and model review over the same admitted scene revision | Separate component results, coverage and follow-up decision |

Omitting `--mode` preserves the existing stdout fields, report layout and exit meanings. Explicit modes write a versioned `evaluation.json` and a combined `report.html`; component reports remain accessible. Advanced `--contract` and `--review-plan` calls keep their existing interface without `--mode`.

## Call it from a CLI or application

```sh
check-3d --list-tests
check-3d --capabilities

check-3d --bundle-root /data/delivery --candidate scene.usda \
  --mode checks --out /data/runs/checks

check-3d --bundle-root /data/delivery --candidate scene.usda \
  --mode both --brief briefs/brief.json \
  --judge-config /data/config/reviewer.json \
  --views /data/evidence/views.json --out /data/runs/both

check-3d --bundle-root /data/delivery --candidate scene.usda \
  --mode judge --judge-config /data/config/reviewer.json \
  --views /data/evidence/views.json --out /data/runs/judge
```

For raw text/image briefs and a frozen caller-capture handoff, use the separate [preparation interface](PREPARATION_AND_SKILLS.md). Its interpreter proposes the mapped brief before evaluation; the evaluator never silently reinterprets it.

Use a new output directory outside the bundle. Omit `--brief` for scene-only review. The brief remains an explicit source/requirement/check map; arbitrary prose does not automatically become executable tests. The [test inventory](TEST_INVENTORY.md) explains all 27 baseline rules, 41 configurable check types and the applicable advisory criteria. Catalog entries are available capabilities, not a statement that every check ran.

The library entry point is `scene_acceptance.evaluation.evaluate_scene(...)`, with keyword arguments corresponding to the options above. The [Python and Node application examples](APPLICATION_CLI.md) accept optional `mode`, `judge_config`, `views`, `rubric` and `judge_exposure` fields. They launch argument arrays without a shell, read `evaluation.json`, and distinguish a reported rejection or partial evaluation from a malformed invocation. Set the host process timeout longer than the configured judge deadline plus the expected script/report work; the examples expose `timeout_seconds` in both hosts.

## Configure the reviewer explicitly

Reuse the [existing Codex or JSON CLI configuration](BRIEFS_AND_MODEL_REVIEW.md#optional-cli-model-review). The executable and arguments are trusted application configuration, never derived from a brief or model response. Authentication stays with that CLI. The adapter records the requested model, available usage, timing, input hashes and raw outputs; it does not invent a resolved snapshot or cost.

By default the new reviewer receives scene/brief/view evidence **without script verdicts, check outcomes or explanations**. Numeric requirements mapped to checks therefore remain unknown to the blind reviewer. `--judge-exposure script-aware` in `both` mode includes all script evidence for assisted interpretation. This is labeled explicitly and is not independent rediscovery. The legacy `check-3d-judge --report …` remains a compatible script-aware report adapter.

## Supply views with provenance and limits

`--views` reads a JSON manifest. Image paths are relative to the manifest's folder and cannot escape it. `scene_sha256` is the canonical identity digest of the admitted USD dependency closure, including the root and external assets, not just the root file hash. Obtain it with `discover_artifact(bundle, candidate).artifact_set_sha256` or a preceding unified scene report's identity. The units and up axis must match the scene; time is elapsed seconds from its authored start. Up to twelve combined reference/view images are accepted. Scene views must be single-frame RGB/RGBA PNG/JPEG, at most 8 MiB and 16 million pixels each, with 32 MiB total view bytes. The manifest is limited to 1 MiB. Exact brief-reference pixel checks retain their separate, smaller limits.

```json
{
  "schema_version": "1.0",
  "scene_sha256": "<64-character admitted scene digest>",
  "up_axis": "Z",
  "meters_per_unit": 1,
  "views": [{
    "id": "front-start",
    "path": "front-start.png",
    "sha256": "<64-character image SHA-256>",
    "camera_id": "front",
    "camera": "Describe the actual camera and framing",
    "projection": "orthographic",
    "time_seconds": 0,
    "method": "Describe the actual renderer or diagnostic projection",
    "producer": "Your application",
    "capabilities": ["geometry"],
    "limitations": ["Schematic shading; no texture mapping or actual lighting"],
    "covered_prims": []
  }]
}
```

This is a template; replace the hashes and camera/method declarations with real evidence. Metadata is caller-declared. Hash validation does not establish that an image was rendered correctly, and `covered_prims` is not a measured asset pass count. All supplied prim paths must exist in the scene.

Declare `surface_materials` only for actual textured surface renders. Reference images alone do not establish the delivered surface appearance. Motion review requires at least three distinct timestamps from a consistent declared camera/projection/method; even then, it covers shown frames only. Wrong scene/image hashes, coordinate disagreement, out-of-range times and escaping paths are errors before a model is called.

Without suitable evidence an item is unknown. If the model nevertheless emits a favourable or concerning opinion without citing suitable evidence, the raw response is retained and the effective item becomes unknown with an explicit coverage note. Known citations establish traceability, not semantic correctness.

## Add a review rubric

`--rubric /path/rubric.json` replaces the general preset. Brief requirements are still added separately. Pack authors can ship such a file beside scripted check declarations; importing or running a pack never invokes the model. The dispatcher owns model calls.

```json
{
  "schema_version": "1.0", "id": "layout-review", "version": "1.0.0",
  "criteria": [{
    "id": "arrangement", "statement": "Are visible components coherently arranged?",
    "area": "geometry", "evidence_kind": "scene_view",
    "limitation": "Shown surfaces only; no dimension, hidden-part or functional proof"
  }]
}
```

Evidence kinds are `scene_view`, `textured_view`, `motion_frames`, `measurements`, and `physical_validation`. The last has no supported judge evidence adapter: an explicit brief or custom rubric asking for it still returns unknown. Scripted simulation packs are separate.

Without a custom rubric, general preset version `2.0.0` selects layout/readability, material use when materials or shaders are authored, and motion when time-sampled attributes are authored. It lists physical validation and other excluded preset areas in `judge.unassessed_areas`; the HTML labels them unassessed, not passing. Thus a static scene can complete its selected visual review without an impossible default physics question, while missing evidence for an explicit requirement still blocks acceptance. Selection is frozen by preparation and preserved when a repaired scene is bound. A new scene inventory never silently relaxes that frozen review scope. `--capabilities` exposes the exact view/rubric/result schemas.

## Read the combined result

`evaluation.json` includes mode, execution status, scene identity/inventory, separate script and judge results, errors, decision, exit code and coverage. `script.checks` retains the existing measured result rows and counts. `judge.findings` records the original model assessment alongside the effective evidence-bounded opinion; `judge.unassessed_areas` discloses preset exclusions. `findings.csv`, the detailed component reports and an output manifest support inspection.

| Exit | Meaning for an explicit mode |
|---|---|
| 0 | Acceptance within selected scripted/declared scope; requested review completed without concern or unknown |
| 2 | Completed required scripted/declared-scope rejection; favourable opinions cannot clear it |
| 3 | Further review or evidence needed; every successful judge-only run uses this exit |
| 4 | Execution/input error, including a failed requested model call; completed script reports remain available |

Execution errors take precedence in the process exit; a known rejection remains in the script component. A completed model opinion does not approve human-review obligations. Missing configuration never silently falls back to checks-only. A partial run is a useful preserved report, not acceptance.

No single percentage combines prims, rule invocations, requirements, images and frames. The HTML distinguishes general checks, supplied specifications, advisory opinions, suitable evidence and remaining gaps. The [original design](MODEL_REVIEW_STRATEGY.md) explains the decisions and the separate empirical judge-evaluation plan.
