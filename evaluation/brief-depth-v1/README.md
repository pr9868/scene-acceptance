# Brief depth across three scene families

This private exploratory experiment compares newly generated gantry, rotary and pump/valve illustrations at simple, light, medium and detailed prompt levels, with two fresh repetitions of each. Read [PROTOCOL.md](PROTOCOL.md) before interpreting results. The actual owner-local delivery packet is separate from the source distribution.

The generator writes complete USDA directly through a tool-disabled CLI call. Its output adapter saves that source verbatim and expands a small palette raster into a PNG. No producer code is executed, and no scene is repaired. This tests first deliveries under a constrained common output interface, not an interactive modelling workflow or the older Astra demo projects.

## Reproduce the preparation and controls

From the repository root, use a Python environment with this version of Scene Acceptance and its USD/material dependencies installed:

```sh
python evaluation/brief-depth-v1/study.py --out /absolute/new-packet/inputs
python evaluation/brief-depth-v1/controls.py \
  --inputs /absolute/new-packet/inputs --out /absolute/new-packet/controls
```

The 33 controls comprise one fixture that passes the ten explicit target checks per family, plus ten deliberate mutations per family. “Positive” here refers to those ten target checks; it does not claim full engineering or general-profile acceptance. An interior trajectory mutation preserves the endpoints. A changed image remains readable. These controls establish that the intended measurements distinguish those specific changes.

Freeze the protocol, source scripts, input hashes, checker implementation and successful control receipt **before** model generation. The retained run includes that freeze separately. Do not overwrite an earlier run directory or change its requirements after seeing outputs.

```sh
python evaluation/brief-depth-v1/freeze_study.py \
  --root /absolute/new-packet --cli /absolute/path/to/compatible/codex
```

The October 3 packet's original freeze was performed before this convenience helper was added; its original receipt is preserved. The helper reproduces that preparation format for a new run.

## Generate only when new model calls are authorized

```sh
python /absolute/new-packet/frozen-study/run_producers.py \
  --inputs /absolute/new-packet/inputs \
  --out /absolute/new-packet/production \
  --cli /absolute/path/to/compatible/codex
```

This makes up to 24 model calls, with at most two in flight, through existing CLI authentication. The protocol fixes the requested model, fresh context, tool isolation, schedule, output budget and deadline. The runner reserves every trial once and retains native events, exact prompts, source images, raw JSON, failures and usage. It has no automatic repair or rerun. Requested model identity is not proof of the resolved model snapshot.

## Assess saved deliveries without more model calls

```sh
python /absolute/packet/frozen-study/evaluate_producers.py \
  --production /absolute/packet/production --out /absolute/packet/assessments
python evaluation/brief-depth-v1/build_report.py --root /absolute/packet
```

`--resume` on the evaluator allows incremental assessment of newly completed receipts while preserving previously assessed scenes, and requires the same checker implementation. The final verifier expects all 24 attempts to have completed. Missing or invalid deliveries are retained as unassessed, never converted to invented failed measurements or silently excluded.

Each delivered scene gets the unchanged general baseline, the mapped requirements actually supplied, and the same full target for its family. The report records individual outcomes and subject units, with source prompts, diagnostic projections and exact evidence. General findings, noncompliance with supplied requirements, differences from withheld targets and unresolved review requirements remain separate.

Only detailed prompts receive the exact image and dense motion specification. Passing 21 sample positions does not prove continuous behavior; matching source pixels does not prove visible texture mapping. Assembly completeness, appearance and physical validity remain outside the numeric guarantee. Two repetitions per family and condition are exploratory evidence, not a general failure rate or productivity estimate.

## Separate follow-up

[SECONDARY_SAMPLING.md](SECONDARY_SAMPLING.md) records a 201-position follow-up added after the first primary results. `secondary_sampling.py --root /absolute/packet --controls` checks two constructed motion controls in a new directory; without `--controls`, it incrementally assesses unchanged producer deliveries. It uses the existing motion pack with a different explicit sampling configuration. No new harness implementation is needed. Its results must stay separate from the original ten-rule comparison. `summarize.py --root /absolute/packet` writes final evidence tables after all 24 primary and secondary receipts exist.

For a fresh packet, freeze that follow-up after its controls, recording which primary results have already been seen:

```sh
python evaluation/brief-depth-v1/secondary_sampling.py --root /absolute/packet --controls
python evaluation/brief-depth-v1/freeze_study.py --root /absolute/packet --secondary
python /absolute/packet/frozen-secondary/secondary_sampling.py --root /absolute/packet
python evaluation/brief-depth-v1/build_report.py --root /absolute/packet
python evaluation/brief-depth-v1/verify_packet.py --root /absolute/packet
python evaluation/brief-depth-v1/summarize.py --root /absolute/packet
```

The report builder and receipt verifier are study tooling. They do not change the core CLI's output protocol or automatically turn arbitrary prose/images into requirements. The images here are small deterministic texture references; semantic interpretation of photographs or engineering diagrams is not evaluated.

`depth_views.py --root /absolute/packet` adds separately recorded depth-tested diagnostic projections while retaining the initial painter-sort views. Neither preview evaluates textures or certifies appearance. `package_deliveries.py --root /absolute/packet` writes a new archive of the original source bundles and verifies every copied byte.
