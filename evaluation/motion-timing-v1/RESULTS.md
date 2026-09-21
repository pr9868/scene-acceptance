# Motion timing results

Harness 0.4.0 development, `motion.timing` 1.0.0. Python 3.12 and OpenUSD 25.11 on macOS arm64, 20 September 2026.

All 17 frozen controls matched their recorded expectations on the first run. The initial 27 dedicated software tests passed. Review then identified and corrected handling of absent/non-transformable targets, adding two controls that require a rejection rather than an evaluator error. The final set has 29 timing software tests, including fractional-clock rescaling, shifted starts, stage-unit conversion and the original time-code-only contract. The full final replay covers 224 software tests. Counts overlap.

| Case | Clock result | Position result | Overall |
|---|---|---|---|
| `correct` | Pass: 2 s | Pass | Accept |
| `clock_rate_changed` | Fail: about 0.083 s instead of 2 s | Unresolved prerequisite | Reject |
| `rescaled_24` | Pass: 2 s | Pass at time codes 0, 24, 48 | Accept |
| `shifted_start` | Pass: 2 s | Pass at time codes 120, 144, 168 | Accept |
| `padded_fast_motion` | Pass: 2 s | Fail at one elapsed second | Reject |
| `wrong_position` | Pass | Fail | Reject |
| Missing/invalid clock or range | Unresolved | Unresolved prerequisite | Insufficient evidence |

The [final full replay](evidence/final-full-replay.json) verifies 224 software tests, 17 timing cases, the unchanged legacy decisions and the existing content/physics observations.

The complete [first-run summary](runs/first/summary.json) and per-case reports include the additional required-rate, duration, missing-unit and invalid-instruction cases. [Input hashes](fixtures/manifest.json) were frozen before evaluation. No previous fixture or expected result was altered.

The retained 22 pack cases and 32 mesh cases preserved their verdicts and individual check statuses. [Comparison record](evidence/legacy-comparison.json). Existing contracts still select `motion` 1.0.0 when they intend time-code-only comparisons; the new timing pack is selected explicitly.

The clock check measures the authored stage interval. Positions measure the named origin at selected elapsed seconds. Neither proves continuous motion, actual time spent moving, collision freedom or physical behavior. These are constructed development tests, not agent samples, independent validation or a measured workflow improvement.
