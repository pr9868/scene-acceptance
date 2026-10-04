# Coverage and reporting development plan

Owner request: each run must explain what was checked, what passed or failed, how many things were assessed, and what remains unassessed. This records the development plan implemented in release 0.5.0. Original audit inputs and first results remain unchanged.

## Contract

- Retain exact per-check contract verdicts. Report check counts separately from object, file, connection and sample counts. Never add counts with different units or call repeated observations independent defects.
- Record scene inventory separately from evaluated subjects. A discovered mesh is not evidence that every rule assessed it.
- Capture observed provider callbacks for the seven pinned NVIDIA rules; expose skips, warnings and object locations. Native OpenUSD stage invocations have stage denominators, not invented object pass counts.
- Show no applicable subjects, unmeasured scope, missing evidence, errors, and unselected domains explicitly. A green structural scope is not acceptance of appearance, motion intent or physical behavior.
- Include installed article checks (texture decoder, sampled connection, bounded simulation worker) with optional dependencies. Explicit contracts select connections and behavior; a reusable baseline can discover file/image dependencies and inspect authored transform samples without inventing intent.
- Export self-contained HTML, JSON, Markdown and CSV summaries with full evidence pointers and revision hashes. Keep large observations outside the initial HTML view.

## Verification

| Area | Verification | Required examples |
|---|---|---|
| Reporting counts | Integration and regression | Mixed pass/fail/warning; duplicate findings; no meshes; provider skips; interrupted check; no denominator |
| Article checks | Retained controls + real worker faults | Corrupt/readable-wrong image; separated connection; sparse sampling; timeout/stale evidence; missing measurement |
| Baseline | End-to-end fixtures | Clean and defective geometry; no textures; unsupported image; animation with/without task requirements |
| Integrity | Regression + saved-scene replay | Immutable input hashes; exact evidence pointers; escaped HTML/CSV; read-only original Astra bundles |
| Installation | Wheel smoke test | Pack discovery and worker execution from installed source, with optional dependencies explicit |

The broader scene replay is a new reporting run, not a replacement of the frozen October 2 audit. Task intent, continuous motion, general physics adapters, rendered appearance and physical calibration remain open unless specific checks supply evidence.
