---
name: scene-harness-judge-authoring
description: Customize or extend the scene-acceptance harness's optional LLM/VLM judge criteria, evidence expectations and adopter integration. Use when an application needs a versioned review rubric, additional visual questions or a tested new evidence/check adapter.
---

# Author a scene judge profile

Read [the extension guide](references/extensions.md) and [the example rubric](references/rubric.json). Make changes in the adopter's own copy. The harness ships a default rubric; customization is explicit input, not a replacement of core safety or evidence rules.

1. Establish the intended use and the observed issue the new criterion should detect. Separate what the user asked for from the application's default review policy. Do not introduce undeclared engineering acceptance limits.
2. Choose the extension level: change/add a rubric criterion, change a capture expectation, add a measurement pack, or implement a new evidence adapter. Use existing supported evidence kinds when adequate. A skill or prompt cannot implement a missing measurement or validator.
3. Write focused observable questions with stable IDs, a profile ID/version, an area, evidence kind and limitations. Visual review uses `scene_view`, `textured_view` or `motion_frames`. Default presets disclose unassessed areas; preserve that distinction from missing evidence for a required criterion. Custom/brief physics requests remain unknown until an actual evidence adapter supports them. Use a brief for task-specific obligations. Numerical measurements stay script-based; exact dimensions should not be estimated from pictures.
4. Require appropriate caller-provided views and map them through the preparation/capture receipt workflow. Declare a view role, nullable exact camera/projection constraints and null sharing group unless one image explicitly serves both requests. State whether the question needs a close-up, more than one angle, material fidelity or particular motion events. Missing adequate evidence must remain unknown. Do not make “looks plausible” a physics certificate.
5. Test the revised profile with a visible discrepancy, a matching example, missing/wrong evidence and an ambiguous example. Test front/rear requests with one reused image; they must not qualify. For motion, include repeated timestamps and mismatched cameras. For texture, include geometry-only images. Check that a contrary model opinion cannot clear a scripted failure. Label synthetic test doubles separately from real model reviews.
6. Save the profile, changes, source of expectations, evidence examples and limitations. Increment its version when questions or expectations change. Re-prepare to freeze the new profile; compare old/new interpreted scope and retain both reports. A rebound scene may introduce material or motion areas missing from the frozen rubric. Treat `judge_coverage_drift` as a request to prepare and review additional scope, not permission to change the approved rubric in place.

Scope approval also binds the general policy and selected pack identities; an upgrade that changes those requires approval of the new scope hash. Report measured results and advisory opinions separately.

For new code adapters, validate schemas, bounded inputs, source hashes, eligibility rules, unknown/error behavior and regression tests before making new evidence kinds selectable. Never let a model response select an executable, install a pack, use a GPU, change approval status or treat an image hash as proof of rendered truth.

## Optional assumption triage

When the caller requests AI help deciding which declared decisions need human review, read [the triage handoff](references/triage.md). This is a separate text-based operation after declared-scope assessment. It does not add a visual question, discover hidden assumptions or supply approval. Use caller-owned policy and preserve the distinction between the AI recommendation and the applied gate.

## Experimental assumption audit

Use the separate `audit` operation only when the caller requests questions about undeclared choices. Read [the audit guide](references/audit.md). Audit can compare the brief, saved scene inventory, declared decisions, pinned scripted results and supplied views. Its output is a cited question for a person, never a measured failure or approval. Preserve missing-evidence disclosures and label synthetic controls separately from measured model discovery.
