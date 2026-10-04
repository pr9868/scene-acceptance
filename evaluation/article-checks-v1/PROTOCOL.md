# Harness follow-ups: evidence plan

Recorded before implementation and execution, September 23, 2026. User selected three new harness follow-ups and explicitly asked for strong evidence. GPU access is available; these particular measurements need no GPU. New work stays private for review.

## Provenance and scope

Base: scene-acceptance commit `33e5721`, copied into the learning notebook's `projects/harness-followups-20260923`. The canonical repository and published v0.3.0 are unchanged. New checks use the existing explicit pack API. The coding assistant proposes and implements the bounded protocols, creates constructed fixtures, runs the experiments and drafts the interpretation under Pradeep's direction. These are development controls, not an independent benchmark or new agent-production trial. No measured friction data or external evaluator is available.

Retain inputs, source hashes, versions, protocol, raw observations, expected and actual outcomes, first failures and later corrections. Freeze fixture hashes before running. Repeat the final matrix without changing those fixtures. Keep timed-out and invalid worker results distinct from a measured task failure. Do not claim continuous motion coverage or measured physical validity.

## 1. When a delivered texture cannot be read

Reader decision: whether to add a required decode check before handing a texture to a viewer. Existing material delivery only checks binding and file presence. Simplest alternative: a direct Pillow verify/load script, which should agree on supported images. The new contribution is integration and evidence accounting, not a new decoder.

Controls: valid PNG/JPEG; plain text named PNG; identifiable but damaged PNG; valid wrong-color PNG; GIF and animated PNG outside scope; a pixel-budget excess; missing dependency; an advisory-only corrupt decode. Keep scene bytes identical where only the texture bytes change. Report actual image format, dimensions, input hash and decode result. Explicitly selected static texture attributes, PNG/JPEG and bounded dimensions only.

Continue if intact supported images pass, corrupt supported images block required acceptance, unavailable/unsupported evidence does not become a pass, and advisory failures remain visible. Stop and fix the check if these fail. A wrong-color image is expected to pass: decoding does not establish appearance.

## 2. A pin can separate while both origins look right

Reader decision: what relationship to measure and how to choose sample times. Compare origin-only and endpoint checks with two transformed local points and a declared sampling schedule. Construct a 35 mm rotating arm crossing 360 degrees, plus a follower at the intended pin position. Wrapped scalar interpolation should produce a large interior gap; the unwrapped version should stay within 0.5 mm. Compare USD read-back with a separately expressed trigonometric calculation.

Add a brief authored excursion located between uniform samples. Compare uniform samples with a schedule that also includes relevant ancestor transform keys and interval midpoints. Retain a counterexample where even that finite schedule passes while a denser diagnostic scan finds a gap. Check millimetre units, inherited transforms, missing clock and intervals outside coverage. A denser scan is diagnostic, not continuous proof. Stop if the implementation reports global interval safety.

## 3. A simulation result has to belong to the job

Reader decision: how to use an external simulation result in acceptance without treating execution failures or stale results as physical failures. Reuse the published two-box incline and CPU MuJoCo adapter, preserving its limitations. Compare direct execution and a subprocess with fixed trusted code, copied inputs, an explicit timeout, bounded steps and output, and verified input/job identity. Keep friction assumptions visible.

Run high/low friction at 1 ms and 0.5 ms for one simulated second. Recompute maximum displacement from CSV and compare with the direct runner and an ideal Coulomb diagnostic calculation. Fault controls: timeout, crash, malformed or oversized result, wrong input identity, inconsistent metric, unsupported scene and missing required provenance. These controls test orchestration, not simulator accuracy. The subprocess is not a hostile-code sandbox; no arbitrary scripts or user-supplied executable paths. No GPU claim and no physical validation claim.

## Initial article-value assessments

| Proposed article | Reader problem | Judgment and reason | Evidence | Useful outcome | Initial verdict |
|---|---|---|---|---|---|
| Required texture decoding | Evidenced: published material article's unreadable-file gap | Partial: decoder limits and explicit selection need implementation | Missing: new integrated run | Partial: runnable contract planned | Strengthen |
| Checking a moving connection | Evidenced: published motion/assembly sampling gap | Partial: relationship plus schedule comparison planned | Missing: new pin read-back and falsification | Partial: schedule procedure planned | Strengthen |
| Accepting a simulation result | Evidenced: published physics runner is separate from acceptance | Partial: job identity and failure classification planned | Missing: worker integration and injected faults | Partial: result protocol planned | Strengthen |

The closest siblings remain the published materials, motion and physics articles respectively. Each new draft must show its own integration result and counterexample. A green regression total alone is insufficient. Final per-article assessment will reference the completed evidence and article passages.
