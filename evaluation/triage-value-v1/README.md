# Does triage save useful review work?

**Status: protocol and scoring controls prepared; no human labels or model-quality result yet.** The ten case cards include three questions anchored to published observations and seven constructed variations. They are a labeling pilot, not a representative manufacturing benchmark. The published delivery subset lacks complete original scenes and all producer decision records; do not call these cards a full replay of those deliveries.

## Freeze before running

1. Have a domain reviewer label each card `matters` or `routine`, with the intended use and reason, before seeing any model output. Use `cases.json` and fill `labels.template.json`. Ambiguous cards should be clarified or excluded before freezing the case list, not after seeing results. Keep at least one item in each class; more independent real cases are needed for a reliable estimate.
2. The responsible owner approves the pass bar in `protocol.json` before running: no labeled-important item treated routinely in any of three repeats; fewer than half of routine-item runs escalated, counting insufficient context as review work. Do not relax it after results.
3. Prepare a real declared-scope assessment/policy for each case with relevant evidence. Protect these inputs from the producer. Case cards alone are not those assessments. Include the preserved producer decisions when available; the selected public excerpts cannot substitute for missing records.
4. Hash the completed labels and protocol. Run `triage` three fresh times per item with the same policy, model configuration and evidence. Record all three outputs, including provider errors. No automatic retries or cherry-picking. Keep reviewer labels out of model requests.
5. Record a baseline: the same delivery, brief and intended use reviewed with selected validators plus a person. Record relevant findings, repair rounds, setup time and active review minutes for both workflows. Use a different reviewer or counterbalanced order to reduce learning effects. Compare equivalent scopes; credit human discoveries separately from scripted discoveries.

The existing [independent producer protocol](../producer-trial-v1/PROTOCOL.md) still needs an externally authored brief and outside assessment. This evaluation does not supply either by naming an assistant an independent reviewer.

## Collect and score

Create an observations JSON with `labels_sha256`, `protocol_sha256` and `cases`. Each case supplies its `id`, optional `baseline_human_minutes` and `harness_human_minutes` (null if unmeasured), plus three `runs`. Each run contains an integer `repeat` 1–3, the same `item_id`, and two paths relative to the observations file:

```json
{"repeat":1,"item_id":"indicator-state","result":"indicator-1/triage-result.json","invocation":"indicator-1/invocation.json"}
```

Use `check-3d-app triage`, `check-3d-triage` or `invoke("triage", ...)` with a fresh output directory for each run. Retain its original `invocation.json` beside `triage-result.json`. Copied receipts, cache-replay responses and human-resolved results cannot stand in for fresh runs. Repeated calls may legitimately return identical recommendations; their original invocation IDs must still be distinct.

```sh
python evaluation/triage-value-v1/score.py \
  --labels ./reviewed-labels.json --observations ./observations.json --out ./evaluation.json
```

The scorer validates results and receipts, verifies that each receipt contains and hashes its result, and checks three distinct invocation IDs per item. All repeats must use the same assessment, item, policy, evidence snapshot, model request and runtime. It counts raw model recommendations separately from enforced policy and reports missed important items, unnecessary escalation, insufficient context, provider errors, variation across repeats and paired reviewer-time differences when measured. A mandatory policy gate does not earn credit for a model that recommended routine handling on a labeled-important item.

Hashes and invocation IDs detect inconsistent records and copied runs; they do not authenticate execution, prove when a person labeled a case or establish assessor independence. The reviewer must also verify that the selected assessment item represents its case card. Retain that evidence in the evaluation record. Every report states its pilot size. Passing this bar on ten selected cases does not establish zero risk in production.

## Future audit holdout

Only after reviewing triage's value, consider an experimental audit that proposes cited questions about undeclared choices. Before testing the diverter, remove its decision record and every answer-revealing feedback file, caption and filename. Include the repaired scene and a legitimately different route policy. Score the specific question and its evidence, not generic suspicion. A question is never promoted automatically to a measured failure.
