# One tool-using Astra mechanical-assembly demonstration

Prepared 20 September 2026 before the producer run. The user chose “Animated mechanical assembly” to give readers a concrete visual example of agent-led production. The coordinating assistant supplies the detailed synthetic brief and assessment plan under that direction. This is a worked demonstration, not the independently supplied brief trial prepared for the harness project, a representative benchmark or a comparison across models.

## Question and claim boundary

Can one tool-using `gpt-6-astra` session turn the supplied crank-slider brief into editable USD, coherent material assignments, saved animation and an orbitable browser delivery? Retain evidence for what happened, including setup and unsuccessful tool commands. A successful example would support the feasibility of this particular workflow. It would not establish failure rate, general tool selection ability, economic savings, physical validity or a new model's capability relative to earlier models.

## Input and execution

Freeze `brief.txt` and the final environment description before generation. Record their hashes, exact CLI invocation, requested model identifier and reasoning level, CLI version, start/end time, raw JSONL events, stderr, final response and available usage. The backend snapshot is unknown unless the service reports it. The producer receives no previous scene, this article corpus, evaluator source or earlier trial responses.

The coordinator provisions a clean disposable workspace and documented tool installations. Tool availability is supplied context, not an autonomous discovery or installation claim. The agent can choose modeling and rendering tools, write scripts, export and inspect files, build a viewer and self-correct within one initial session. No coordinator edits to the scene or viewer count as agent work. Preserve the first submitted workspace before assessment. Allow at most one feedback attempt if a required delivery fails; freeze both submissions and the exact feedback. Report initial versus corrected results separately. Do not regenerate a successful submission merely to find a more flattering example. Initial runtime cap: 20 minutes; feedback cap: 12 minutes.

## Requirements fixed before inspection

1. Editable scene: USD opens with explicit positive metre scale, a valid time range representing four seconds and identifiable crank/link/slider/support geometry. Save source and rebuild instructions.
2. Materials: the named structure, metallic components, orange moving component and rubber feet have distinct resolved material assignments. Inspect actual viewer and rendered image for visually distinct surfaces; do not equate a shader binding with matched appearance across renderers.
3. Motion: a 35 mm crank radius and 110 mm rod pin spacing, a moving slider constrained to one line, a complete four-second revolution and matching loop endpoints. Read saved transforms at 0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5 and 4 seconds. Compare pin distance and straight-line motion within 0.5 mm. These finite samples do not certify every instant, collision clearance, tolerances, dynamics or manufacturability.
4. Delivery: local browser view loads the delivered model without runtime CDN calls, orbit changes the view, zoom works, play/pause changes animation state and the scrubber changes the pose. Inspect at desktop and mobile sizes. A GLB viewer must be labeled as such; do not call it direct USD playback.
5. Reusability: source/generator, named parts and recorded export files support inspection. Any import/export discrepancy, manual intervention or missing file stays visible.

## Evidence and acceptance

Freeze the submitted artifacts and retain SHA-256 identities before evaluating. Inspection scripts and browser checks are coordinator work, separate from producer self-checks. Use OpenUSD for scene readback and the installed harness only for its supported checks; do not widen its claimed support to fit the demonstration. Record additional semantic/kinematic measurements separately. Visual judgment is the coordinating assistant's assessment; the user's final viewing judgment is separate. Both agents and criteria come from the same coordinated exercise, so this is not independent validation.

Report requirements as observed pass, fail or unresolved with the measurement or reference. Preserve failures, export warnings, and unsupported harness input honestly. Distinguish final submitted outputs from preparation intermediates. A visual success alongside limited physical evidence is an expected possible outcome, not a reason to invent a defect or a hallucination.

## Editorial placement

Create a private demonstration page with the actual prompt, replay/orbit view, tool trace summary, artifact links and scoped result. The delegation article can use a concise visual example; the core harness article can link to the same evidence and explain acceptance. Draft updates remain private until publication is approved. Keep the original trials, four harness article assessments and public releases unchanged until this demonstration supplies a concrete reason for an edit.
