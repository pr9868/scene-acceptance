# Extended delivery checks

These features are in the 0.7 development candidate. They broaden what a caller can ask, while keeping measurements, external evidence and model questions distinct. They do not establish that a delivery is fit for every use.

| Capability | What the caller supplies | What the harness returns | Boundary |
|---|---|---|---|
| PDF brief | PDF plus selected pages and optional regions | Text, drawing images and page/region citations in the proposed requirements | No OCR, CAD import or automatic P&ID understanding; scope review remains required |
| Composed USD | Local layers and assets | Selected variants, loaded payloads, inherited/specialized prims and instance proxies available to checks | All authored branches are admitted; no URLs, packages, value clips or dynamic formats |
| Layer policy | Required units and up axis | Mismatches by layer | Metadata checks do not convert geometry |
| UDIM dependencies | Local `<UDIM>` filenames and explicit dependency budget | Hashed tiles and a cross-check against OpenUSD discovery | Tiles 1001–1999; available tiles do not establish which tiles the brief intended |
| Mesh clearance | Two Cube/triangle-Mesh paths, time, representation and minimum distance | Triangle distance and pass/fail/unknown | Static topology; closed-solid containment requires valid consistently oriented solids |
| Clear-height zone | A world-space box and explicit obstacle list | Obstructions for each named obstacle | Does not infer a complete obstacle list or navigability |
| Swept clearance | Interval, translation paths, clearance and calculation budget | Conservative lower bounds over each certified interval | Animated rotation/deformation or an exhausted budget stays unknown |
| Continuous connection | Two local points, interval, allowed gap and numerical margin | A maximum-gap bound across every piecewise-linear segment | Saved translations with static other transforms; no arbitrary rotation or runtime-controller proof |
| Viewer performance | Named viewer/machine, resolution, camera path and rendered frame times | Median FPS, p95 frame time and threshold results | Draw callbacks are not rendered FPS; the caller runs the viewer |
| Engine evidence | Caller-controlled CLI adapter, engine/profile identity and native status mapping | Original engine report, normalized named profile/runtime tests and gaps | Tested transport is not validation of a specific SimReady/PhysX installation |
| Color/orientation comparison | Explicit sRGB, linear RGB8 or ICC policy and stored/EXIF orientation | Source-pixel errors in linear sRGB | RGB8 only; no HDR, alpha compositing or rendered-image equivalence |
| Assumption audit | Scene, brief, optional declared decisions, script report and views | Cited questions for a person | Experimental model opinion; no finding, approval or acceptance decision |
| Native isolation | POSIX worker memory/CPU/time budgets | Bounded worker result or explicit execution error | Resource containment, not a hostile-code security sandbox |

The admission boundary still limits a stage to 10,000 composed prims, including instance proxies, and 32 MiB per file. These extensions do not by themselves replay the complete 125,000-prim distribution-centre delivery. A larger admission and context strategy remains necessary for that original-scene audit.

Discover exact parameters through `check-3d-packs` and `check-3d --list-tests`. Fixture-specific incline and four-job packs live in the example catalog (`check-3d-packs --include-examples`). A contract explicitly naming one still loads it for replay. Third-party packs still require caller approval.

## PDF sources

From the repository checkout, install the PDF extra with `python -m pip install '.[pdf]'`. A raw brief source can be:

```json
{"path":"drawings/layout.pdf","role":"pdf","caption":"Service access drawing","selections":[{"page":2,"region_pdf_points":[0,0,600,420]}]}
```

Pages start at 1. Regions use PDF points with the origin at the bottom left. Omit the region for the whole page. Select at most twelve regions per source and keep the combined reference/view image budget in mind. Native extraction retains embedded text and renders each region to an RGB image; scanned pages can supply images even when there is no extractable text. Rotated PDF pages require a normalized source revision first. Text extraction does not establish reading order or drawing semantics.

Preparation preserves the original PDF, its hash, derived source hashes and page/region locations. The interpreter cites source IDs and exact text quotes. Those citations travel with the proposed requirements; they do not grant approval. Use the supervised worker for unfamiliar native inputs.

## Assumption audit

```sh
check-3d-app audit --bundle-root ./delivery --candidate scene.usda \
  --raw-brief brief.json --audit-config ./caller/audit.json --out ./audit-run
```

The model configuration uses the same optional CLI protocol as the judge. Add `--views views.json` for scene images; no renderer runs inside the harness. `--producer-decisions decisions.json` accepts the packaged `audit-declarations-v1` schema. A supplied `--script-report report.json` also needs `--expected-script-sha256 HASH` and must describe the same scene revision.

An audit asks questions such as whether an indicator's state has been specified during parcel occupancy. It must cite supplied evidence and valid scene paths. Exit 3 means questions were proposed; exit 0 means this invocation proposed none. **Neither means delivery acceptance.** Questions can lead the owner to clarify the brief, request views, add a check or decide that an intentional variant is acceptable. Triage remains the separate operation for evaluating declared items against the owner's consequence policy.

Transport tests use deterministic adapters. They establish citation checking and error handling, not discovery quality. The human-labeled triage study, independent producer trial and blinded diverter holdout remain separate evaluation work.

## Engine bridge and caller evidence

```sh
check-3d-app collect-engine --bundle-root ./delivery --candidate scene.usda \
  --adapter-config ./caller/engine.json --out ./engine-run
```

The caller owns the executable configuration outside the producer bundle. The bridge copies the admitted scene, passes its path to the configured CLI, supervises resource use and retains the native JSON report. It refuses a run that modifies the scene snapshot. The adapter configuration names the profile, engine environment and JSON pointers for the tests to import. Missing selectors or unfamiliar status values stay unknown. Review the native report schema before configuring these mappings; the harness does not guess it.

The versioned `engine-adapter-v1` schema documents the configuration. Arguments may contain whole-argument placeholders `{scene}`, `{report}` and `{out}`. No shell is used. The `external.evidence.engine_tests` pack compares the resulting receipt with the caller's required tests and verifies its native-report attachments. Place the receipt and named attachments among the explicit `evidence_sources`; attachment paths are relative to the evaluation bundle. Preserve the original receipt when organizing a copy for evaluation.

For SimReady, select the relevant profile through its own validator. The [Foundation validation guide](https://nvidia.github.io/simready-foundation/2026.08.0/guides/validate_workflow.html) documents `simready-validate` and native JSON output. [Runtime benchmarking](https://nvidia.github.io/simready-foundation/2026.08.0/guides/benchmark/benchmark.html) runs in the target engine and has separate results. Keep those phases distinct in the adapter. This repository tests the bridge with controlled subprocesses; it does not claim a completed SimReady/PhysX runtime test on this host.

## Supervised native execution

```sh
check-3d-isolated --wall-seconds 120 --memory-mib 2048 --cpu-seconds 120 \
  check --bundle-root ./delivery --candidate scene.usda --out ./new-run
```

Install the `isolation` extra. Python callers use `scene_acceptance.isolation.invoke_isolated`. The worker opens USD and PDF in a separate process. The POSIX supervisor monitors the process tree, bounds output and kills its owned processes on time, memory or CPU limits. Linux also applies per-process address-space and CPU limits. Deadline and cancellation controls remain active in the supervisor. Progress from the isolated worker is retained and emitted after completion. macOS uses sampled resident memory; brief spikes are not a hard allocator limit. If process inspection is unavailable, execution fails explicitly. Filesystem/network access still needs an operating-system container or sandbox when the input or extensions are hostile.

## Adoption and evaluation

The [Blender client](../examples/blender_scene_acceptance/README.md) calls this same boundary on saved USD files. Its UI still needs a live Blender integration test. [The solver study](../evaluation/solver-drift-v1/README.md) records the numerical sensitivity of the existing two-box example without changing its acceptance policy. [Triage evaluation](../evaluation/triage-value-v1/README.md) requires human labels and a measured human baseline; unit tests cannot provide those results.
