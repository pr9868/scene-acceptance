# Reports that state what was actually checked

A run should answer four questions: what evidence was selected, which subjects were assessed, what was found, and what remains outside coverage. A contract result is always scoped to its selected requirements.

Start with the new [scene and specification overview](SCENE_AND_SPECIFICATION_REPORTS.md): scene identity/structure, a general-versus-specification results matrix, recorded human/application/agent/preset sources, and coverage of each declared requirement. The detailed object/sample tables remain underneath. Missing provenance is labeled unrecorded; passing checks do not imply full specification coverage.

For a combined artifact and requirement review, use [`check-3d --review-plan`](DECLARED_SCOPE_REVIEW.md). The same distribution now includes [21 supplemental four-job comparisons](SUPPLEMENTAL_CHECKS.md) and the five-layer review. Explicit targets remain separate from generic baseline diagnostics; unresolved review obligations stay visible beside passing measurements.

## One summary with separate details

Every artifact report, declared-scope assessment, unified evaluation, prepared evaluation and triage result generates `delivery-report/index.html` beside its existing detailed report. For legacy brief calls this is inside `report/`. The application envelope's optional `report` field and the `check-3d` stdout `report` field select this summary. The saved-run index links to it. If execution stops before a result exists, the saved-run index explains the error instead of presenting empty checks as a pass.

| Page | What the reader gets |
|---|---|
| Summary | Scene and inventory; brief supplied or absent; brief authorship and interpretation review; considered sources/stages; next action; check matrix and review queue |
| Scripted checks | General versus requirement-driven checks; pass, warning, fail, unknown, error and no-subject outcomes; per-check subject counts, targets and measurements |
| Brief & coverage | Supplied text/reference-image files, PDF source anchors when recorded, source provenance, each mapped requirement and its coverage limits |
| Judge / visuals | Judge execution state, supplied rendered views, evidence eligibility, opinions and excluded areas |
| AI risk triage | Selected items, model recommendations, applied owner policy, low/medium/high review priorities, missing context and unselected items |
| Human decisions | Brief interpretation review, scope approval and item decisions, separate from model opinions |
| Evidence | Declared producer decisions, selected triage text sources, structured snapshots and links to native reports |

A reference image describes what was wanted; it is not proof of what was delivered. A supplied view may still be ineligible for a particular question. The report labels missing provenance as unrecorded and an unavailable review as not attached. No-applicable-subjects is not a successful test. Check rows, requirements and AI review items overlap; their counts cannot be added into a defect or unique-asset total.

Triage automatically includes a matching saved evaluation when its exact pinned assessment resides in that evaluation's known output layout. It does not scan other project folders. For separately retained runs, assemble the same report explicitly:

```sh
check-3d-app report --evaluation-run ./saved-evaluation \
  --triage-run ./saved-triage --run-root ./scene-acceptance-runs
```

Omit `--triage-run` for an evaluation-only view. A prepared evaluation folder is also accepted, preserving its outer scope gate. Input records must match their manifests; triage must belong to the exact assessment and snapshot. This operation makes no model call, reruns no scene checks and leaves the source runs untouched. It presents historical evidence; it does not refresh stale approval. Standalone audit questions are not joined in this version, and their absence is stated.

`combined.json` and structured source snapshots sit beside the pages. Original run links require those folders to remain available. Reports can contain the caller's private brief and evidence paths; keep project history private unless deliberately sanitized for sharing.

## Run the reusable baseline

From this development checkout with Python 3.12:

```sh
python -m pip install -e '.[test,nvidia,article_checks]'
check-3d \
  --bundle-root /path/to/delivery --candidate scene.usda \
  --max-dependency-files 256 --out /path/to/new-report
```

Omitting `--brief`, `--contract`, `--review-plan` and `--profile` selects the general baseline automatically. `--profile usd-delivery-baseline` remains an equivalent explicit selection. The shipped `usd-delivery-baseline` 1.2.0 profile selects 27 checks: 17 native OpenUSD invocations, seven NVIDIA rule invocations, external-file availability, image decoding and finite authored-motion data. It discovers explicit local references inside the caller's bundle root and applies the existing path, size, composition and resource limits. It does not accept arbitrary resolver paths or infer task intent. Generated requirements and their canonical JSON digest are saved with the report. Use `--brief` for a text/image package with explicit check mappings, or `--contract` for narrower allowlists, reference comparisons and task-specific requirements.

The default file budget remains 64. Set a larger bounded budget deliberately when needed. Image discovery is limited to recognized image suffixes in the admitted USD dependency closure; orphan files and arbitrary shader semantics are outside the scan. PNG and JPEG decode with explicit byte/pixel limits; HDR, EXR and other discovered image formats remain unknown. Missing optional libraries produce an execution error instead of a pass.

Authored-motion diagnostics inspect prims with time-sampled local transform operations, evaluating composed world matrices at all authored keys plus playback boundaries and midpoints inside that interval. Keys before or after playback are valid USD and are listed separately; their existence does not cause a failure, although non-finite transforms at those keys still fail. The check requires an authored valid range and an effective rate from authored `timeCodesPerSecond` or its authored `framesPerSecond` fallback, with metadata provenance in the report. A wholly implicit default rate remains unresolved by this delivery policy. Per-prim/total sample budgets still apply. Static descendants, runtime-driven motion, collision, intended trajectories and continuous-time guarantees are not covered by this check.

## Read the result

| Output | Purpose |
|---|---|
| `delivery-report/index.html` | Default summary and navigation to separate detail pages |
| `report.html` | Original interactive component report: coverage by area, per-check counts, filters, example findings and input inventory |
| `summary.md` | Portable readable table |
| `checks.csv` | One row per selected check, including required/advisory status and count unit |
| `subjects.csv` | Passing, failing, warning, unknown and skipped subjects with pointers into `result.json` |
| `findings.csv` | Provider observations and non-passing subject outcomes; `kind` distinguishes them to avoid double-counting |
| `result.json` | Full original evidence, parameters, identities, inventory and coverage summaries |
| `contract.json` | Generated baseline contract, when using `--profile` |
| `manifest.json` | Hashes of output files |

Counts within a check have exclusive statuses. Assessed = pass + fail + warning. Unknown/error/skipped subjects remain outside that count. Candidates = the sum of all six categories. A warning can leave the contract status PASS while the report shows PASS_WITH_WARNINGS. A provider skip can leave its original contract status PASS while the report shows PARTIAL_COVERAGE. This preserves the original contract semantics without presenting unassessed subjects as successful evaluations.

NO_APPLICABLE_SUBJECTS contributes no successful subject checks. Missing denominators are shown as “—”, never zero. Native OpenUSD validators generally expose a stage-level result, so their unit is **stage-validator invocations**, not passing objects. Selected rigid-body/collider/joint rules with zero matching inventory are explicitly marked as having no applicable subjects. The seven supported NVIDIA rules expose measured prim callbacks and documented eligibility gates under pinned version 1.20.0. Other rules remain unmeasured. Callback instrumentation is serialized and always restored; direct-provider parity tests preserve the original findings.

Inventory is distinct from validation: prims, meshes, materials, physics schemas, time-sampled attributes, USD layers and external files describe the admitted scene, not what every check validated. Do not add subject counts across rules or exports: the same object or file may occur repeatedly. Counts are not a quality score or independent model-error rate.

The coverage table always includes areas that were not selected. Appearance, task intent and physical reference coverage remain open under the baseline. “Complete” retains the existing meaning: all required contract results are resolved, not every conceivable scene requirement was checked.

## Add article-specific requirements

The three article packs are now included in the main source distribution and default registry. They are available without a separate private extension installation. Optional dependencies are installed with `article_checks`.

- `textures.decode` 0.2.0: `image` checks one named `UsdUVTexture` attribute. Requires `asset_attribute`, `max_pixels`, `max_bytes`. It does not infer expected pixels.
- `motion.connection` 0.1.0: `distance` compares task-named local points. Requires `a`/`b` paths and local points, `interval_s`, `segments`, `schedule`, `max_gap_m`. The report records sampled gaps; finite samples cannot prove every instant.
- `physics.incline-worker` 0.2.0: `displacement` runs the fixed CPU incline adapter. Requires timestep, duration, deadline, displacement threshold and measured-parameter requirement. It is not a general USD physics importer. No physical calibration is inferred.

The preserved controls are in `evaluation/article-checks-v1/fixtures`. All three packs can appear in the same v2 contract as structural checks. Runtime behavior is only executed when explicitly selected. Third-party entry points still require `--allow-pack`; the bundled article packs no longer use that path.

```sh
python -m pytest tests/test_article_checks.py tests/test_reporting.py -q
```

These are constructed development controls, not an independent evaluation of a model. The initial historical protocol is retained; migration into the main package changes provider registration and source pins. No prior results were overwritten.

## Evaluate multiple saved deliveries

Create a JSON array with `id`, `label`, `bundle_root` and `candidate`; optionally supply a `contract` path relative to its bundle. IDs must be unique and use simple lowercase names. Omit `contract` to select the shipped baseline.

```sh
python -m scene_acceptance.batch --manifest deliveries.json --out /path/to/new-audit \
  --max-dependency-files 256 --timeout-seconds 600 --workers 2
```

The batch creates individual reports, an HTML index, a combined check table and execution logs. Each process has a deadline; at most two run together. There is no hard memory sandbox. A timeout or process failure remains an evaluation error, not a rejected scene or a clean result. No simulation or external provider is selected by the baseline.

## Measured findings and unresolved work

The first-delivery upgrade retains per-subject expected/observed results and explicit omission counts in the application projection. A clearance failure remains visible even when another selected object cannot be measured. Its subject table distinguishes a measured mismatch, unsupported geometry, numerical uncertainty, missing evidence and exhausted capacity. The summary groups available causes with the corresponding next step; full provider evidence remains linked.

Mechanical coverage counts declared relationships separately from evaluated knots. A single connection checked across many times is one relationship, not many accepted assets. Surface/solid choice, allowed contact and any physical contact allowance are part of the recorded requirement. Changed policy is not reported as a repaired scene.
