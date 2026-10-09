# Optional AI triage of assumptions

The triage operation asks a caller-configured model whether a declared decision or obligation needs human review. It returns the **AI recommendation** and the **applied caller policy** separately. It never supplies human approval or changes the underlying scripted or declared-scope verdict.

This feature is additional to the visual judge. Its first implementation is text-based and operates on caller-selected obligations, inferred requirements and producer decision records. It does not discover every hidden assumption or compute an engineering risk score.

Human-review items use **low, medium or high review risk** with built-in definitions that the owner can override. The report keeps the model's suggestion, the applied level and the human decision separate. All three levels still require review. These defaults apply when triage runs; ordinary scripted checks still make no model call.

## Where it fits

1. Evaluate the saved scene and declared scope using the existing review workflow. Retain the resulting `assessment.json` and its original producer/review input roots.
2. Select the decisions or obligations to triage and write an owner-controlled policy. Supply any relevant brief excerpts as explicit text evidence.
3. Call `check-3d-app triage`, the equivalent `check-3d-triage` alias, or `scene_acceptance.application.invoke('triage', ...)` with a configured model CLI.
4. Inspect the recommendation, evidence references, policy decision and next action. The application routes work and enforces release policy.

Use the [synthetic worked example](../examples/assumption-triage/README.md) to prepare a visualization decision and an unsupported physical-calibration assumption. Preparation itself makes no model call.

## Call it from any application

```sh
check-3d-app triage \
  --assessment ./assessment/assessment.json \
  --expected-assessment-sha256 ASSESSMENT_HASH \
  --policy ./review/triage-policy.json \
  --expected-policy-sha256 POLICY_HASH \
  --bundle-root ./delivery --review-root ./review \
  --triage-config ./model-cli.json --out ./triage-result
```

Hashes are the SHA-256 of the exact JSON file bytes retained by the calling application. Use a new output directory outside the assessment, producer and review roots. The policy must not come from the producer bundle. The existing [model configuration](BRIEFS_AND_MODEL_REVIEW.md#optional-cli-model-review) supports the isolated Codex driver or a trusted JSON CLI adapter; selecting it explicitly authorizes sending these inputs to that provider. Nothing calls a model during ordinary scripted checks.

```python
from scene_acceptance.application import invoke

result = invoke(
    "triage",
    assessment="./assessment/assessment.json",
    expected_assessment_sha256=assessment_hash,
    policy="./review/triage-policy.json",
    expected_policy_sha256=policy_hash,
    bundle_root="./delivery",
    review_root="./review",
    triage_config="./model-cli.json",
    out="./triage-result",
)
```

The same envelope, progress/deadline/cancellation controls and verified-completed-run reuse apply as in the [application protocol](APPLICATION_PROTOCOL.md). CLI options include `--progress`, `--deadline-seconds`, `--cancel-file` and `--reuse-completed`. A changed report, input, policy, configured adapter or output invalidates reuse. Local hashes identify bytes; they do not authenticate their author or prove their truth.

## Define the policy

A minimal policy for an existing assessed item is:

```json
{
  "schema_version": "1.0",
  "id": "viewer-delivery-review",
  "version": "1.0",
  "items": [
    {
      "item_id": "material-binding",
      "allow_routine_handling": true,
      "mandatory_human_review": false,
      "reason": "Styling choices are discretionary for this visualization.",
      "review_guidance": "Flag missing evidence or a choice that changes intended use; do not invent an exact color requirement.",
      "evidence_ids": []
    }
  ],
  "evidence": []
}
```

The item ID must exist in the supplied assessment. Each selected item carries its statement, original result, mapped measurements and any producer decision record, including assumption strings and affected object paths. It is one triage item even if that decision declares several assumptions. Other assessment items are listed as unassessed by triage; their original verdict still applies.

Optional `evidence` entries have `id`, `path`, `sha256`, `kind: "text"` and `description`. Paths are relative to the review root. List their IDs on the relevant policy item. The model sees only these explicit text sources and the selected assessment/check records. Text files are bounded to 256 KiB each and the model request has its normal byte budget. Missing declared sources stay visible; altered sources, escaping paths and references to unrelated evidence are rejected. Images continue to use the separate visual-review workflow.

## Recommendations and gates

| AI recommendation | Meaning | Applied boundary |
|---|---|---|
| `routine_handling` | The model sees no need for additional human review within the supplied context | Requires explicit caller permission; cannot clear an existing required review, required failure or missing context |
| `human_review_needed` | The model proposes escalation, with its reason and possible consequence | Report as a review request, not a confirmed defect or calibrated risk level |
| `insufficient_context` | The model cannot support a recommendation from the evidence | Request evidence or scope clarification; do not treat it as low risk |

The reducer preserves required review from the original assessment and mandatory review in the triage policy. A routine model recommendation cannot close either. The caller can close a triage request with the existing human-review record format through `resolve-triage`, described below. Resolve original declared-scope obligations through their existing workflow, then reassess changed inputs.

## Low, medium and high within human review

The hierarchy is:

```text
Routine handling
Human review needed
  High
  Medium
  Low
  Unrated — no supported grade available
Insufficient context
```

Unrated is a coverage state, not a fourth risk level. Missing information must not become low risk. Risk grades are qualitative judgments about the consequence of accepting the selected choice for its intended use; they are not probabilities, model-confidence scores or a manufacturing safety standard.

No extra configuration is needed for these default definitions:

| Level | Built-in definition |
|---|---|
| Low | Limited, reversible impact; a brief owner check can settle the choice. |
| Medium | Could invalidate the intended use or require substantial rework; review the basis before relying on it. |
| High | Could have serious consequences for physical operation or a consequential decision; require qualified domain review. |

When `review_risk_rubric` is absent, triage uses these definitions, including with an existing version `1.0` policy. The original policy file and its hash remain unchanged. The model request and result contain the active definitions and `review_risk_rubric_source: "built_in"`; an owner override is labelled `"owner"`. The HTML report identifies the source beside the rubric. Request and runtime identity bind the defaults used in that run, so changing the implementation requires a fresh triage run before human closure.

The owner decides whether these general definitions fit the job and can replace them with a reusable domain rubric. The model must explain its grade using the active definitions and supplied evidence. A missing physical parameter can warrant high-risk review when the possible consequence is clear. If the context cannot support any grade, the model leaves it null and explains the gap. Scripts validate the response, citations and policy gates; they do not verify the semantic accuracy of a risk grade.

To replace the defaults, use policy `schema_version: "1.1"` and supply all three definitions in this top-level field (a fragment, not a complete policy). These example custom definitions narrow the rubric to an internal visual walkthrough:

```json
"review_risk_rubric": {
  "low": "A reversible presentation choice that needs a short owner check.",
  "medium": "Could confuse the walkthrough or require rebuilding part of the scene.",
  "high": "Could mislead a decision the walkthrough is intended to support; require domain review."
}
```

A partial, null or malformed override is rejected rather than silently replaced with defaults. Remove the field to return to the built-in definitions. Keep the policy ID/version with the run and update it when changing the rubric.

A selected item can also set `minimum_review_risk: "high"` in a version `1.1` policy. This requires `mandatory_human_review: true` and works with either default or custom definitions. If the model suggests low, the applied level stays high. If it suggests routine handling, the item still goes to high-risk human review. A model can recommend a higher level than the owner's minimum. The report retains both values and the reason for the applied level.

| Situation | Reported result |
|---|---|
| Model recommends human review with a supported low/medium/high grade | Human-review queue at that level; no automatic approval |
| Owner minimum exceeds the model's suggestion | Human-review queue at the owner minimum, with both values visible |
| No custom rubric supplied | Built-in definitions apply; the model must still support its grade with evidence and a reason |
| An older response without risk fields, or insufficient basis for grading | Unrated when human review is required; no invented grade |
| Potential consequence is supported, but a measurement or source is missing | The model may propose a grade with its basis; the original evidence gap and gate remain. A high-risk concern does not fill in the missing measurement. |
| Model recommends routine handling or insufficient context | Its risk fields must be null; owner-required review and minimums still apply |
| Human approves the current triage request | Removed from the pending review-risk counts; model grade and owner policy remain in the record. Original failures and gaps still apply. |

`triage-result.json` exposes per-item `review_risk`, `review_risk_basis` and `review_risk_reason`, plus `human_review_risk_counts` for low, medium, high and unrated. The model opinion separately contains `review_risk` and `risk_reason`. Counts refer to selected obligations/decisions, not assets or newly discovered assumptions. The HTML report shows the nested queue and active rubric with its source. Changing the rubric or an item minimum invalidates an earlier human approval just like any other policy change.

The [worked example](../examples/assumption-triage/README.md) uses the default definitions and a high owner minimum for its physical-use decision. These are software controls; accuracy of model-assigned risk levels still needs human-labelled evaluation.

A routine recommendation accompanied by missing context cannot proceed routinely. Neither model output nor triage policy can clear an existing required artifact failure. A known advisory failure remains visible and can be treated as an allowed variation when the selected policy and evidence support that judgment.

| Combined result | Exit | Next step |
|---|---:|---|
| `NO_ADDITIONAL_REVIEW` | 0 | No additional review requested for the selected items; underlying scope accepted. This is not general scene approval. |
| `REJECT` | 2 | Preserve the original rejection and route repair; triage findings remain visible. |
| `NEEDS_REVIEW` | 3 | Resolve original scope gaps, obtain a human decision or supply evidence, as reported. |
| `EVALUATION_ERROR` | 4 | Fix invalid/stale inputs or model execution/response errors. Original verdicts remain visible if available. |

## Inspect the evidence

`report.html` shows the original verdicts, selected/unassessed counts, each declared decision, the AI's reason and possible consequence, cited evidence IDs, and the actual policy outcome. `triage-result.json` contains the same results. Copies of the original assessment and policy, the exact model request, validated response, native logs and a file manifest remain in the output folder.

Omit `--out` to keep each triage attempt in a dated folder under `./scene-acceptance-runs/`, or choose a project history with `--run-root PATH`. Open the returned `storage.summary_report` for the review-level counts and links to the full report. Failed attempts remain beside later runs. [Saved-run layout and replay limits](APPLICATION_PROTOCOL.md#saved-runs).

The operation verifies the caller-pinned assessment against its current producer/review input hashes, including previously missing files. It does not rerun the scene checks. Reassess a changed scene before triage. The report is intended for the calling application and may contain local evidence paths; review and sanitize it before publishing it outside that environment.

The separate experimental [audit operation](EXTENSIONS.md#assumption-audit) now proposes cited questions about undeclared choices. It produces no acceptance finding or approval. Source-linked individual assumption records, document semantics, specialist risk adapters and independent discovery-quality evaluation remain in the [enhancement plan](ASSUMPTION_REVIEW_PLAN.md). Unit tests exercise enforcement and transport; they do not establish that a model reliably recognizes consequential manufacturing assumptions.

## Close a mandatory triage item

A completed triage run now writes `review-requests.json`. Its `snapshot_sha256` binds the assessment, policy, item contents, original triage request and evidence identity. The owner records a decision in the existing declared-scope review format:

```json
{
  "schema_version": "1.0",
  "snapshot_sha256": "COPY_THE_TRIAGE_REVIEW_REQUEST_SNAPSHOT_HASH",
  "reviews": [{
    "item_id": "material-binding",
    "status": "approved",
    "reviewer": "Responsible reviewer",
    "reason": "Reason for accepting this specific item within the stated use",
    "evidence": [{"path": "review-note.txt", "sha256": "HASH_OF_REVIEW_NOTE_BYTES"}]
  }]
}
```

The JSON above uses explanatory hash placeholders; replace them with the exact retained hashes. Save it in the caller's review root, with referenced evidence relative to that root. The application then consumes that decision:

```sh
check-3d-app resolve-triage --triage-run ./triage-result \
  --expected-triage-sha256 HASH_OF_TRIAGE_RESULT_JSON \
  --review-record triage-reviews.json --out ./resolved-triage
```

No model is called. A current approval closes that triage request only. Original required failures, UNKNOWN/ERROR evidence and outstanding original scope reviews remain in force. A rejection or pending review returns `review_finding`. Any change to the scene, assessment, policy or original evidence makes the approval stale. Resolve against the original triage run; a later decision creates a new resolved output from that same original request.

Limited acceptance needs an explicit revised scope and a fresh assessment; it is not an informal `approved_with_limits` status. The report shows model recommendation, owner policy and human decision side by side. Hashes establish correspondence to evidence, not the identity or authority of a reviewer. The receiving application must protect review records against producer self-approval.

## Evaluate whether triage is useful

The [human-label guide and pilot protocol](../evaluation/triage-value-v1/README.md) explain how to test the model's recommendations. A domain reviewer first marks each case `matters` or `routine` for its intended use, with a reason, without seeing model output. Three fresh model runs per item then let the study count missed important items, unnecessary escalation, missing context and variation. Reviewer-time savings need a measured human baseline.

These labels are only for the evaluation. They are kept out of model requests and do not replace the caller's policy or the human decisions above. Ordinary harness runs need no label sheet. The pilot still has no completed human labels or model-quality result.

## Model response compatibility

New model responses use schema `1.2`, retaining `model_policy_paraphrase` and adding required `review_risk` and `risk_reason` fields. Both risk fields are null outside a supported human-review grade; an ungraded human-review response under a rubric must explain its missing context. **Model’s reading of the policy** remains separate from the actual owner policy. Version `1.1`, explicit `1.0` and old unversioned responses remain accepted; missing risk fields normalize to null. Unknown versions fail validation.

Result schema `1.3` records the active definitions and their source. All earlier result schemas remain available for retained reports. A default rubric supplies definitions, never synthetic human labels or an automatic grade for an older model response.

The Codex driver can optionally carry `ignored_codex_notices`, an exact-match list of known informational error-item messages. The default is empty. A new message, a changed suffix, a failed turn or a tool event still fails; no prefix match is used. This configuration is rejected for other drivers. Configure each model role deliberately; triage does not silently change interpreter or judge behavior.

Current policies use `triage-policy-v1.1`; unchanged version `1.0` policies use the built-in grading definitions. New results use `triage-result-v1.3` and review requests use version `1.1`. The existing human-review record format stays unchanged. All older published policy, response and result schemas remain available through capabilities. The pilot scorer accepts retained result versions but still scores review routing only, not risk-level accuracy. Human closure requires a fresh current-version run and matching runtime/evidence; it does not migrate an old result into an approval.
