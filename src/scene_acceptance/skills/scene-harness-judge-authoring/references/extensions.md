# Extension levels

| Change | Adopter edits | Implementation required? |
|---|---|---|
| Different judge questions or priorities | Versioned rubric JSON supplied to `--rubric` during preparation or direct evaluation | No. Order criteria by importance and state the concern plainly. Core reports do not implement weighted scores. |
| Task-specific visual/measurement scope | Original brief and source images; interpreter emits a proposed map and capture requests | No for supported mappings; interpretation remains pending review. |
| Stricter/different capture targets, camera guidance, times or resolution | Versioned capture overrides during preparation | No for supported still-image evidence; capabilities and receipt validation still apply. |
| New numerical test | Implement/version a check pack; explicitly select it in a contract or mapped brief | Yes. Inspect `check-3d --capabilities` for the bounded automatic mapping types. The interpreter cannot invent executable checks or engine jobs. |
| Different pixel comparison region/tolerance | Saved `brief.measurements.image_pixels` parameters, declared reference and optional mask source | No new adapter. The existing comparator supports region unions, exclusions, binary masks and maximum/optional mean channel-error limits. |
| Video, depth, segmentation, simulator traces or another evidence kind | Decoder, limits, provenance, suitability policy, schema and tests | Yes. A rubric string alone cannot enable them. |

Use `check-3d --list-tests` for supported scripted checks and `check-3d --capabilities` for public schemas. Use `check-3d-packs` to inspect actual installed packs. External packs are caller-approved code; model responses cannot approve them.

## Rubric rules

Each criterion has `id`, `statement`, `area`, `evidence_kind` and `limitation`. IDs must be unique; preparation adds `review.` to them. Provide a new profile `version` whenever its meaning changes. Empty criteria are allowed for a brief-only visual profile; judge invocation with no effective criteria fails explicitly, so use checks mode for a script-only plan.

Supported evidence kinds:

- `scene_view`: caller declares geometry visibility; bound to the requested objects/views through capture receipts.
- `textured_view`: requires caller-declared surface-material fidelity, not merely source pixels or wireframes.
- `motion_frames`: at least three distinct same-camera timestamps. Request additional event times for the actual question; frames do not establish continuous correctness.
- `measurements`: available in direct script-aware evaluation only when all referenced check results are PASS/FAIL. General rubric criteria do not declare check IDs; prefer a mapped brief for this role.
- `physical_validation`: the current judge has no admitted evidence adapter, so it stays unknown. This does not disable the separate scripted physics packs.

The interpreter and judge can use separate caller-configured CLIs/models. Interpreter outputs requirements and evidence expectations. Judge outputs consistent/concern/unknown explanations against supplied evidence. Neither output approves the mapping, substitutes for a script measurement, or decides a scene is physically safe.

Default general preset `2.0.0` selects layout/readability plus authored material and time-sampled areas. It reports unsupported physical validation and other exclusions in `judge.unassessed_areas`; excluded areas are not passes. Named static/animated profiles disclose their exclusions too. Custom criteria are retained exactly, including unsupported `physical_validation`, which remains unknown and blocks combined acceptance. Preparation freezes this selection; a repair cannot remove a required review item merely by removing its authored content. Conversely, added content does not silently extend the frozen review. Inventory-based exclusion reasons refer to the original scope selection.

## Reference images and pixel comparisons

Visual references accept single-frame RGB/RGBA PNG/JPEG up to 8 MiB and 16 million pixels each, 32 MiB total reference bytes. The combined reference/view count is twelve. Original bytes, alpha and colour metadata are preserved; the source record discloses no conversion, compositing or EXIF rotation. The exact source-pixel comparator instead accepts RGB-only images up to 1 MiB/262,144 pixels each. An interpretation image need not qualify for numerical comparison. Do not infer that a source image proves delivered appearance.

For a numerical image requirement, version the reference and comparison policy together. `image_pixels` supports required `max_channel_error`, optional `max_mean_channel_error` (every RGB channel mean must meet it), `regions`, `excluded_regions` and `mask_image`. Rectangles use stored-pixel coordinates, X right/Y down, half-open bounds. Included-region unions are reduced by exclusions and intersected with the mask's white pixels; black mask pixels are excluded. The same-size mask must be a declared RGB evidence image under the comparator limits. Empty selections and out-of-bounds rectangles are invalid. Reports preserve compared/excluded counts, whole-image diagnostics and all source identities. Neither exclusions nor colour-space differences may be silently treated as successes.

## Policy and worker identity

Prepared scope now includes the general baseline plus resolved selected pack identities. Ordinary binding keeps scope and approval. An explicit runtime migration that changes either creates a new scope hash and policy diff; obtain authorized approval of that new scope before acceptance. Older prepared scopes lacking evaluation policy require new preparation/review. Preserve historical reports, and distinguish compatibility tests from numerical equivalence.

The separate bounded incline worker verifies worker, adapter and fixed-profile hashes before/after execution and in its returned evidence. Those checks establish local execution identity, not real-world calibration or a hostile-code sandbox. A new physics or visual evidence adapter needs its own admission, provenance and applicability tests; changing rubric text is insufficient.

## Capture overrides

Pass `--capture-overrides` to preparation with a versioned JSON object: `schema_version: "1.0"`, `id`, `version` and `requests`. Each request uses an existing capture ID and replaces its purpose, targets, timestamps, camera guidance, view role, nullable exact camera/projection constraints, sharing group, capabilities, minimum dimensions and limitations. Requirement bindings and evidence kind remain attached to the original request. Discover IDs from an initial preparation; freeze overrides in a new preparation and retain the previous version. Do not guess an ID or remove a requirement to improve results.

## Model adapter

Config contains `driver` (`codex` or `json-cli`), `executable`, `args`, `model`, `effort`, `timeout_seconds`. Codex uses fixed isolation flags and no extra args. Generic JSON CLI adapters own their provider transport and isolation; they receive the exact JSON request on stdin and return the required JSON on stdout. Optional config fields declare modalities and call/request/output byte budgets. Both roles retain requests, full local output schemas, provider-compatible schemas for Codex, native logs and responses. Provider schema adaptation does not remove local validation. All explicit images must actually be sent to a vision-capable model for visual review; a text-only adapter must report unknown. The harness cannot verify a generic adapter's remote payload.

## Suggested adopter validation record

Record profile/version, scene and plan hashes, original brief, requested/returned evidence, model requested and any verified resolved identity, raw/effective opinions, script outcomes, expected behavior and observed discrepancies. A test-double response verifies plumbing, not model accuracy. Repeat real reviews before making reliability claims and retain negative findings. Do not present broader article or application coverage as proof a particular check ran.
