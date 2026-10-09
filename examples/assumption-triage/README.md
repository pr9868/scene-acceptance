# Two decisions, different review needs

This synthetic example uses a small material-delivery fixture. It is a test of the handoff, not a manufactured scene failure or a calibrated simulation.

- A valid surface binding is acceptable for a visualization whose color is discretionary. The policy permits routine handling.
- A producer declares that visual plausibility establishes contact friction. The brief requires physical evidence and domain review. That gate remains open even if the model recommends routine handling.

After installing the current package, run:

```sh
python examples/assumption-triage/prepare.py --out /tmp/assumption-triage-example
```

This prepares a scene, source brief, producer decisions, caller policy and a fresh declared-scope assessment. It makes no model call and creates no human approval. The artifact check passes; the physical-use obligation remains unresolved.

The script prints a `check-3d-app triage` command with the generated input hashes. Replace `YOUR_MODEL_CONFIG.json` with your explicitly configured model CLI and run that command. Both recommendations and the applied policy are in the new `triage/report.html`. The result must continue to require review of the physical-use decision, regardless of the model's opinion.

The generated policy uses the built-in low/medium/high definitions by omitting `review_risk_rubric`, and sets a high minimum for the physical-use item. Even a routine or low model recommendation cannot lower that owner requirement. The report identifies the definitions as built-in and shows the suggested grade, applied level and pending counts separately. Supply all three definitions in `review_risk_rubric` to replace the defaults for your job. The high minimum in this example is a synthetic owner policy, not a validated risk threshold.

See the [triage guide](../../docs/ASSUMPTION_TRIAGE.md) for the policy schema, input boundaries, exit meanings and Python call. The current operation uses declared decisions and text evidence; it does not find every hidden assumption or validate physical behavior.
