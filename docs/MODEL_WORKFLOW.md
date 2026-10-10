# From a saved plan to usable evidence

A successful `prepare` call means a proposal was saved. It does not mean the caller can render everything requested or that every check can measure its targets.

Read these fields before starting capture:

| Field | What the application should do |
|---|---|
| `data.readiness.ready_for_capture` | Proceed to scope review and capture only when true. This is prerequisite readiness, not an acceptance decision. |
| `data.readiness.blockers` | Route named check prerequisites, capture gaps and unresolved requirements to the right owner. |
| `data.next_action` | `revise_preparation` means address those blockers; `review_scope_then_capture` means the proposal can proceed. |
| `data.readiness.checks_without_preflight` | These providers do not advertise prerequisite checks. Their outcome is still unknown until evaluated. |

An unresolved plan is retained with `status: completed`, **exit 3** and its blockers. Exit 0 means no known preparation blocker; it does not approve the scope. This also applies when capture capabilities were omitted. `bind` recomputes readiness for the new delivery, including `judge_scope` blockers when new motion or materials lack a frozen review question. That requires a new preparation; approving the old scope cannot add coverage. Checks-only diagnostics can still run. An owner may approve the intended requirements while execution remains unresolved: scope approval does not manufacture missing geometry or evidence.

## Optional, bounded plan revision

```sh
check-3d-app prepare --bundle-root delivery --candidate scene.usda \
  --raw-brief brief.json --interpreter-config caller/interpreter.json \
  --capture-capabilities caller/caps.json --plan-revision-attempts 1 \
  --out prepared
```

The default is zero additional interpreter calls. Set one or two only when you want that bounded extra work. That is an initial interpretation plus at most the requested number of additional calls. The adapter's per-request budgets still apply. Each attempt receives the prior interpretation, deterministic prerequisite results and capture budget after caller capture overrides. The final plan uses the same override and feasibility logic. Calls stop when ready, when the attempt limit is reached or when a response fails validation. The last valid proposal remains saved if a revision fails; inspect `revision-attempts.json` and the retained model logs.

This revision path is deliberately narrow:

- A single aggregate obstacle can become a selector for **all geometric descendants of that exact root**. No exclusions are introduced.
- A model can propose sharing compatible captures and fill unspecified camera metadata. Existing framing instructions, camera IDs and projections cannot change. Every capture ID, target, timestamp, capability and minimum resolution remains required. Sharing is still subject to owner scope review and actual view suitability.
- Requirement IDs, statements, sources, quotes, routes, check types and policy remain fixed. Changing a solid requirement to surfaces, adding a 1 mm allowance, dropping an object or removing a capture is rejected.

For a real change in requirements or delivery policy, make a new preparation and review its scope. A limited revision cannot resolve an ambiguous brief, invent a tolerance or silently accept less evidence. It also cannot repair geometry or prove that shared framing will show every target clearly.

## Compact model context without false reference errors

Large inventory lists are bounded in the model prompt. Audit and interpreter reference validation still use the complete admitted prim set. A valid part cited by a supplied declaration remains valid even if it falls beyond the prompt's inventory limit. This does not tell the model what omitted parts look like or restore truncated measurements as usable evidence.

Audit errors name the declaration or question, unknown evidence IDs and unknown prim paths. Declarations must still match the current scene revision. A model cannot add an object to the trusted inventory by naming it.

## Adapters and older checklists

The [public adapter example](../examples/json-cli-adapter/README.md) reads the response schema from the request and distinguishes the exact transport hash from semantic and projected-context identities. Model/configuration identity also matters for replay. A replay is labelled and never counts as a fresh model test.

Evaluation continues to reject mismatched pack versions. The error points to an explicit proposal command:

```sh
python -m scene_acceptance.contract_upgrade \
  --contract caller/contract.json --out caller/upgrade-proposal
```

Review `upgrade.json` and the proposed contract before adopting it. The command does not approve changed behavior, replace an implementation pin, change tolerances or edit the original contract.
