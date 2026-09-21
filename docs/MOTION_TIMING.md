# Require seconds as well as positions

The original `motion` 1.0.0 pack checks positions at explicit USD time codes. It records `timeCodesPerSecond` but cannot require a rate or duration. Changing the passing fixture from one to 24 time codes per second still satisfies that contract, although its 0–2 interval now spans about 0.083 seconds.

Harness 0.4.0 adds `motion.timing` 1.0.0 without changing the original pack's contract. It supplies two checks:

| Check | Requirement | Boundary |
|---|---|---|
| `clock` | `duration_s` with `tolerance_s`; optional exact `time_codes_per_second`. | Checks the authored stage interval, not how long an object actively moves. |
| `positions` | `path`, `tolerance_m`, and `samples` containing `elapsed_s` and `world_origin_m`. | Samples elapsed seconds from the authored stage start. No continuous path, orientation, collision or dynamics claim. |

Both require authored `timeCodesPerSecond`, start and end time codes. Missing or non-finite metadata, a non-positive rate or reversed range returns unresolved evidence. The new pack deliberately does not accept an implicit fallback clock. A valid clock that contradicts a required duration or rate fails.

Use positions together with duration when the brief requires both. Increasing the declared end time can make the duration pass while leaving the object at the wrong position halfway through.

## Configure a two-second panel move

The full [correct contract](../evaluation/motion-timing-v1/fixtures/correct/contract.json) pins `motion.timing` to `1.0.0` and selects:

```json
[
  {
    "id": "motion.clock",
    "pack": "motion.timing",
    "check": "clock",
    "parameters": {"duration_s": 2, "tolerance_s": 1e-9},
    "required": true
  },
  {
    "id": "motion.seconds",
    "pack": "motion.timing",
    "check": "positions",
    "parameters": {
      "path": "/World/Panel",
      "tolerance_m": 1e-6,
      "samples": [
        {"elapsed_s": 0, "world_origin_m": [0, 0, 0]},
        {"elapsed_s": 1, "world_origin_m": [0.5, 0, 0]},
        {"elapsed_s": 2, "world_origin_m": [1, 0, 0]}
      ]
    },
    "required": true,
    "after": ["motion.clock"]
  }
]
```

These are the full contract's `checks`, not a standalone contract. The small tolerances belong to exact constructed coordinates; choose tolerances for the consuming task when adapting them. There is no expected rate in this example, so the producer can choose a different valid clock if it preserves the requested seconds. A consumer requiring exactly 24 time codes per second can add `"time_codes_per_second": 24` to the clock parameters.

Conversion is `startTimeCode + elapsed_s × timeCodesPerSecond`. The origin is the authored start, including when that start is nonzero. Out-of-range seconds remain unresolved; unordered or schema-invalid sample instructions produce an evaluation error. Unit conversion still uses the authored `metersPerUnit` through the existing position evaluator.

## Run the controls

Use the [README installation](../README.md#try-a-passing-edit-and-a-rejected-edit) for the 0.4.0 development branch. From that checkout:

```bash
check-3d --bundle-root evaluation/motion-timing-v1/fixtures/correct \
  --contract contract.json --candidate scene.usda --out /tmp/timing-correct-01

check-3d --bundle-root evaluation/motion-timing-v1/fixtures/clock_rate_changed \
  --contract contract.json --candidate scene.usda --out /tmp/timing-rate-01

check-3d --bundle-root evaluation/motion-timing-v1/fixtures/rescaled_24 \
  --contract contract.json --candidate scene.usda --out /tmp/timing-rescaled-01
```

Expected decisions are accept, reject and accept. Each output path must be new. In the rejected case, `motion.clock` reports about 0.083 seconds against 2 seconds; the dependent position check remains unresolved. Application code owns whether to request another producer attempt.

The `padded_fast_motion` fixture has a two-second stage interval but retains the early keyframes. Its clock passes and its position at one elapsed second fails. This control prevents the article from treating a metadata-only duration check as proof of the requested motion.

```bash
python evaluation/motion-timing-v1/run.py --out /tmp/timing-suite-01
```

The [17-case record](../evaluation/motion-timing-v1/RESULTS.md) includes missing clocks, invalid ranges, conflicting rates, wrong positions and invalid instructions. Additional software tests cover fractional rates, nonzero starts, unit conversion and the old contract's unchanged meaning.

## What the fix establishes

Adding this pack makes the selected duration and seconds-based samples explicit acceptance requirements. It does not infer missing brief requirements or establish motion between samples. Producer prechecks and application acceptance can use the same contract, but both would share a defect in its requirements or evaluator. The [producer-trial protocol](../evaluation/producer-trial-v1/PROTOCOL.md) describes the separate test still needed for workflow usefulness.
