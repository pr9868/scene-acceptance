# Caller helpers

`check-3d-app identify --bundle-root DELIVERY --candidate scene.usda` returns canonical identity for the admitted file closure.

`check-3d-app preflight --bundle-root DELIVERY --candidate scene.usda --checks-file checks.json` inspects selected check prerequisites. The file contains an array of `id`, `pack`, `check`, `parameters` records. Legacy packs without callbacks report preflight unavailable.

`check-3d-app package-evidence --preparation PREPARED --expected-plan-sha256 HASH --view-spec views.json` accepts `{ "views": [...], "requests": { "capture-id": ["view-id"] } }`. Each view uses the public view schema with image path relative to this file; omit the generated `sha256`. Supply camera, projection, elapsed time, method, producer, capabilities, limitations, covered prims and view roles. The helper copies/hashes images, generates scene-bound `views.json` and `receipt.json`, and validates them. Missing mappings remain unavailable. Packaging authenticates no rendering or visibility assertion.

The same commands run through `scene_acceptance.application.invoke`; normal run history and output rules apply. `--max-prims` changes admission capacity only. It cannot clear unknown geometry or relax requirements.

Preparation readiness is separate from successful persistence. Inspect `readiness.ready_for_capture`, named blockers and `next_action`; unresolved proposals return exit 3. Optional `--plan-revision-attempts 1` or `2` permits bounded additional interpreter calls with deterministic feedback; zero is the default. Retain every attempt. Scope approval does not clear feasibility gaps. Use the public response schema in `model_protocol`, and bind semantic input, projected context and model/configuration identity for explicit replay. Replay is not fresh model evidence.
