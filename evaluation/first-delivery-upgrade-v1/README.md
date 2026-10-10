# First-delivery usefulness: developer replay

The upgrade makes more of the original geometry measurable without rewriting a delivered scene. It also keeps unsupported subjects visible when another subject has a proven failure. These are developer regressions against three retained deliveries and constructed controls, not an independent accuracy study.

## Original deliveries

The original scenes were copied and hash-checked before and after evaluation. Check implementations were explicitly migrated to the new versions. Expected values and acceptance policy were unchanged in the middle column. Counts include the admission row; they count checks, not assets or unique requirements.

| Delivery | Earlier checks | New checks, original policy | Alternative declared policy |
|---|---|---|---|
| Conveyor | 10 pass, 12 unknown | 16 pass, 6 unknown | 22 pass |
| Process skid | 6 pass, 1 fail, 2 unknown | 6 pass, 3 fail | 9 pass |
| Rack and AGV | 9 pass, 5 unknown | 9 pass, 3 fail, 2 unknown | 14 pass |

The last column explicitly selects surface geometry, allows boundary contact and supplies a 1 mm physical boundary allowance. The skid also declares `bidir` as an alias for `bidirectional`. These are proposed policy changes, not approved replacements or producer repairs. Intermediate variants without the boundary allowance are retained in [summary.json](summary.json).

A failed check can contain unresolved subjects. Under original policy, each conveyor zone measures 17 of 18 named obstacles and each skid zone 21 of 22. The rack aisle checks measure 126 of 126 each; each rack load-height check measures 18 of 36 because the remaining wrapping is open geometry under a solid-volume policy. The report retains those denominators.

## What the controls show

Sixteen replay runs cover original and repaired deliveries, seeded faults, unsupported skinning and two admission budgets. Known timing, route-state, material, source-image and aisle-intrusion failures remain reported. Lowered-duct intrusions that were previously obscured by unsupported subjects now produce three failed zone checks while preserving the unresolved subjects.

One earlier failure changes intentionally: a missing sign image used to fail the unrelated belt-material check. The new material check follows only the selected network. The belt passes, while admission identifies the missing sign file and the image check remains unknown. The delivery is still blocked. A selected sign-material check reports a missing connected image as a failure; this attribution is covered by the public regression test.

The mirrored-UV control is still missed by source-image comparison. The unlisted carton is still missed by the old explicit object list. Neither result is presented as complete scene acceptance. A separate, retrospective subtree-selector trial includes the carton and 26 rack posts in its failures. A proposed amendment exempting rack-frame subtrees assesses 721 objects: 720 pass and only the stray carton fails. These exemptions need owner review. Subject discovery cannot decide what “load height” means for the job.

The declared engagement check catches a preserved **185 mm gap** in a lift-bar assembly. The repaired scene has **215 mm minimum projected overlap** over the same 16-second interval. This is one relationship over nine affine-motion knots, chosen after the gap was known. It is neither automatic assumption discovery nor proof of physical joint function.

## Runtime on one retained workload

Same host and dependencies, three separate-process first calls plus three warm repetitions per implementation. “First call” does not mean an empty operating-system cache. Other light desktop work occurred during measurement.

| Workload | Earlier median first call | New median first call | Earlier / new warm median | Outcome |
|---|---:|---:|---:|---|
| General checks | 5.56 s | 6.02 s | 5.23 / 5.46 s | Same 28 passing rows |
| Five clearance checks on the repaired rack scene | 135.00 s | 2.31 s | 134.47 / 2.14 s | Same five passing checks plus admission |

The clearance improvement comes from conservative separation and early proven-intersection handling. This is a workload result, not a general throughput claim. Exact ranges and process peak memory are in the summary. General-check overhead increased about 8%; it stayed within the preselected 20% comparison limit.

## Public reproduction and remaining evidence

Run the deterministic conformance and caller-protocol tests from a configured checkout:

```sh
python -m pytest -q tests/test_usefulness.py tests/test_caller_tools.py
```

`reproduce.py` additionally exercises the complete software suite and the earlier packaged studies. The original delivery packets are not distributed here; the public JSON is a sanitized aggregate, not a complete replay of those scenes. Numerical controls are developer-authored. Independent holdouts, human-labelled model calibration, fresh visual-review comparisons and measured reviewer-time savings remain pending.

See [supported behavior and caller examples](../../docs/USEFULNESS_UPGRADE.md) before selecting geometry or contact policy.
