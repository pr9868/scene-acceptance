# Artifact checks and declared-scope review in one run

The review layer is installed with Scene Acceptance as `scene_acceptance.review` (review version 0.2.0). It reruns the core evaluator and records a second verdict for caller-declared obligations. It does not accept an uploaded green report as evidence, infer all requirements, or make independent engineering judgments.

Reports now open with the [scene, specification sources and coverage matrix](SCENE_AND_SPECIFICATION_REPORTS.md). Optional `specification_source`, `areas` and `coverage_declaration` fields make intended-use reporting clearer without replacing the existing check/review gates. A passing mapped check is kept separate from the claim that it covers the full requirement.

```sh
check-3d --review-plan plan.json --review-root /path/to/owner-review \
  --plan-sha256 <sha256-of-plan.json> --bundle-root /path/to/delivery \
  --decisions decisions.json --reviews reviews.json --out /path/to/new-report
```

Omit `--decisions`/`--reviews` when absent. Paths for the plan and reviewer records resolve within the review root; producer decisions, contract, candidate and optional baseline resolve within the delivery root. Roots must be separate and non-nested. Output must be new and outside both roots. `--max-dependency-files` retains the core's caller-controlled admission budget. `--allow-pack` explicitly enables trusted installed extensions. The pinned plan owns the contract/candidate/baseline: CLI overrides are rejected.

`check-3d` keeps the same exit meanings in every mode: 0 accepted in the stated scope, 2 rejected, 3 insufficient evidence/needs review, 4 evaluation error. Argument errors in `check-3d` return 4. The compatibility command `assess-3d PLAN ... --approve-pack ...` keeps the earlier review command's exit codes 0/1/2/3. The former separately installed `harness_review` import is replaced by `scene_acceptance.review`; no second Python distribution is required.

Try the deliberately incomplete example:

```sh
python examples/declared-scope/prepare.py --out /tmp/declared-scope-example
```

Run the command it prints. The scene passes its required sampled checks, but the broad continuous-motion obligation and pending mapping review prevent declared-scope acceptance. This example creates no approval or reviewer identity on anyone's behalf.

| Review question | What the caller supplies | What the harness enforces |
|---|---|---|
| Explicit requirements | Requirement, source/basis, required/advisory, mapped check IDs | Known required failures reject; unmapped required obligations stay UNKNOWN |
| Inferred necessities | Proposed/approved status, approver and reason | A proposed inference is not silently treated as an established defect |
| Design decisions | Producer's choice, alternatives, assumptions and evidence; separate reviewer judgment | Producer explanations cannot approve themselves; missing decision/evidence stays unresolved |
| Delivery integration | Required links to suitable core checks | Actual current artifact/check results, with the original verdict preserved |
| Evidence for intended use | Relevant simulation/reference evidence or a required review | Finite samples do not become continuous proof; no renderer or real-world calibration is invented |

The closed plan schema requires all five layer declarations, including a reason for every exclusion, at least one required obligation, the contract hash, and mapping-review status. Included layers without obligations are gaps. A row contains `id`, `layer`, `statement`, `basis`, `required`, `check_ids`, `review_required`, `decision_id` and `inference_authorization`. Schema definitions are in `scene_acceptance.review.schemas`; the example is an editable starting point.

Run once to obtain an assessment snapshot. If a judgment is required, the caller reviews that evidence and supplies a reviewer record with the exact snapshot hash, item ID, status (`approved`, `rejected`, `needs_review`), reviewer, reason, and evidence file hashes. Scene, contract, plan, relevant measurements, producer decisions or evaluator changes make old judgments stale. The fingerprint excludes only known execution-duration fields; simulation time, trajectories and unknown provider fields remain bound. A recorded approval cannot cancel a known required failure. Reviewer identities are recorded, not authenticated; local directory separation is a convention, not an OS sandbox.

| Declared-scope result | Meaning |
|---|---|
| `ACCEPT_FOR_DECLARED_SCOPE` | Core accepted; required declared obligations passed; mapping recorded as reviewed; no blocking scope gaps |
| `REJECT` | Required artifact/obligation failure or applicable required rejection |
| `NEEDS_REVIEW` | Required evidence/judgment/mapping is unresolved; advisory UNKNOWNs remain visible without independently blocking acceptance |
| `EVALUATION_ERROR` | Invalid policy, unknown check IDs, execution/integrity error or unusable configured inputs |

One output directory contains:

- `report.html`: both verdicts, all five review layers, obligation counts, detailed artifact check counts and inventory, searchable check table and coverage limits.
- `summary.md`, `obligations.csv`, `assessment.json`, unchanged `core-result.json`, and a recursive file-hash manifest.
- `artifact/`: the complete original HTML/Markdown/check/subject/finding CSV/JSON report. Obligation CSV pointers target `assessment.json`; artifact CSV pointers target `artifact/result.json`.

Obligation counts, assets, samples and provider invocations are distinct units. A review layer with UNKNOWN/ERROR items says `ASSESSED_WITH_GAPS`, rather than implying a complete assessment. An excluded layer never counts as passing.

**Known limit retained as a test:** a caller can map a material requirement to an unrelated but passing format check and mark that mapping reviewed. The tool cannot independently determine that the mapping is relevant. It also cannot discover a requirement absent from the plan. This is why a good requirement map and suitable measurement remain necessary alongside the harness.
