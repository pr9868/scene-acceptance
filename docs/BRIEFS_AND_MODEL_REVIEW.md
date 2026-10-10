# Text/image briefs and optional model review

The generic baseline diagnoses saved scene structure, dependencies, readable images and authored motion data. It cannot know the intended dimensions, image content or trajectory without a target. The core engine can execute those target-based measurements when a brief has an explicit check mapping.

`check-3d --brief` adds source text, reference images, provenance and a requirement map to the existing report. It copies the admitted scene and declared brief files into a new evaluation snapshot, compiles the baseline plus selected checks, then runs the existing declared-scope review. It never edits the original delivery. A different brief can produce a different result for exactly the same scene.

## Runnable sample

Use the same executable in either mode:

```sh
# General diagnostics, without a brief.
check-3d --bundle-root /path/to/delivery --candidate scene.usda \
  --out /path/to/general-report

# General diagnostics plus the checks mapped from a text/image brief.
check-3d --bundle-root /path/to/delivery --candidate scene.usda \
  --brief briefs/brief.json --out /path/to/brief-report
```

The first command selects the 27-check baseline automatically and writes `general-report/report.html`. The second includes that baseline, adds the mapped requirements, and writes `brief-report/report/report.html`. Both commands require a new output directory outside the input bundle. Missing optional check providers remain errors, never passes.

The second command expects a mapped JSON brief manifest, not a raw prose file. For example, `delivery/briefs/brief.json` can reference `briefs/instructions.md` and `briefs/reference.png`, with check mappings and coverage declarations in the manifest. The source files must be inside the bundle. For raw text/image sources, the separate [preparation interface](PREPARATION_AND_SKILLS.md) uses an explicitly configured interpreter to propose a map for caller review. Evaluation itself does not reinterpret it.

Install the development package with its optional measurement dependencies using the repository installation instructions. Then:

```sh
python evaluation/brief-study-v1/prepare.py --out /tmp/brief-examples
check-3d --brief briefs/image-a.json --candidate scene.usda \
  --bundle-root /tmp/brief-examples/panel --out /tmp/matching-brief
check-3d --brief briefs/image-b.json --candidate scene.usda \
  --bundle-root /tmp/brief-examples/panel --out /tmp/different-brief
```

The same retained panel passes the first reference and fails the second. The second reference is a different assignment, not a historical producer error. `briefs/size.json` demonstrates text-only scope; `briefs/conflict.json` records an unresolved contradictory width. All sample briefs are labeled assistant-authored presets. They are examples of the input format, not independent human requirements or approvals.

The output contains `report/report.html`, source-text/image copies, `brief-context.json`, the existing result and specification matrices, compiled `inputs/__brief_contract__.json`, the caller plan, and a `source-integrity.json` receipt. `--expected-brief-sha256` can pin the manifest. Exit codes remain 0 for acceptance within declared scope, 2 for rejection, 3 for required review/insufficient evidence and 4 for an evaluation error.

## What a brief package contains

`brief.json` has `schema_version: "1.0"`, an ID, title, intended use, provenance statement, up to sixteen source files, explicit checks, requirements and a mapping-review record. `scene_acceptance.briefs.BRIEF_SCHEMA` is the closed schema; the prepared examples contain complete JSON.

- Each file has a bundle-relative path, `text` or `reference_image` role, and a caption. Text is bounded to 64 KiB per file. Visual references accept single-frame RGB/RGBA PNG/JPEG, at most 8 MiB and 16 million pixels each, with 32 MiB total reference bytes. Model review admits at most twelve images including scene views. Original bytes are hashed and copied; a screenshot is not automatically a dimensioned engineering reference.
- Each selected check uses the normal pack/check/parameters fields and optional `specification_source`. Mark actual user-supplied instructions `human` and cite their source; keep assistant-authored examples `preset` or `agent`. Source attribution is recorded, not authenticated.
- Each requirement uses the existing review item format: statement, basis, mapped check IDs, required/advisory flag, area, source and coverage declaration. A missing mapping remains unknown. Qualitative or continuous-time requirements can require separate review even when sampled checks pass.
- `mapping_review` says who checked the relevance of the map. `pending` prevents a full declared-scope acceptance. A wrong but syntactically valid mapping remains a known limitation: software cannot establish that a person selected all relevant checks.

The direct runner consumes a saved map. A caller can author it or use the preparation interpreter, whose output remains pending review. Conflicting instructions must remain unresolved obligations rather than being silently dropped. A schema-valid model response does not establish complete interpretation. Adding a source file without a mapped measurement does not create coverage.

## Added reusable measurements

| `brief.measurements` check | Measurement | Boundary |
|---|---|---|
| `bounds` | Recomputed world size/centre of one Cube, Mesh, Cylinder or Sphere | One time; no shape equivalence; ignores untrusted authored extent hints |
| `children` | Active direct children of the requested USD type | Counts do not prove useful geometry or machine function |
| `axis_gap` | Directed gap between two named world bounding boxes | One axis/time; no walkability, safety or swept-volume proof |
| `metadata` | Explicit authored up axis, units and/or clock endpoints/rate | Missing authoring cannot pass on a USD fallback; values do not prove behavior |
| `image_pixels` | Decoded RGB pixels in declared regions or a binary mask, with maximum and optional mean channel-error limits | Stored rows; excluded pixels are unassessed. No colour management, UV orientation or rendered-appearance proof |

Each check reports comparison subjects and observed/expected values. A roller-count comparison is one comparison involving twelve children, not twelve independently passing roller-quality tests. Reuse `motion.timing` for elapsed-second positions and clock requirements. Other installed packs remain available; external packs still require `--allow-pack` and the trusted entry-point interface.

To add a requirement: retain its original text/image reference, select or implement the measurement, choose tolerances explicitly, map its check IDs, and leave anything outside the measurement unresolved. Inspect the updated report before treating the mapping as reviewed.

## Comparison regions and image policy

Visual reference admission and exact pixel comparison serve different purposes. The visual path preserves RGB/RGBA bytes, alpha and ICC metadata; it records image dimensions/mode and that no conversion, compositing or EXIF rotation was applied. The exact comparator retains its smaller single-frame RGB-only PNG/JPEG budget: 1 MiB and 262,144 pixels per image. Unsupported size or mode stays unknown. A normal 1080p photograph may therefore be usable as interpretation evidence without qualifying for this numerical comparison. The harness does not silently resize or flatten it.

`brief.measurements.image_pixels` in pack `1.1.0` accepts `regions`, `excluded_regions`, an optional `mask_image`, required `max_channel_error` and optional `max_mean_channel_error`. Rectangles use stored-pixel coordinates: X right, Y down, half-open bounds. Selected pixels are the union of included rectangles minus exclusions, intersected with the mask's white pixels. With no regions/mask, the whole image is selected. A mask is same-size RGB black/white PNG/JPEG under the same decoder limits; declare it as a brief reference/evidence source so it is hashed and copied. Empty selections and out-of-bounds rectangles are invalid policy, not passing comparisons.

For the 256 × 256 four-quadrant JPEG example, the reusable comparison can express the earlier boundary exclusion directly:

```json
{
  "asset_attribute": "/World/Looks/Label/Texture.inputs:file",
  "reference_image": "briefs/reference.png",
  "max_channel_error": 32,
  "max_mean_channel_error": 4,
  "excluded_regions": [
    {"x": 120, "y": 0, "width": 16, "height": 256},
    {"x": 0, "y": 120, "width": 256, "height": 16}
  ]
}
```

This is a policy example; use the actual delivered attribute path and a declared reference. All three channel means must meet the mean limit. Reports retain selected/excluded pixel counts, maximum and per-channel mean errors, whole-image diagnostics, source hashes and the comparison policy. Excluded pixels receive no acceptance claim. These are stored RGB-value comparisons, without perceptual metrics or colour-space conversion.

Texture selection can follow a bounded static material-input connection to one asset-valued source. Cycles, multiple sources, animated values and computed shader outputs remain unknown; the harness does not execute shader code. This applies to both numerical pixel comparison and selected-image decoding.

## Optional CLI model review

The [unified invocation](EVALUATION_MODES.md) now supports `checks`, `judge` and `both` with an optional brief, scene-bound views and separate measured/advisory reporting. The compatible separate command below still requires an existing brief report and exposes script evidence to the reviewer.

Normal harness runs do not call a model. A caller explicitly invokes a separate advisory review:

```sh
check-3d-judge --report /tmp/different-brief/report \
  --config /path/to/my-judge.json --out /tmp/model-review
```

A Codex configuration is:

```json
{
  "driver": "codex",
  "executable": "/absolute/path/to/codex",
  "args": [],
  "model": "your-available-model",
  "effort": "high",
  "timeout_seconds": 600
}
```

The Codex adapter uses an ephemeral, read-only, tool-disabled invocation and attaches the explicitly selected images. An existing standalone CLI may be older than the application's bundled CLI; record the executable/version rather than assuming they are equivalent. No automatic upgrade or model substitution occurs.

For another CLI, use `driver: "json-cli"` with an executable and argument array. That trusted adapter reads one JSON request from stdin and returns one JSON object on stdout. It owns authentication, provider/image transport and its own isolation. The request contains the original brief, requirements, scene inventory, every recorded script check and explicit image paths. The response must match `scene_acceptance.judge.RESPONSE_SCHEMA`, echo the request hash, cover every requirement once and cite known evidence IDs. See `tests/test_judge.py` for a deterministic adapter example. Do not treat the mock as a model test.

Optional `--view /path/to/scene.png` arguments add caller-selected diagnostic images. Providing the CLI authorizes that adapter to send these explicit inputs to its configured model provider. Source/reference text and scene content are data, not instructions to execute.

The separate report labels each model opinion `consistent`, `concern` or `unknown`. It retains request/response, CLI logs, requested model, available usage, elapsed time, hashes and failures. Missing, malformed, stale or untraceable responses remain errors. Known evidence IDs prove traceability, not semantic correctness. The model cannot override a script failure, turn an unknown into a measured pass, or supply human approval. A same-family model review is not independent validation.

## What the study can establish

The frozen protocol in `evaluation/brief-study-v1/PROTOCOL.md` separates assessment context from creation context. Reassessing an existing scene under a later brief measures agreement with that later brief; it does not show what would have happened had the original producer received it. Fresh creation runs address that separate question, within the disclosed bounded production interface. Three repetitions per arm are exploratory. Preserve negative findings and evaluator errors; do not promise that a more detailed prompt will eliminate failures.
