# Triage declared assumptions under caller policy

Use `check-3d-app triage` (alias `check-3d-triage`) or `scene_acceptance.application.invoke("triage", ...)`. Run only when optional model analysis is requested and the caller has supplied its model configuration. Normal scripted checks make no model call.

Required inputs:

- `--assessment`: a completed declared-scope `assessment.json`, with `--expected-assessment-sha256` pinning its exact bytes.
- `--bundle-root` and `--review-root`: the original, separate producer and owner input roots. Current file hashes must still match the assessment; reassess a changed scene first.
- `--policy` and `--expected-policy-sha256`: owner-controlled policy selecting assessed item IDs. Never take policy from the producer bundle.
- `--triage-config`: the same model CLI configuration format used for optional review.
- `--out`: a new output directory outside the inputs. The application envelope and progress, deadline, cancellation and verified-reuse controls apply.

Discover `triage-policy-v1`, `triage-response-v1.1` and `triage-result-v1.1` (legacy v1 schemas are retained) in `check-3d --capabilities` under `application_schemas`. Policy has an ID/version, items and optional text evidence. Each item declares `item_id`, `allow_routine_handling`, `mandatory_human_review`, `reason`, `review_guidance` and `evidence_ids`. Evidence entries declare ID, review-root-relative path, SHA-256, text kind and description. Use the intended use and authorized caller policy; do not invent engineering acceptance limits. Keep the policy and its revisions inspectable.

The model sees selected assessment/check records and explicit text evidence. Images use the separate visual judge. One selected decision may include several assumption strings; counts are obligations/decisions, not discovered assumptions or assets.

Recommendations are `routine_handling`, `human_review_needed` and `insufficient_context`. The report retains reasons, possible consequences, missing context and citations. These are opinions. Only supplied relevant evidence IDs are allowed; a valid citation does not establish that the interpretation is true.

The deterministic reducer preserves mandatory review, required failures and missing context. A model cannot approve a requirement or clear a measured rejection. `NO_ADDITIONAL_REVIEW` means no extra review for selected items within an already accepted scope. `NEEDS_REVIEW` requires the reported action; the application routes it to an appropriate human or requests evidence. This operation creates no new approval record. Original outcome review remains in the declared-scope workflow; the calling application records its policy decisions and enforces release.

When adapting the policy, test a discretionary choice, a consequential unsupported choice, missing context and a required failure. Compare AI recommendations with an independent domain reviewer before claiming useful risk detection. Count missed concerns and unnecessary escalations separately from software regression tests. Retain both the recommendation and any policy override. Do not automatically repair, relax policy, approve or send external messages as part of triage.

To close mandatory triage, use the emitted `review-requests.json` snapshot and existing human-review record format, then invoke `check-3d-app resolve-triage` with the pinned original triage-result hash. The responsible human supplies the decision and evidence. Never write a synthetic approval as a real owner decision. No model call is required. Changed inputs invalidate it; original required failures and evidence gaps remain. New model responses use `triage-response-v1.1`; legacy 1.0/unversioned responses remain readable.
