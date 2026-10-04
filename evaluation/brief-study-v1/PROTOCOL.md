# Brief context and creation study — frozen before new production

2026-10-02. Owner requested text/image sample briefs, same-scene comparisons, repeated simple-versus-brief creation, and an optional CLI model reviewer. This is private development evidence, not a benchmark or publication.

## Questions and sequence

1. First assess an unchanged retained producer panel with no brief, a size-only brief, a matching reference-image brief, a different-image brief, and an explicitly conflicting brief. The altered briefs are counterfactual requirements, not corrections to the producer's historical assignment. Preserve originals and all first outcomes.
2. After that completes, create a new inspection-conveyor assembly in six fresh Astra calls: simple then detailed text+image, repeated three times. Each call starts with no prior response, evaluator output or repair feedback. Assess every delivery with the same default baseline, text brief, image brief and changed target brief. Do not select favorable trials or add defects to production outputs.
3. Trial order is interleaved, not randomized; temperature/seed and resolved model snapshot are unavailable. Request gpt-6-astra/high through the installed CLI. Three runs per arm are exploratory, not sufficient for a failure rate or causal claim. A brief supplied before creation may affect output; a brief supplied only at evaluation cannot alter scene bytes.
4. Production is a bounded, tool-disabled structured-output exercise: the model writes complete USDA text and an 8x8 palette raster. A deterministic delivery adapter saves the text unchanged and expands each raster cell to 8x8 pixels. It does not repair USD, dimensions, materials or motion. Common output conventions and named prim paths are supplied to both arms and are a confound relative to unconstrained prompting. No claim that this reproduces the original full tool-using Astra applications.

## Frozen task targets

Complexity here means a multi-part mechanical illustration (conveyor deck, 12 rollers, legs, guards, cabinet, signal tower, sensor, animated carton and textured warning panel), not a calibrated industrial digital twin.

- Conveyor deck world size 3.0 x 0.8 x 0.1 m, centre (0,0,0.8) m.
- Exactly 12 direct Cylinder children of /World/Rollers.
- Cabinet lies on positive Y, its nearest Y edge at least 0.9 m from the deck's positive-Y edge. This checks one axis-aligned gap, not walkability or safety compliance.
- Carton size 0.3 x 0.2 x 0.2 m at stage start.
- Authored duration 4 s at 24 time codes/s. Carton origin moves linearly from (-1.2,0,1.05) to (1.2,0,1.05) m, checked at 21 times with 1 mm tolerance. Continuous correctness remains unmapped.
- Warning image is 64x64 RGB, with yellow upper-left/lower-right and black other quadrants, as the supplied reference. Compare decoded source pixels exactly; this does not establish UV orientation or rendered appearance.
- Visually readable, credible assembly is a separately required qualitative obligation, left unresolved by the script checks.
- Dimensional and positional tolerance 1 mm; clock tolerance 1e-9 s. These are study policies disclosed in the briefs.

Changed-target condition uses a 1.4 m cabinet gap and reversed reference quadrants; it is deliberately a different assignment, not a producer defect against the original brief. Conflicting text/image instructions stay unresolved; the runner never silently chooses a winner.

## Implementation and verification

Add a bounded reusable measurement pack for named dimensions/centres, direct-child count, axis gap and reference-image pixels. Reuse installed timing checks and the existing 27-check baseline. A brief package contains text, images, source attribution and an explicit requirement-to-check map; natural language/image interpretation is not automatic. Report every requirement, checked subjects, pass/fail/unknown, source files/hashes, missing scope and exact comparisons. New checks must pass known positive/negative, missing-input, transformed/unit-scaled and coverage controls before production evaluation. Freeze checker and brief hashes before the first producer call. If an evaluator bug is found, retain the first results and record an amendment before reruns.

Optional model review is explicitly invoked by a caller-selected executable/configuration. Provide the same frozen brief plus selected evidence and image inputs; validate output shape, requirement/evidence IDs and snapshot identity. Keep raw request, response, model request, usage, errors and elapsed time. Model observations are advisory, cannot override script failures, approve a review obligation, certify engineering truth or count as measured asset passes. Unknowns and CLI failures stay visible. Test the adapter with deterministic controls and run a small live demonstration after the production results; same-family judge is not independent validation.

Keep all raw model outputs, failures, absent artifacts and unassessed items. No assumed model failures, always/never claims, hardware operation, existing app changes, Kitting material, publication or outside messaging.
