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

Create an observations JSON with `labels_sha256`, `protocol_sha256` and `cases`. Each case supplies its `id`, optional `baseline_human_minutes` and `harness_human_minutes` (null if unmeasured), plus three `runs` with `repeat` 1–3, `result` (path relative to that observations file), and `item_id`. Each result is an actual retained `triage-result.json` from that run, not a hand-entered policy outcome.

```sh
python evaluation/triage-value-v1/score.py \
  --labels ./reviewed-labels.json --observations ./observations.json --out ./evaluation.json
```

The scorer validates each result schema, counts raw model recommendations separately from enforced policy, checks complete three-repeat coverage and refuses duplicate request-output paths or mixed label/protocol identities. It reports missed important items, unnecessary escalation, insufficient context, provider errors, variation across repeats and paired reviewer-time differences when measured. A mandatory policy gate does not earn credit for a model that recommended routine handling on a labeled-important item.

Hashes bind the chosen files; they do not independently prove when a person labeled them or that the assessor was independent. Retain that evidence in the evaluation record. Every report states its pilot size. Passing this bar on ten selected cases does not establish zero risk in production.

## Future audit holdout

Only after reviewing triage's value, consider an experimental audit that proposes cited questions about undeclared choices. Before testing the diverter, remove its decision record and every answer-revealing feedback file, caption and filename. Include the repaired scene and a legitimately different route policy. Score the specific question and its evidence, not generic suspicion. A question is never promoted automatically to a measured failure.
