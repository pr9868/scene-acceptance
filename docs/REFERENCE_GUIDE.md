# Detailed reference

Use the [README](../README.md) for current development/release status, supported capabilities and the three starting paths. This guide keeps runnable measurement examples and retained replay instructions; it is not a second capability inventory.

| Need | Current guide |
|---|---|
| Understand the brief, responsibilities and reusable packs | [Acceptance workflow](ACCEPTANCE_WORKFLOW.md) |
| Integrate the CLI or Python library | [Application protocol](APPLICATION_PROTOCOL.md) |
| Prepare a brief, review scope and request renders | [Preparation](PREPARATION_AND_SKILLS.md) and [readiness](MODEL_WORKFLOW.md) |
| Read the default summary and details | [Reporting](REPORTING.md) |
| Extend the checks or model review | [Pack API](PACKS_API.md), [test inventory](TEST_INVENTORY.md) and [skills](PREPARATION_AND_SKILLS.md#customization-shipped-in-the-wheel) |
| Review declared assumptions | [Triage and human closure](ASSUMPTION_TRIAGE.md) |
| Understand experimental extensions | [Boundaries](EXTENSIONS.md) and [first-delivery improvements](USEFULNESS_UPGRADE.md) |
| Maintain or release the package | [Maintenance checks](MAINTENANCE.md) |

## Try a passing edit and a rejected edit

Use Python 3.12. These commands install the core and its pinned test dependencies; NVIDIA and the experiment tools are optional for this first example.

```bash
git clone https://github.com/pr9868/scene-acceptance.git
cd scene-acceptance
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.lock
python -m pip install --no-deps --no-build-isolation .

check-3d \
  --bundle-root evaluation/mesh-v1/fixtures/translated_mesh \
  --contract contract.json --candidate scene.usda \
  --baseline baseline.usda --out /tmp/scene-accepted-01
```

Expected: `ACCEPT_FOR_USE`, exit code 0. Open `/tmp/scene-accepted-01/report.html` to see the requirements and their individual results.

Now check an edit whose outer dimensions are right but whose interior changed:

```bash
check-3d \
  --bundle-root evaluation/mesh-v1/fixtures/interior_shape_changed_same_bounds \
  --contract contract.json --candidate scene.usda \
  --baseline baseline.usda --out /tmp/scene-rejected-01
```

Expected: `REJECT`, exit code 2. Six checks pass; shape preservation fails because an interior point moved by 40 mm. This is a deliberately constructed evaluator test, not an observed agent failure.

![Projection of the saved tray geometry: unchanged outer bounds conceal a changed interior point](images/tray-evidence.svg)

Choose a new output directory for each run. Outputs must be outside the submitted bundle. Relative input paths resolve inside `--bundle-root`. A command-line usage error returns 4. Measured scene rejection returns 2; scope review or missing evidence returns 3. Use the structured report and its next action to decide what to do next.

## Evaluate a larger local bundle

The default dependency budget is 64 files per scene, including its root USD layer. The calling application can raise it for a larger approved delivery without editing the contract or flattening the scene:

```bash
check-3d --bundle-root ./delivery --contract contract.json \
  --candidate scene.usda --max-dependency-files 256 --out /tmp/larger-scene-01
```

The Python API accepts the same `max_dependency_files=256` keyword. Values must be integers from 1 to 1024. The report records the selected budget in `runtime.admission_limits`. Exceeding it produces `INSUFFICIENT_EVIDENCE` (CLI exit 3), with a `resource_limit` observation and unexecuted checks left `UNKNOWN`. This records a coverage gap; it does not establish a scene defect.

The budget belongs to the caller, not the submitted contract. Unique local layers and external assets count toward it, including missing declared assets; the root counts once and repeated dependencies count once. The limit applies separately to candidate and baseline. The composed-prim budget is separately configurable with `--max-prims` (default 10,000, maximum 250,000). The 32 MiB per-file limit, dependency allowlist, path containment and supported-composition rules still apply. This option does not add a default validation profile or change acceptance criteria. Run large evaluations in a caller-managed process with a suitable memory and time budget.

## How it fits into an application

![Requirements and evidence flow through checks and review to a caller-owned decision](images/acceptance-workflow.svg)

The core validates the contract, admits supported inputs, resolves approved packs, runs checks in prerequisite order and produces `result.json`, `report.html` and a manifest. Required checks determine the overall result; advisory findings remain visible. A failed prerequisite leaves its dependent checks unresolved.

| Result | What the caller can conclude |
|---|---|
| `ACCEPT_FOR_USE` | The required checks passed for this contract and submitted revision. Unchecked properties remain outside that conclusion. |
| `REJECT` | A required check found a violation. Other errors or missing evidence remain visible. |
| `INSUFFICIENT_EVIDENCE` | A required obligation could not be established from the supplied evidence. |
| `EVALUATION_ERROR` | Input, integrity or evaluator problems prevent a valid acceptance result. |

The caller owns the brief, approved providers, references, retry policy and release. Packs execute trusted Python in-process. The optional supervised worker adds time, memory, CPU and output limits; it does not isolate files or the network. There is no automatic scene-repair loop. See [native execution](EXTENSIONS.md#supervised-native-execution).

## Selected pack examples

This table explains the original measurement families. Use `check-3d --list-tests` and the [test inventory](TEST_INVENTORY.md) for the current catalog, including clearance, relationships, state and process checks.

| Pack | Included evaluation | Current limit |
|---|---|---|
| `openusd` | Explicitly selected native validators | The selected rules' scope; a clean result does not establish every requirement in a brief. |
| `geometry` | Cube and polygon geometry, placement, bounds and declared edit constraints | Bounded representations; shape-preserving translation uses corresponding points/connectivity. |
| `materials` | Resolved bindings, expected surface shader IDs and declared dependencies | Binding/file checks only; image decoding and source-pixel comparison are separate checks below. No rendered appearance acceptance. |
| `scene.audit` / `textures.decode` | General file/image/motion diagnostics and explicit image decoding | Decoding establishes readable supported images, not correct UV mapping or visual quality. |
| `brief.measurements` | Named bounds, child counts, axis gaps, metadata and source-image pixel comparisons | Bounded targets; no walkability, whole-scene rendered comparison or machine-function proof. |
| `motion` | World-space transform origins at contract-specified time codes | No whole-interval collision, orientation or dynamics proof. |
| `motion.timing` | Authored duration, optional exact clock rate, and sampled origins at elapsed seconds | Separate from the legacy time-code check; does not infer active motion duration or prove a continuous path. |
| `nvidia.asset-validator` | Explicitly selected NVIDIA USD Validation rules | Optional dependency; no SimReady certification or automatic fixers. |
| `studio.mesh-budget` | A separately installed example of a consumer's polygon budget | Example extension; face count does not establish rendering performance. |

Inspect the installed catalogue:

```bash
check-3d-packs
check-3d-packs --upstream openusd
python -m pip install '.[nvidia]'
check-3d-packs --upstream nvidia
```

Available names describe discoverability. They do not mean that every upstream rule has been exercised. A required but unavailable provider produces an evaluation error.

OpenUSD and NVIDIA validators already cover more than syntax and allow custom rules. This project combines their selected results with application requirements, evidence and revision identity. It does not claim a new category of semantic validation.

## Libraries and why I included them

| Library | Role |
|---|---|
| OpenUSD (`usd-core` 25.11) | Compose admitted scenes, inspect geometry/materials/transforms and run selected native validators. |
| JSON Schema (`jsonschema` 4.25.1) | Validate contracts, parameters and structured records. |
| NVIDIA USD Validation 1.20.0 | Reuse selected asset and physics configuration rules through an optional adapter. |
| Pillow 12.3.0 | Decode admitted image evidence and source textures; compare explicitly selected source pixels. |
| MuJoCo 3.6.0 | Execute the restricted two-box incline experiment on CPU. |
| NumPy 2.5.3 | Support the experiment's numerical operations. |

Some rules overlap. I would choose the checks at runtime through the application's contract, retaining overlap when it supplies useful evidence. The base install requires only OpenUSD and JSON Schema. The full replay adds the optional packages with pinned versions. Dependencies retain their own licenses; see [third-party dependencies](../THIRD_PARTY_NOTICES.md).

## Reproduce the retained results

From the project root, with the environment above active:

```bash
python -m pip install -r requirements-articles.txt
python -m pip install --no-deps --no-build-isolation ./examples/studio-mesh-pack
python reproduce.py --out /tmp/scene-acceptance-replay-01
```

The output directory must be new and outside this checkout. The replay verifies the distribution hashes and installed implementation identity before and after execution, and compares the new decisions and physics observations with the retained records. Changed pack pins are proposed explicitly in separate replay copies, with `contract-upgrades.json` recording each change. The original inputs and reports remain unchanged; direct evaluation rejects outdated pins.

| Evidence | What is reproduced |
|---|---|
| Software tests in this checkout | Core, pack, CLI, approval, evidence and integration regressions. The executed count and zero-failure requirement are recorded in the replay’s `pytest.xml` and `verification.json`. These tests include cases counted below. |
| 22 pack cases | Selected validators, materials, motion, external packs and error handling. |
| 32 mesh cases | Prior geometry and edit decisions, including the changed interior. |
| 17 timing cases | Clock changes, legal rescaling, duration, sampled seconds and unusable timing evidence. |
| Four content probes | Material decoding and motion-sampling coverage comparisons. |
| Three configuration cases and four CPU simulation runs | Positive/negative mass controls, then two friction assumptions at two timesteps. |

The counts overlap and are not independent model samples. The replay makes no model calls. Current reproduction runs on Python 3.12 on macOS arm64 and Ubuntu 24.04 in CI; the retained original runs keep their own environment records. Inspect the CI result for the revision you adopt. Other platforms need compatible wheels and their own verification.

The first pack run matched 19 of 22 expected decisions. Three texture-dependency cases falsely accepted. Explicit asset-attribute inspection corrected the reader, and the unchanged cases then matched 22 of 22. Both stages remain in the repository. A historical competent-script comparison tied on 18 shared cases, so these results do not establish an accuracy advantage over a suitable script.

## Inspect the evidence by question

- [Astra mechanical assembly](https://github.com/pr9868/scene-acceptance/blob/v0.5.0/examples/astra-mechanical-assembly/README.md): the recorded producer delivery, portable viewer, checks and evidence limits.
- [Evidence guide](EVIDENCE.md): where to find protocols, fixtures, first failures, corrected results and historical model outputs.
- [Historical material-delivery probe](../article-evidence/content-probes): binding/file checks alone accept an unreadable PNG. Version 0.5.0 adds decoding in the general baseline and a selectable image-decoding check; the retained probe isolates the narrower check. [Workflow](images/materials-flow.png).
- [Motion sampling](../article-evidence/content-probes): the same motion accepts at three requested times and rejects when a missed excursion is checked. [Workflow](images/motion-flow.png).
- [Motion timing](MOTION_TIMING.md): require the declared duration and sample positions in elapsed seconds; preserve valid clock/keyframe rescaling.
- [Physics experiment](../article-evidence/physics-experiment): selected configuration rules pass while task behavior differs with assumed friction. [Workflow](images/physics-flow.png).
- [Pack API](PACKS_API.md) and [external example](../examples/studio-mesh-pack): how to add another evaluation without modifying the core.

## What I want to test next

My next application trial would use independently supplied edit briefs and a producer connected by the caller. I would record first-attempt acceptance, violations missed by the evaluator, false rejections, unresolved requirements, repair attempts, total runtime cost and human review time. Comparing contract prechecking with findings received only after submission would test whether that feedback helps the producer.

The [trial protocol](../evaluation/producer-trial-v1/PROTOCOL.md) defines the inputs, comparison and record before execution. It is awaiting an independently supplied brief and external assessment; no workflow benefit is reported from that plan.

Version 0.5.0 includes the bounded texture-decoding, sampled-connection and incline-worker follow-ups, source-image pixel comparisons and optional advisory review of supplied renders. The historical v0.3.0 release remains unchanged. General continuous-motion guarantees, arbitrary physics import, deterministic comparison of fully rendered scene appearance and physical calibration remain future work.

## Contribute

Start with a consuming requirement and a failing example. Add checks as an external pack when possible, using the [contribution guide](../CONTRIBUTING.md). A useful contribution states what it measures, what it cannot establish and how another person can reproduce both passing and failing cases.

This is an AI-assisted project directed by Pradeep Kaushik. The recorded experiments are development probes with shared authorship of briefs, implementation and review. They are not an independent benchmark, a productivity study or validation against measured physical behavior.

MIT licensed. See [LICENSE](../LICENSE). Project context: [roughcut.dev](https://roughcut.dev).

**Disclaimer:** The views and opinions expressed in this account are those of my own and do not represent those of my employer, NVIDIA.
