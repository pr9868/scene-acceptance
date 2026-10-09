# Optional AI triage of assumptions

The triage operation asks a caller-configured model whether a declared decision or obligation needs human review. It returns the **AI recommendation** and the **applied caller policy** separately. It never supplies human approval or changes the underlying scripted or declared-scope verdict.

This feature is additional to the visual judge. Its first implementation is text-based and operates on caller-selected obligations, inferred requirements and producer decision records. It does not discover every hidden assumption or compute an engineering risk score.

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

The reducer preserves required review from the original assessment and any mandatory review in the triage policy. A mandatory triage-policy item remains a human-review request even if the model says routine; the calling application records and acts on the human decision. This operation does not issue a new approval record. Resolve original declared-scope obligations through the existing review workflow, then reassess changed inputs.

A routine recommendation accompanied by missing context cannot proceed routinely. Neither model output nor triage policy can clear an existing required artifact failure. A known advisory failure remains visible and can be treated as an allowed variation when the selected policy and evidence support that judgment.

| Combined result | Exit | Next step |
|---|---:|---|
| `NO_ADDITIONAL_REVIEW` | 0 | No additional review requested for the selected items; underlying scope accepted. This is not general scene approval. |
| `REJECT` | 2 | Preserve the original rejection and route repair; triage findings remain visible. |
| `NEEDS_REVIEW` | 3 | Resolve original scope gaps, obtain a human decision or supply evidence, as reported. |
| `EVALUATION_ERROR` | 4 | Fix invalid/stale inputs or model execution/response errors. Original verdicts remain visible if available. |

## Inspect the evidence

`report.html` shows the original verdicts, selected/unassessed counts, each declared decision, the AI's reason and possible consequence, cited evidence IDs, and the actual policy outcome. `triage-result.json` contains the same results. Copies of the original assessment and policy, the exact model request, validated response, native logs and a file manifest remain in the output folder.

The operation verifies the caller-pinned assessment against its current producer/review input hashes, including previously missing files. It does not rerun the scene checks. Reassess a changed scene before triage. The report is intended for the calling application and may contain local evidence paths; review and sanitize it before publishing it outside that environment.

Source-linked individual assumption records, automatic discovery of undeclared choices, document semantics and specialist risk adapters remain in the [enhancement plan](ASSUMPTION_REVIEW_PLAN.md). Unit tests exercise enforcement and transport; they do not establish that a model reliably recognizes consequential manufacturing assumptions.
