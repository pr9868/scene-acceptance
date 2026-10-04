# Supplemental checks and review consolidation — local development

The installed Scene Acceptance distribution now contains `brief.four-job` 1.0.0 (21 named checks) and `scene_acceptance.review` 0.2.0. `check-3d --review-plan` produces one report with the unchanged artifact verdict, a declared-scope verdict, obligation counts and detailed artifact coverage. The generic baseline remains 27 checks; example-specific targets require explicit selection.

| Verification | Outcome |
|---|---|
| Full software suite | 380 passed, no skips, including all 42 retained review controls and 31 new consolidation tests |
| Frozen supplemental replay | 21 expected outcomes: eight original artifacts, eleven faulty derivatives and two valid alternatives |
| Readable but wrong image | Decoding passes; declared pixel content fails |
| Valid panel offset and variable motion speed | Both accepted under the original brief; the constant-speed comparison remains advisory |
| Missing image or reference | Missing evidence is UNKNOWN while independent dimensions/UV/shader checks still execute |
| Review integrity | Missing mappings, stale input/evidence, proposed inferences and producer self-approval controls preserved; known failures cannot be overridden |
| Known wrong mapping | Deliberately mapping a material obligation to a passing format check still accepts when the caller marks it reviewed; relevance cannot be inferred automatically |
| Packaged installation | Main package installed from a wheel; imports/implementation identity verified outside the checkout. Existing pinned dependency installations reused, not freshly resolved |
| Report usability | Desktop 1440 px and mobile 390 px; 12 example checks, search narrows to one, no JavaScript errors or document overflow. Narrow count-table overlap found and fixed |

The frozen fixtures and expected outcomes are in `cases.json`, with byte identities in `frozen-inputs.json`. Copied fixture contracts retain the former experiment-local identifier/digest; `run.py` explicitly migrates copied contracts to the integrated pack. Original data is never rewritten. The derivative cases are evaluator-created controls, not observed producer mistakes. Tests include these same fixtures; counts are not independent experiments.

```sh
python -m pip install '.[test,nvidia,article_checks]'
python -m pip install ./examples/studio-mesh-pack
python -m pytest -q
python evaluation/consolidation-v1/run.py --out /tmp/consolidated-controls
```

The main `reproduce.py` workflow now includes these 21 cases alongside the older mesh, provider, timing and article evidence. Compact final run receipts are retained beside this record. Full private producer replays remain in the Learning evidence directory; no excluded private demo measurements or assets are included here.

Source identity for the completed implementation: `8ed1805709031cf0dbe4b58c26a86ef2a783cfb9e0e9f2f6b3c719b62426953f`.

Limits remain substantive: four-job constants are not universal scene criteria; root-layer field equality is not composed-scene equivalence; sampled motion is not continuous proof; UVs/pixels are not rendered appearance; simulation is not physical calibration. Review identities are not authenticated, absent requirements remain undiscovered, and mapping relevance remains caller-owned. No new model call, GPU job, GitHub push, release or article publication occurred.
