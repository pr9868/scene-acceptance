# Calling the harness from an application

Use `check-3d-app` or `scene_acceptance.application.invoke` for a versioned application boundary. The older `check-3d` contract/profile interfaces remain compatible. There is no HTTP server, renderer or GPU allocation in this package.

| Operation | Caller supplies | Harness returns |
|---|---|---|
| `doctor` | Optional scene and model configuration | Provider versions, format/feature limits, admitted scene identity, configured modality and resource limits; no model call |
| `prepare` | Saved local USD, optional raw text/image brief and interpreter configuration, capture capability declaration | Frozen requirements, source anchors, script mapping, requested views, scene/plan/scope hashes; a proposed mapping |
| `approve` | Expected scope hash, reviewer, reason and decision | Separate caller-owned approval record; no modification of the plan |
| `bind` | Existing scope hash and revised saved scene | New scene binding with identical requirements and source references, refreshed feasibility gaps; no interpretation call |
| `validate-evidence` | Frozen plan and paired view manifest/receipt | Supplied/missing/invalid capture matrix and eligible evidence IDs; no model call |
| `evaluate` | Frozen plan, optional scope approval, mode, evidence and judge configuration | Script outcomes, subject counts, advisory findings, missing evidence and next actions |
| `check` | Saved scene, optional already mapped brief, mode | Direct evaluation without preparation; the same application envelope |
| `resolve-triage` | Pinned original triage run and caller-owned human review record | Current human decisions applied to triage requests, with original checks preserved; no model call |
| `triage` | Pinned declared-scope assessment, original input roots, selected items, caller policy, text evidence and model configuration | AI review recommendations beside applied policy, original verdicts and next actions; no new approval |

`checks` is the default. `judge` selects advisory review only. `both` retains separate component results, withholding script findings from the judge by default. A malformed image manifest or failing model does not discard completed script results. The overall operation returns code 4 for that partial execution; inspect `data.script` or the prepared report to retain measured failures.

The separate, opt-in [assumption-triage operation](ASSUMPTION_TRIAGE.md) runs after declared-scope assessment. It uses text evidence and caller-selected items, preserves existing required reviews and failures, and does not change the `checks`/`judge`/`both` modes.

## Minimal calls

```sh
check-3d-app doctor --bundle-root ./scene --candidate scene.usda
check-3d-app check --bundle-root ./scene --candidate scene.usda --out ./baseline

check-3d-app prepare --bundle-root ./scene --candidate scene.usda \
  --raw-brief brief.json --interpreter-config ./interpreter.json \
  --capture-capabilities ./caps.json --review-profile static-visual --out ./prepared

# After the caller has reviewed the proposed scope:
check-3d-app approve --preparation ./prepared --expected-scope-sha256 SCOPE_HASH \
  --reviewer "Application reviewer" --reason "Compared mapping with supplied brief" --out ./approval.json

# Caller renders and returns the requested evidence.
check-3d-app validate-evidence --preparation ./prepared \
  --views ./captures/views.json --receipt ./captures/receipt.json --out ./evidence-check

check-3d-app evaluate --preparation ./prepared --expected-plan-sha256 PLAN_HASH \
  --approval ./approval.json --mode both --judge-config ./judge.json \
  --views ./captures/views.json --receipt ./captures/receipt.json --out ./run

# Test a repair against unchanged requirements, without asking the interpreter again:
check-3d-app bind --preparation ./prepared --expected-scope-sha256 SCOPE_HASH \
  --bundle-root ./repaired-scene --candidate scene.usda --out ./rebound
check-3d-app evaluate --preparation ./rebound --approval ./approval.json \
  --previous-run ./run --out ./repair-check
```

The convenience commands `check-3d-prepare`, `check-3d-approve`, `check-3d-bind`, `check-3d-evidence`, `check-3d-run-plan`, `check-3d-triage` and `check-3d-doctor` use this envelope too. This replaces the earlier development-only prepare/run summaries; application callers must read `data`. Existing direct `check-3d` output is unchanged.

## Response and control contract

Every application-command invocation, including argument and missing-file errors, returns one JSON object on stdout:

```json
{
  "schema_version": "1.0", "operation": "evaluate", "run_id": "unique-run-id",
  "status": "completed", "exit_code": 2, "reused": false,
  "data": {"decision": "REJECT"},
  "errors": [], "events": []
}
```

This abbreviated example shows a successfully executed rejection. Full schemas are in `check-3d --capabilities` under `application_schemas` and packaged `schemas/*-v1.schema.json`. `data` is the operation-specific object. Status describes execution: completed, partial, failed, cancelled or timed_out. Codes are 0 scoped success, 2 rejection, 3 review/evidence gap, 4 invalid input/execution/cancellation. Never treat code 3, an unknown opinion, or an unassessed check as a pass.

Errors contain code, phase, message and retryable. That field permits a fresh attempt; it does not promise an unchanged model response or automatically trigger retries. Reports and partial attempts stay on disk. Model/provider diagnostics go to stderr or retained logs.

All operations accept:
- `--progress`: JSONL phase events on stderr. Native USD diagnostics may also appear there; parse JSON lines and retain other lines as diagnostics.
- `--deadline-seconds N`: cooperative operation deadline, polled during model execution and between scripted checks.
- `--cancel-file PATH`: creating that file requests cancellation.
- `--reuse-completed`: directory-output operations may reuse a completed invocation only after checking runtime/environment, selected input identities and every retained output hash. Use it on the initial call to save a replay fingerprint. Changed inputs, modified outputs and partial/failed runs cannot be reused.

SIGINT/SIGTERM stop the owned adapter process group on POSIX. A hard kill cannot run cleanup. Native validators are not preempted inside a single call; the deadline is observed at checkpoints. Generic adapters must keep descendants in their process group. Windows only guarantees direct-child termination. A caller needing a hard wall-clock limit for all native operations should supervise the harness process tree.

Python uses the same boundary:

```python
from scene_acceptance.application import invoke
from scene_acceptance.execution import RunControl

response = invoke(
    "evaluate", preparation="/data/prepared", out="/data/new-run",
    mode="checks", reuse_completed=True,
    control=RunControl(deadline_seconds=120, progress=on_progress),
)
```

An application can keep `RunControl` and set `cancelled = True`. In a worker thread, handlers are not installed; cancellation/deadline checkpoints still apply. The lower-level library functions remain available for callers who prefer native exceptions.

## Scope, review and revisions

`scope_sha256` identifies requirements, source material, review rubric, capture expectations and `evaluation_policy` independently of a candidate. That policy includes the complete general baseline and resolved pack versions/implementation digests, including each pack's recorded dependency identity. `plan_sha256` identifies their binding to a specific scene, capture capabilities, runtime and dependency environment. Approval records pin the scope, so they can survive an ordinary repair; evidence receipts pin the plan and scene, so captures must be supplied for the new revision.

Scope approval means the mapping reflects the intended tests. It does not approve their outcome. Visual/unresolved requirements remain pending in scripted scope reports until a caller supplies a separate snapshot-bound outcome review using `--review-record` (the existing declared-scope review schema). A judge cannot produce human approval. Reviewer names are recorded, not authenticated; authorization belongs to the calling application.

`--previous-run` compares stable finding IDs and scope hashes. Checks absent from the new run are marked unassessed, not fixed. Advisory consistency is never reported as a measured repair. Each finding includes a next action: repair_scene, provide_evidence, review_specification, review_finding or fix_environment, plus available parameters, observations, evidence pointers and subject counts.

Changed brief/rubric/capture requirements require a new preparation and new scope review. Binding preserves existing target paths and sample times even when the revised scene lacks them. It does not relax expectations to fit the revision.

Runtime and provider identity are pinned. After an intentional upgrade, `bind --migrate-runtime --reviewer … --reason …` creates an audited binding with both environment identities. If the evaluation policy is unchanged, the scope hash is preserved. If general requirements or selected pack identities changed, binding creates a **new scope hash** and records added, removed and changed checks/packs in `binding.policy_changes`. The previous approval no longer matches. Review that difference and approve the returned new scope hash; without that approval an otherwise passing run returns `NEEDS_REVIEW`. Ordinary repairs made after that migration still require the new approval.

Migration does not certify numerical equivalence. Replay relevant known cases before using the migrated binding for acceptance. Older development packets without an independent scope or without its `evaluation_policy` require a new preparation and scope review. Their historical results remain valid records of the earlier evaluator; they cannot be silently treated as approval of this policy.

## Evidence, profiles and resource budgets

Each capture request declares a `view_role` (front, rear, overview, detail, etc.), optional exact `camera_id`/`projection`, framing guidance, targets, times, resolution and capabilities. Returned views declare `view_roles`. Identical image bytes cannot serve distinct requests unless those requests explicitly share the same non-null `sharing_group` and role. General overview criteria intentionally share an overview image when all other requirements are met.

Metadata eligibility is not proof of camera truth, visibility or renderer fidelity. Different bytes are not proof of different views. A VLM must still assess what is actually visible and leave ambiguity unknown. The harness does not render.

The default `general` review uses preset version `2.0.0`: layout/readability, material use when materials or shaders are authored, and motion when time-sampled attributes are authored. Unsupported physical validation and other excluded preset areas are reported in `judge.unassessed_areas` and the HTML as unassessed, not passes. Selection uses inventory, not favourable findings. `static-visual` explicitly selects layout/readability/materials; `animated-visual` also selects motion. A custom rubric is kept as supplied. Explicit brief/custom requirements remain required even when evidence is unavailable: asking for physical validation still yields unknown and requires review.

The automatic interpreter selects the bounded types exposed by `check-3d --capabilities`: geometry and layer policy, state and connection checks, process connectivity, timing, materials and source-image comparisons. External-engine jobs and arbitrary code are never generated from a model response. Unsupported intent stays visible and the owner must review the scope.

The default dependency budget is 64 files; `--max-dependency-files` allows 1–1024 through preparation, binding and evaluation. Visual reference images accept single-frame RGB/RGBA PNG/JPEG, up to 8 MiB and 16 million pixels each, with 32 MiB total reference bytes. Views have the same per-image limits and a separate 32 MiB view total; the combined reference/view count is at most twelve. Exact source-pixel comparisons retain a separate 1 MiB/262,144-pixel RGB decoder limit. See [brief image policy](BRIEFS_AND_MODEL_REVIEW.md#comparison-regions-and-image-policy). Install `scene-acceptance[visual,nvidia]` for image evidence plus baseline providers, without requiring the physics extras.

The optional two-box simulation pack verifies the installed worker, adapter and fixed-profile hashes before and after its subprocess, checks returned identities, then validates the trajectory and compares it with the requirement. It remains a bounded CPU experiment, not a general USD simulator or a hostile-code sandbox.

Model configurations optionally declare `modalities`, `max_model_calls` (0 or 1 per operation), `max_request_bytes` and `max_output_bytes`, alongside the required timeout. A text-only declared adapter cannot receive images. If no requested criterion has eligible evidence, the judge returns deterministic unknowns without invoking a model. Provider-reported usage is saved. Hard token/spend limits and truth of the declared modalities belong to the configured provider; this package does not pretend to enforce them through every external CLI.

Verified replay hashes the executable and explicit file arguments, not a generic adapter's entire service or software dependency graph. Remote model snapshots are not independently pinned. Cache reuse reuses the recorded opinion; a fresh output directory requests a fresh opinion.

## Scope rejection and coverage changes

Prepared results include a primary `next_action`. A rejected or still-pending scope approval returns `NEEDS_REVIEW` / exit 3 and `review_specification`; the finding retains the reviewer and reason. Measured failures remain in `script_verdict` and the per-check rows. Execution errors take precedence with exit 4 and `fix_environment`. Legacy `check-3d` also uses 4 for malformed CLI arguments; scene rejection remains 2.

Repair binding preserves the approved rubric but reports `binding.judge_coverage_drift` against the original preparation inventory. Newly applicable material or motion areas missing from that rubric block judge/both acceptance and request fresh preparation. Approving the old scope cannot add the missing questions. Checks-only runs expose the omitted visual scope without changing the numerical verdict.

For a renderer-supplied library, use the explicit [runtime dependency evidence protocol](RUNTIME_DEPENDENCIES.md). Its policy and target environment are scope-bound; the per-scene receipt is separate from view-capture receipts.


## Invocation costs and repair comparison

Every `invoke` / `check-3d-app` result after argument parsing includes `metrics`: wall time for the operation, available provider usage with links to native model records, and optional caller costs. Direct legacy commands retain their existing timing fields and do not produce this application ledger. Failed attempts count as work too.

Pass `--cost-context cost.json` (or `cost_context=` to `invoke`) with:

```json
{"schema_version":"1.0","delivery_id":"conveyor-demo","revision_id":"v1","human_minutes":null,"compute_cost":null,"currency":null,"source":"Caller record; human time and billing not yet measured"}
```

Record each human/compute cost once, as an increment for that invocation. Use a three-letter currency when compute cost is known. Null means unmeasured, never zero. A reused completed receipt retains its original metrics and incurs no new model call; do not count it twice. Parsing failures have no completed invocation metrics.

`scene_acceptance.accounting.summarize(receipt_paths)` validates and groups original `invocation.json` receipts by delivery. It rejects duplicate run IDs, replay-response receipts, malformed or non-finite metrics, compute costs without a currency, and mixed currencies. Totals stay unknown when a component is missing. Use the original saved receipt after a cached call; the replay response is not another billable run. Receipt validation does not authenticate the caller or verify every output file. Include unsuccessful attempts when assessing cost per accepted delivery. Retain the owner's final scoped acceptance separately: a successful preparation is not acceptance, and summed overlapping call durations are not end-to-end latency.

`evaluate --previous-run PATH` already compares repaired deliveries. Under the same scope it now distinguishes `improved_in_stated_scope`, `regressed_in_stated_scope` and `newly_unresolved_in_stated_scope`. A disappeared check remains unassessed. A changed scope is reported separately rather than claimed as a repair.
