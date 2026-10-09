# Why did the high-friction block keep creeping?

The original two-box result is sensitive to solver settings. This follow-up keeps geometry, mass, gravity and friction fixed, then compares the original settings with `impratio=100` and ten `noslip` iterations. Each runs for five seconds at two time steps. “Settled” was defined before execution as an absolute fitted displacement slope of at most 0.01 mm/s during the last second. The original acceptance policy and retained results are unchanged.

| High-friction case | Final displacement, 2 ms step | Drift during last second | Meets this study's settled criterion? |
|---|---:|---:|---|
| Original solver settings | 4.516 mm | 0.8732 mm | No |
| `impratio=100` | 0.194 mm | 0.00873 mm | Yes |
| Ten `noslip` iterations | 0.164 mm | 0.000116 mm | Yes |

The 1 ms runs show the same pattern. The low-friction control keeps sliding under all three configurations and eventually travels beyond the ramp; its five-second displacement is not a contact-only friction measurement. No run reported a solver warning.

This supports a numerical explanation for much of the continuing creep in this particular model. It does not validate the material's physical friction or show that another solver will agree. The final displacements remain time-step dependent. The useful next step is to specify the solver, observation window and intended physical behavior before accepting a simulation result, rather than retuning friction until a check passes.

Run:

```sh
python evaluation/solver-drift-v1/run.py --out /tmp/new-solver-study
```

[Retained summary](results.json) contains all twelve runs, source hashes and dependency versions. The command retains the full trajectories for a fresh run. These are constructed controls, not measurements from a physical press or a process plant.
