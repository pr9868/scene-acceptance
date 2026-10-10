# Evidence guide

The release keeps the inputs and observations needed to inspect the bounded claims in the README. The default replay executes existing fixtures. It does not request new model outputs or rerun the historical script comparison.

| Directory or record | What it contains | How to read it |
|---|---|---|
| `evaluation/packs-v1/fixtures` | 22 frozen development cases | Expected decisions test the evaluator, not a producer's failure rate. |
| `evaluation/motion-timing-v1` | 17 frozen timing controls and the first run | Rate-only changes reject, legal rescaling accepts, and missing timing evidence stays unresolved. These are additional constructed cases. |
| `evaluation/packs-v1/runs/first` | The first run, matching 19 of 22 cases | Three texture-dependency cases falsely accepted. These failures are retained. |
| `evaluation/packs-v1/runs/final` | Corrected results for the same fixtures | Asset-valued attribute inspection fixed the reader. All 22 matched. |
| `evaluation/mesh-v1` | 32 geometry cases and retained reports | Includes unchanged bounds with a changed interior, wrong destinations and missing evidence. |
| `evaluation/runs/final-comparison/summary.json` | Historical comparison with a competent script | Both matched 18 shared cases. This is not evidence of superiority. |
| `experiments/fresh-astra-content-2026-09-19` | Selected historical protocols, prompts, responses, saved scenes and assessments | Eight responses from nine CLI launches: six saved scenes accepted for layout; two correctly identified incompatible requirements. No observed hallucination in the evaluated outputs and no content repairs. |
| `article-evidence/content-probes` | Frozen texture and motion comparisons | Delivery acceptance does not imply a decodable image; sampled origins do not establish motion between samples. |
| `article-evidence/physics-experiment` | Frozen two-box inputs, restricted adapter, models and traces | Four one-second CPU runs test a 10 mm drift requirement under two assumed friction values and two timesteps. Neither friction value was measured. |

Two historical physical-evidence assessments remained unresolved, as intended. Deliberately modified derivatives are separate from the model outputs. In particular, the shrunken derivative exposed a missing shape requirement; it was not a defect produced by Astra. The requested model identifier is recorded, but no unreported backend snapshot is inferred.

The historical protocol describes raw execution logs retained during the original experiment. This public distribution includes selected prompts, final responses, artifacts and assessments, rather than every local session log. Those historical observations are inspectable; regenerating them would be a new experiment.

## Reproduction and file identity

Run the README setup and `python reproduce.py --out /tmp/scene-replay-01`. It verifies retained files and the installed checker identity, runs the software tests and fixture suites, then compares the content and physics observations. New outputs go to a separate directory and leave retained reports unchanged.

The current replay uses explicit verification errors, including under `python -O`. It rejects missing replay cases, changed per-check outcomes, skipped or failed software tests, changed runtime identity and changed retained bytes. Physics comparisons require matching configurations, run counts, timesteps, decisions and finite recorded displacements. `verification.json` records the individual verification results; its combined success field is calculated from those checks. A successful replay establishes agreement with these retained controls, not independent correctness or production coverage.

`MANIFEST.json` covers the distributed files other than itself. `checker_sha256` identifies the runtime implementation. `original_files_sha256` and `portable_report_views` preserve the lineage of report copies whose local workspace prefixes were replaced for portability. Numeric observations and input artifacts were not changed. Internal hashes inside historical reports may identify their original copies; the distribution manifest identifies the published copies.

The initial GitHub release packaged the same 0.3.0 runtime as the earlier article companion. Its README, contribution instructions, project metadata and visual documentation are revised for a standalone repository. The prior archive's hash is retained in the manifest's `distribution_origin` field. The original archive remains unchanged.

The original manifest and replay script are preserved in `release-records/v0.3.0`. The top-level manifest identifies this checkout, including later additions. Existing fixtures and historical reports are preserved; the updated replay compares old decisions and per-check statuses, and reports new timing cases separately. Test counts come from the executed pytest report.

## Limits that matter when extending this project

The coordinating assistant helped author the briefs, evaluator and review. These are development tests, with no independent held-out evaluation or measured productivity gain. Full replay needs the optional dependencies and separately installed example pack. Skipped optional checks are not evaluated coverage.

The retained article probes used standalone image-decoding and MuJoCo experiments. The current package also exposes `textures.decode` and `physics.incline-worker` as selectable runtime packs. The image pack checks supplied image bytes; the physics pack runs its admitted block-and-ramp model with bounded parameter variations. The older article adapter still accepts only its frozen two-box fixtures. Neither physics route is a general USD-to-MuJoCo importer or evidence of physical calibration. No hardware or robot policy was tested.

## 0.5 replay policy

Changed packs have new versions. `reproduce.py` replays the retained scenes using separate input copies with explicit known-version upgrades; each copied bundle retains `contract-upgrades.json`. Unknown versions and implementation digest pins are preserved by the version upgrader, including the deliberately invalid controls. The older consolidation/declared-scope replay separately migrates its `fresh.brief` provider to the installed supplemental pack; its record includes that alias/digest change and the actual original contract hash. Original requirements, tolerances, scene bytes and historical results are not rewritten. A current replay is a new result under the identified implementation, not a claim that the old implementation produced it. The evaluator itself never upgrades contracts automatically.
