# Scene evaluation HTTP API — proposed contract

Status: optional future wrapper, October 3, 2026. The owner's clarified direction is [a CLI callable from applications](APPLICATION_CLI.md), which is the primary integration. The service-first assumption below is superseded; this proposal is retained for applications that may later need remote execution. No HTTP server, endpoints, upload store or job queue is implemented. The local CLI and Python evaluation functions already support general checks, mapped briefs, explicit contracts and declared-scope review. Optional CLI model review exists separately.

Use one evaluation endpoint with a required scene and optional specification. General checks and brief-based checks are modes of the same operation. Starting a run, fetching its results and requesting a model opinion are separate operations.

## Initial scope and assumptions

Start as a local application service around the existing saved-USD harness. There is no requirement yet for a public multi-user service or distributed workers. One scene means a root USD entrypoint plus its referenced local files, not necessarily a single file and not every possible 3D format. Existing admission and pack limits still apply.

An uploaded bundle is immutable. In the first API version, scene files, optional baseline, brief manifest, text and reference images share that bundle. Paths are relative to it. This matches the current runner and avoids inventing remote filesystem access. A caller adding a brief later uploads a new bundle; content deduplication or independently reusable brief bundles can follow once source-path mapping is implemented and tested.

The flow is: upload a bundle, start an evaluation, poll its status, then retrieve its JSON or HTML report. The HTTP adapter creates isolated run directories and invokes existing evaluation code. It does not change measurement criteria or run a producer.

## Proposed endpoints

| Endpoint | Responsibility | Implementation phase |
|---|---|---|
| `POST /v1/bundles` | Upload a package of named files; return immutable `bundle_id`, content hash and file inventory | First service version |
| `POST /v1/evaluations` | Evaluate one scene, with an optional mapped brief | First service version |
| `GET /v1/evaluations/{id}` | Read execution status, structured results and report links | First service version |
| `GET /v1/evaluations/{id}/report` | Read the HTML report and linked report resources | First service version |
| `POST /v1/evaluations/{id}/model-reviews` | Opt in to an advisory model review of the saved result | Follow-on adapter; CLI capability exists |
| `GET /v1/model-reviews/{id}` | Read the separate model-review status and opinions | With model-review endpoint |
| `POST /v1/evaluation-batches` | Submit a list of ordinary evaluation requests, with per-scene outcomes | Later convenience layer |
| `POST /v1/brief-drafts` | Turn raw text/images into a proposed requirement map using an explicitly configured model | Future capability; not implemented in the harness |

The report route also needs namespaced access to its generated assets, source copies and evidence files, for example `GET /v1/evaluations/{id}/report/{relative_resource_path}`. It serves only files in the saved report manifest. An HTML link must not expose an arbitrary server path.

## One evaluation request, optional brief

Scene-only request:

```http
POST /v1/evaluations
Content-Type: application/json
Idempotency-Key: caller-chosen-run-key
```

```json
{
  "scene": {
    "bundle_id": "bundle_123",
    "entrypoint": "scene.usda"
  }
}
```

With a prepared text/image brief:

```json
{
  "scene": {
    "bundle_id": "bundle_123",
    "entrypoint": "scene.usda"
  },
  "brief": {
    "manifest_path": "briefs/brief.json"
  },
  "limits": {
    "max_dependency_files": 64
  }
}
```

Omitting `brief`, or explicitly setting it to `null`, selects the shipped general baseline. A present but invalid/empty brief is an input error; it must never silently fall back to general checks. The brief manifest references its original text/images and explicit checks, requirements, tolerances and mapping-review state. Their hashes become part of the evaluation record. Passing an image alone does not create an appearance test.

The first service supports these two request forms only. Follow-on explicit `contract` and `review_plan` selectors must be mutually exclusive with `brief`, matching the CLI. A contract-based edit check can additionally name a baseline in the same bundle. The service must preserve the caller-owned review/contract boundary rather than treating an uploaded producer decision as approval. Unsupported selectors should be rejected, never ignored.

## How scenarios map to the same operation

| Scenario | Request difference | Expected assessment scope |
|---|---|---|
| Check a scene without requirements | Omit `brief` | General diagnostics; no claim that task intent is satisfied |
| Check a scene against text requirements | Include a mapped brief referencing text | General checks plus selected numerical/structural targets |
| Check against text and reference images | Include a mapped brief referencing both | General checks plus selected image and other comparisons; not automatic rendered-appearance certification |
| Assess the same scene under a different brief | Create another evaluation with a different brief manifest | Separate result with both identities; preserve the earlier assessment |
| Check a repaired scene | Upload the new revision and create another evaluation using the same brief | New revision-bound evidence; do not mutate the old result |
| Check a before/after edit | Later explicit contract mode, with candidate and baseline paths | Only the edit-preservation checks selected by that contract |
| Add qualitative model analysis | Create a model-review job against a completed evaluation | Advisory opinions alongside unchanged script findings |
| Submit raw prose/images without mappings | Prepare and review a map before evaluation; optional future draft endpoint | No implied complete coverage from merely attaching source material |

## Execution status and assessment are different fields

The proposed create response is `202 Accepted` with an evaluation ID and status/report URLs. `queued`, `running`, `completed` and `failed` describe service execution. A successfully produced report can reject a scene; that is not an HTTP server failure.

Illustrative completed response, not an existing runtime schema:

```json
{
  "evaluation_id": "eval_456",
  "status": "completed",
  "scene": {
    "bundle_id": "bundle_123",
    "entrypoint": "scene.usda"
  },
  "brief": {
    "manifest_path": "briefs/brief.json"
  },
  "result": {
    "artifact_verdict": "REJECT",
    "declared_scope_verdict": "REJECT",
    "model_review_status": "not_requested"
  },
  "links": {
    "report": "/v1/evaluations/eval_456/report",
    "evidence": "/v1/evaluations/eval_456/report/core-result.json"
  }
}
```

Without a brief/review plan, `declared_scope_verdict` is `null`; it must not report that user requirements passed when none were supplied. The complete result also exposes the existing scene inventory, check matrix, per-check subject units/counts, specification coverage, unknown/skipped areas and evidence. Avoid one percentage that mixes asset inventory, samples, stage validators and requirement comparisons.

The service records immutable input hashes, selected pack/check versions, checker digest, effective limits and separate baseline/brief identities where relevant. Missing optional providers remain evaluation errors. When a valid report records `EVALUATION_ERROR`, preserve that report with execution `completed`; use execution `failed` when the service could not produce a valid report. Input-schema errors use a client-error response; service/process failures must not masquerade as scene rejection.

An idempotency key binds to a canonical request hash: repeating the same key/request returns the same run, while reusing it for a different request returns a conflict. An explicit new key starts a new run even if the inputs are identical. Do not promise an identical qualitative model response from identical evidence.

## Optional model reviewer

The newer [CLI invocation](EVALUATION_MODES.md) implements a shared dispatcher with `checks`, `judge` and `both`, including no-brief review. A future HTTP wrapper should use that same dispatcher; the present separate-review sketch below reflects the legacy judge's brief-report limitation. No HTTP route is implemented.

Example proposed request:

```json
{
  "reviewer_id": "configured-reviewer",
  "view_ids": ["view_front", "view_overview"]
}
```

Send it to `POST /v1/evaluations/{id}/model-reviews`. The service resolves `reviewer_id` to a server-configured CLI adapter; HTTP callers do not send executable paths, shell commands or provider credentials in this payload. View IDs resolve to explicitly admitted caller-supplied images tied to the evaluation. The existing reviewer requires a brief report; a no-brief evaluation must return a clear unsupported-input response until a separate general-review contract is designed.

Model reviews retain their own request, response, model request, hashes, costs/usage when available, limitations and errors. They see script evidence, so agreement is not independent rediscovery. Failure or timeout of an optional review leaves the completed script report available. No model opinion changes a script verdict, supplies human approval or becomes a measured asset pass.

## Implementation sequence and verification

First implement bounded uploads, immutable bundle IDs, one isolated worker per evaluation, the scene-only/brief dispatcher, result persistence and report routes. Reuse `baseline_contract`/`evaluate_packs` for direct checks and `evaluate_brief` for brief mode; do not create a second evaluator. Run jobs asynchronously because provider checks and later model/simulation adapters have different durations. An initial bounded local queue is enough; no distributed infrastructure is justified by current usage evidence.

The upload adapter must validate package paths and limits before admitting a bundle. Callers select IDs and relative paths, not arbitrary host paths or fetch URLs. Map public resource IDs to private directories and keep each run's inputs/output isolated. Existing source-integrity checks remain necessary but are not a process sandbox. Authentication, ownership checks and operating limits must be defined before exposing this beyond the local application.

API tests should establish CLI/API outcome parity, source immutability, invalid/empty brief refusal, missing-file/provider reporting, concurrent run isolation, request-idempotency behavior, manifest-contained report routing and job-failure versus scene-rejection semantics. Add model-review tests only when that endpoint exists. These HTTP tests have not been written or run; the current 416 passing tests cover the local package, not this proposed service.

Revisit independent brief uploads, content deduplication, cancellation, retention, batch submission and distributed workers when actual application needs justify them. Automatic requirement drafting needs its own mapping-quality evaluation; it should remain separate from executing a reviewed requirement map.
