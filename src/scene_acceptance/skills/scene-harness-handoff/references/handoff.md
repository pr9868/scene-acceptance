# Caller contract

The core requires Python 3.12 and local USD. Textured references/views additionally need Pillow (install the checkout with `pip install '.[visual]'`). The harness does not supply a renderer or require a GPU. A configured model CLI may send the explicit inputs to its provider. Ordinary structural evaluation remains model-free.

| Stage | Caller supplies | Harness returns |
|---|---|---|
| Prepare | Saved USD bundle, optional raw brief manifest and interpreter config, capture capability declaration, optional rubric | Immutable scene snapshot, proposed requirement/check mapping, source anchors, capture plan, pending scope review, plan hash |
| Capture | Its own renderer and compute; requested views or an explanation of missing evidence | No rendering; capture plan is a data contract |
| Evaluate | Preparation path/hash, mode, optional explicit judge config, paired views and receipt | Structural and mapped-check outcomes, subject counts, evidence coverage, advisory findings and separate gaps |

## Commands

```sh
check-3d-prepare --bundle-root ./scene-bundle --candidate scene.usda --out ./prepared
check-3d-prepare --bundle-root ./scene-bundle --candidate scene.usda \
  --raw-brief brief.json --interpreter-config ./model.json \
  --capture-capabilities ./capture-capabilities.json --out ./prepared-with-brief
check-3d-run-plan --preparation ./prepared-with-brief --expected-plan-sha256 PLAN_HASH \
  --mode both --judge-config ./model.json --views ./captures/views.json \
  --receipt ./captures/receipt.json --out ./run
```

Library equivalents are `scene_acceptance.preparation.prepare_scene(...)` and `scene_acceptance.prepared_run.evaluate_prepared(...)`. `check-3d --capabilities` exposes schemas; direct `evaluate_scene` / `check-3d` still accept optional pre-mapped briefs. There is no hosted HTTP service in this package.

## Raw brief

Paths are relative to the scene bundle and must remain inside it. Text sources: UTF-8, at most 64 KiB each. Visual references: single-frame RGB/RGBA PNG/JPEG, at most 16 million pixels and 8 MiB each, with 32 MiB total reference bytes. PDF inputs use `role: pdf` and explicit one-based pages/regions; install the PDF extra. The selected embedded text and rendered regions retain original-document hashes and page/region citations. Scans without embedded text remain visual evidence; no OCR or P&ID semantic extraction is claimed. Up to 16 raw sources (64 compiled sources); at most twelve images including subsequent scene views. Original bytes and alpha/profile metadata are preserved. Source metadata records that no colour conversion, compositing or EXIF rotation was applied.

Exact numerical pixel comparison is separate: single-frame RGB PNG/JPEG, at most 262,144 pixels and 1 MiB each. A valid 1080p/RGBA visual reference may exceed that comparator's scope. Do not silently resize, flatten alpha or weaken the comparison to obtain a pass. Its `regions`, `excluded_regions`, optional same-size RGB black/white `mask_image`, maximum channel error and optional per-channel mean error must come from the reviewed brief/policy. Declare reference and mask files as evidence sources. Rectangles use stored-pixel coordinates, X right/Y down, half-open bounds; masks include white and exclude black. Reports retain selected/excluded counts and whole-image diagnostics. Excluded pixels are not accepted; stored channel comparisons do not establish colour-managed rendered appearance.

```json
{
  "schema_version": "1.0", "id": "panel-demo", "title": "Panel review",
  "intended_use": "Illustrative assembly", "provenance": "Synthetic adopter example",
  "files": [{"path": "brief.txt", "role": "text", "caption": "User requirements"}]
}
```

Example `brief.txt`: “At time code 0, /World/Panel must measure 2 by 1 by 0.1 metres, within 0.001 metres on each axis. The front label should be legible in a rendered front view.” This gives numerical bounds a script can measure and a separate visual question. Do not claim this illustrative brief was a real user requirement.

```json
{
  "schema_version": "1.0", "capabilities": ["geometry", "surface_materials"],
  "max_images": 12, "max_width": 1920, "max_height": 1080,
  "limitations": ["Caller renders still images; no continuous-motion proof"]
}
```

Without a capability declaration, capture requests remain outstanding. The plan never reduces desired scope to match available rendering.

## Captures and receipts

`capture-plan.json` lists stable request IDs, reviewer requirement IDs, targets, purposes, camera guidance, timestamps (seconds from scene start), minimum image dimensions, capabilities and limitations. Requests declare `view_role`, `sharing_group`, nullable `camera_id` and nullable `projection`. Sharing qualifying views requires an explicit common non-null group and role. Front/rear/detail views must not silently reuse image bytes. A receipt must cite the saved plan hash and scene hash, then map request IDs to view IDs or mark them unavailable with a reason.

```json
{
  "schema_version": "1.0", "plan_sha256": "COPY_FROM_PLAN", "scene_sha256": "COPY_FROM_PLAN",
  "requests": [{"request_id": "general-0", "status": "supplied", "view_ids": ["front"], "reason": "Rendered overview"}]
}
```

Replace the hash placeholders with actual 64-character hashes. The view manifest contains `schema_version`, `scene_sha256`, `up_axis`, `meters_per_unit` and a `views` list. Each view has `id`, relative `path`, image `sha256`, `camera_id`, camera description, `projection`, `time_seconds`, `method`, `producer`, `capabilities`, `limitations` `covered_prims` and `view_roles` matching the requested roles. Use `view_manifest_schema` from capabilities for the full schema. Hash the exact supplied bytes.

Missing requests or mismatched targets/times/resolution/fidelity keep the affected judge items unknown. Declaration matching does not establish actual visibility, truthful rendering or physical correctness. At least three distinct same-camera frames is an eligibility floor, not a complete motion test. Exact dimensions belong in measurement checks.

The automatic interpreter selects the bounded types exposed by `check-3d --capabilities`: geometry and layer policy, state and connection checks, process connectivity, timing, materials and source-image comparisons. External-engine jobs and arbitrary code are never generated from a model response. Unsupported intent stays visible and the owner must review the scope.

## Application lifecycle

Use `check-3d-app {doctor,prepare,approve,bind,validate-evidence,evaluate,check}`. Every operation returns `schema_version, operation, run_id, status, exit_code, reused, data, errors, events`; inspect `data` for the operation result. Errors have code, phase, message and retryable. Code 4 can retain completed script results in a partial evaluation. Evaluation codes 0/2/3 mean scoped success/rejection/review gaps. For prepare/bind, code 0 means the proposal is ready for scope review and capture, and 3 means named readiness blockers remain. Neither approves the scope.

`approve` requires expected_scope_sha256, reviewer and reason; this approves the selected requirements/evaluation policy, not outcomes. Scope includes the full general baseline and resolved pack version/implementation identities. `bind` requires the existing scope pin and a revised saved bundle/candidate; it runs no model. `evaluate --approval approval.json --previous-run previous-directory` applies that scope review and compares findings. Captures must match the new plan/scene hashes. Use snapshot-bound `--review-record` only for separately authorized caller outcome reviews.

The optional `check-3d-isolated` wrapper supervises native work on POSIX with wall, memory, CPU and output limits; it honors deadline and cancellation settings. Its worker progress is buffered until completion, unlike the direct CLI. Resource containment does not isolate filesystem/network access.

All operations expose `--progress` (JSONL stderr), cooperative `--deadline-seconds`, `--cancel-file`, and directory-output `--reuse-completed` (opt in on first call). Never reuse partial outputs or erase failed attempts. SIGTERM stops owned model process groups on POSIX; hard kills and detached descendants cannot be cleaned up by the harness.

General preset `2.0.0` selects layout/readability, material use when materials or shaders are authored, and motion when time-sampled attributes are authored. `static-visual` and `animated-visual` explicitly select their named areas. All presets disclose excluded areas as unassessed, not passes. Custom/explicit requirements remain authoritative: unsupported requested physics stays unknown. Preparation freezes the selected criteria and exclusions; rebinding does not add or drop them to fit the candidate. Inventory-based exclusion reasons refer to scope selection, not an assertion that later repairs lack that content.

Use `--max-dependency-files` (default 64, maximum 1024) consistently. Runtime/provider changes require explicit `bind --migrate-runtime --reviewer … --reason …`. If policy is unchanged, scope identity survives. Changed general rules or selected pack identities create a new scope hash and `binding.policy_changes`; previous approval cannot be reused. Review the diff and approve the new returned hash before acceptance. Without it, otherwise passing migrated runs remain `NEEDS_REVIEW`, including subsequent repairs. Older preparations without `evaluation_policy` need new preparation/review. Retain their old reports.

The optional incline simulation pack verifies installed worker, adapter and fixed-profile hashes before/after execution, verifies returned identities and validates the trajectory. It runs only the bounded two-box CPU model; it is not general scene physics or a security sandbox. Model review has no physical-validation evidence adapter.

Raw brief manifests may include `source_origin: {provided_by: human|application|agent|preset|unrecorded, reference: ...}`. Do not label agent-written sample text human-authored. The mapping author remains separately recorded. Model configuration may limit calls, request/output bytes, timeout and modalities; token/spend enforcement belongs to its provider. With no eligible visual evidence, no judge call is made.


## Renderer-library evidence

The default policy leaves unresolved MDL source libraries unknown. For caller-owned runtime evidence, pass `runtime_dependency_policy="caller-attested"` and the independently selected `runtime_environment_sha256` at preparation, or on a direct check. Pass `runtime_dependency_evidence` on evaluation. The prepared policy/environment are scope-bound and require caller approval; a repaired scene needs a receipt for its new artifact-set hash.

Inspect the packaged `runtime-dependency-receipt-v1` schema through `check-3d-app capabilities`. It requires scene/environment hashes, exact layer/attribute/authored MDL identifiers, renderer/runtime names and versions, resolved library hashes, attestation source/author and UTC observation/expiry. Obtain those values from the target application. Do not copy an untrusted receipt's environment hash as the expected target. The receipt remains a caller statement of availability, not an independent compile/render test. Missing ordinary textures and explicit local-file requirements cannot be waived this way.
