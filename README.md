# Scene Acceptance

I built this harness to manage acceptance of a particular 3D delivery: **which requirements apply, what evidence supports them, and what needs to happen next.** It checks saved OpenUSD scenes against selected rules and a reviewed brief, with optional model review of caller-supplied renders and declared decisions.

A completed scene can still miss part of the brief or rely on an assumption the owner did not intend. The harness gives the receiving application inspectable evidence and repeatable checks after repairs. The owner defines acceptable use and decides release.

**Status:** experimental. This checkout is the **0.7.0 development candidate**; the latest published release remains [0.6.0](https://github.com/pr9868/scene-acceptance/releases/tag/v0.6.0). See the [enhancement decisions](docs/ENHANCEMENT_DECISIONS.md) for implemented changes, implemented extensions and remaining evaluation work.

## Start here

Install from this checkout with Python 3.12:

```sh
python -m pip install '.[nvidia,article_checks]'
```

Use the repository's `main` branch for the development features described here, including the default review-risk levels. For the earlier tagged release, check out `v0.6.0` and follow its README; it does not include those newer features. Installation is through GitHub; this package is not published on PyPI. Add the `pdf` and `isolation` extras for PDF sources and supervised native execution.

| Path | Use it when | Start with |
|---|---|---|
| **1. Checks only** | You have a contract selecting the rules, subjects and tolerances. No model is needed. | The command below and [pack authoring](docs/PACKS_API.md). |
| **2. Brief with reviewed scope** | You have text, images or PDF pages and need a proposed requirement map. | [Prepare → review scope → evaluate](docs/PREPARATION_AND_SKILLS.md#invocation). The owner reviews the interpretation before it becomes acceptance policy. |
| **3. Full workflow** | You also need visual judgment or review of declared assumptions. | [Application workflow](docs/APPLICATION_PROTOCOL.md) plus [optional triage and human closure](docs/ASSUMPTION_TRIAGE.md). The caller supplies renders and a model CLI. |

```sh
check-3d --bundle-root ./delivery --candidate scene.usda \
  --contract contract.json --out ./new-report
```

Omit `--contract` to run the general 27-rule delivery baseline. A baseline pass says nothing about requirements it never tested. `check-3d --list-tests` lists available checks; the report lists what actually ran, its subjects, passes, failures and missing evidence.

![The brief becomes reviewed requirements. Packs and optional review evaluate the saved delivery. The owner receives evidence, gaps and next actions.](docs/images/acceptance-workflow.svg)

## Responsibilities

| Who | Responsibility |
|---|---|
| Human/domain owner | Defines intended use and delivery policy, reviews the proposed scope, supplies engineering judgments and owns release. |
| Calling app or agent | Supplies saved scenes and briefs, renders requested views, keeps review records and routes repairs or evidence requests. |
| Harness | Runs selected measurements, keeps model opinions separate, checks evidence identity and reports coverage and the next action. |
| Producer | Builds and repairs the scene against the agreed brief and delivery policy. |
| Pack author | Adds a specialist check with explicit inputs, coverage, limits and passing/failing/missing-evidence controls. |

A brief can include a P&ID, equipment list, dimensions, photos or intended behavior. Raw preparation accepts text, images and selected PDF pages or regions with source citations. The interpreter proposes supported requirements and requests evidence. It cannot guarantee that it understood the whole job.

## What it covers

| Area | Supported scope |
|---|---|
| General structure and delivery | Selected OpenUSD/NVIDIA rules, dependencies, bindings, texture readability and authored-motion sanity. |
| Brief-specific measurements | Named geometry, placement, timing, sampled connections and explicit source-image comparisons. |
| State between events | [Held token/string/bool agreement](docs/SEMANTIC_CHECKS.md) across every authored transition in a declared interval, using caller-supplied reference and activation state. |
| Process connectivity | [Equipment tags, ports, directions and directed relationships](docs/SEMANTIC_CHECKS.md) against a structured connection list. No P&ID extraction or process-engineering approval. |
| Visual review | Optional model opinions on suitable caller-rendered views; no built-in renderer or GPU requirement. |
| Assumption triage | Optional model recommendations on selected declared decisions. Human-review items use default low, medium and high definitions that owners can override, with owner minimums enforced. Low still requires review; items without a supported grade stay unrated. A matching human record can close a triage request; it cannot clear measured failures or missing required evidence. |
| Assumption audit | A separate experimental operation proposes cited questions about undeclared choices. Questions are never automatic findings or approvals. |
| Extended checks | Triangle clearance, bounded translation sweeps, continuous connections, layer policy, UDIM dependencies and explicit color/orientation comparisons. [Scope and limits](docs/EXTENSIONS.md). |
| External measurements | Named viewer-performance traces and caller-owned engine profile/runtime tests with retained native evidence. |
| Simulation | A fixed CPU ramp-and-block example remains available as an explicitly selected example pack; general simulation stays with the calling engine. |

Where a [SimReady profile](https://docs.omniverse.nvidia.com/simready/latest/simready-faq.html) fits the job, I would use its validation and runtime tests within this workflow. The [external-engine bridge](docs/EXTENSIONS.md#engine-bridge-and-caller-evidence) can invoke a caller-configured CLI and import selected native results. Its transport controls are tested; a specific SimReady/PhysX installation still needs its own passing/failing runtime validation. The NVIDIA baseline pack continues to select USD Validation rules.

## Use or extend it

- [Adopter guide: your brief, responsibilities and reusable packs](docs/ACCEPTANCE_WORKFLOW.md)
- [Application API, repair comparison and invocation accounting](docs/APPLICATION_PROTOCOL.md)
- [Pack API](docs/PACKS_API.md), [test inventory](docs/TEST_INVENTORY.md), [judge customization and packaged skills](docs/PREPARATION_AND_SKILLS.md)
- [Consumer CI example](examples/ci/README.md)
- [Extended capabilities, evidence formats and native worker](docs/EXTENSIONS.md), [experimental Blender client](examples/blender_scene_acceptance/README.md)
- [Two-scene findings and repairs](examples/two-scene-repair-study/README.md), including the route-indicator finding from separate review
- [Human labels and triage evaluation](evaluation/triage-value-v1/README.md): how to measure the model's review recommendations; labels are not required for ordinary harness runs. Human labels and independent baseline are still pending.
- [Detailed reference and retained experiments](docs/REFERENCE_GUIDE.md)

Checks and providers run as trusted local code. The optional supervised worker bounds native execution resources; it is not a filesystem/network security sandbox. The application enforces release policy. Reports can contain caller paths and evidence. Review them before publishing outside the receiving application.
