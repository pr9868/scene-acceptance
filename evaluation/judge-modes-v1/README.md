# Script and model review study

The new `check-3d --mode checks|judge|both` entry point is implemented. Use [the mode guide](../../docs/EVALUATION_MODES.md) for applications and [the complete test inventory](../../docs/TEST_INVENTORY.md) for scope. This folder contains reproducible study tooling; running the software tests never starts this model study.

`PROTOCOL.md` fixes a separate review of 24 previously generated synthetic scenes, three repeated reviews and two context probes. Model review does not modify or regenerate a scene. A configured model CLI is required and may transmit the explicit admitted evidence to its provider. The brief/dependency hashes, view bytes, source renderer limits, requested model, rubric and installed evaluator are frozen before a run. Use this protocol only with authorized inputs.

1. Install a non-editable harness wheel and its declared dependencies. Keep the existing original study packet unchanged.
2. Prepare a new root with `run.py --prepare --root NEW --original ORIGINAL --cli CODEX_EXECUTABLE --harness CHECK_3D_EXECUTABLE`. This copies the study/evaluator snapshot and views, retaining original hashes and the 29-case schedule.
3. Validate admission and script parity locally with `preflight.py --study NEW --original ORIGINAL --out NEW_PREFLIGHT`. This uses a deterministic software adapter and makes zero model calls.
4. Run `run.py --root NEW` once. It reserves each case exclusively, launches at most two independent CLI processes, preserves native responses/errors and never retries an answer. The configured CLI must have the host access needed to initialize; script results remain available if it fails.
5. Run `summarize.py --root NEW`, then `verify.py --root NEW`. The summary requires all scheduled slots to finish, including errors. Verify views and the desktop/mobile report presentation separately.

The retained October 3 execution exposed two infrastructure boundaries before any response: the tiny exact-reference decoder could not accept 960×600 scene views, then the desktop CLI could not initialize under the outer host sandbox. Both failed batches are preserved separately. The corrected scene-view decoder has its own bounded pixel/byte policy and regression test. The real review used the same frozen scene/view bytes; successful or partial model answers were not replaced.

`summarize.py` writes HTML, Markdown, JSON and CSV with measured results, opinion counts, exact explanations, three repeated-opinion comparisons and the same-scene context probes. It explicitly separates rule counts, target-check counts and geometry-prim inventory. `verify.py` checks the original sealed packet, source immutability, script parity, distinct native contexts, rubric/configuration, request/response identity, evidence hashes and local report links. It does not establish model truth.

A `corroboration.json` file may add separately recorded follow-up to the summary. Each item uses `case`, `requirement_id`, `status` and `explanation`; keep exact source/evidence pointers in additional fields. Never edit the original model response. `corroborate_cable.py` is one post-review measurement of a nominated cable concern, checking mesh face connectivity and selected terminal points at retained times. It is not part of the frozen general checks, not a continuous-motion guarantee and not a new default cable test.

Model-only concerns begin as unverified claims. A concern supported by an existing script measurement is corroboration, not a newly added detection. View readability can be a limitation of the chosen evidence and renderer. Unknown materials or physics are honest coverage gaps. No numeric opinion count is an engineering acceptance score.
