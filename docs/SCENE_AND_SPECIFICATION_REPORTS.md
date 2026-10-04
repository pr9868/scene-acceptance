# Reading a scene test report

The report now starts with the scene that was tested, how it is structured, where the selected requirements came from, and a compact results matrix. Detailed measurements remain underneath. No acceptance rule or existing expected outcome changes as part of this presentation.

| Section | Question answered |
|---|---|
| Scene under test | Which saved file/revision, baseline and intended use? How many prims, meshes, materials, animated transforms, physics objects and dependencies? Which units, up axis and clock? |
| Results at a glance | Which general or specification-influenced checks passed, warned, failed, remain unknown, errored, or had no applicable subjects? |
| Specifications by area | Was a human source recorded for geometry, materials, texture content, UVs, motion, physics, simulation, appearance or delivery? What other sources were recorded? |
| Specification details | What was requested, which checks mapped to it, what targets/values were compared, and how much automated coverage exists? |
| Detailed results | Which individual objects/files/samples were assessed, and where is the original evidence? |

## Three independent distinctions

**Domain** says what was checked: geometry, textures, motion and so on. **Basis/source** says whether the check needs a task-specific target and who is recorded as supplying it. **Method** says how evidence was obtained: saved-artifact inspection, a simulation worker, or separate review. A simulation can test a human specification; it is counted once, not as an additional category of success.

The matrix partitions selected automatic checks into five groups:

1. General structural/delivery diagnostics: known rules that need no task-specific target. A person can still select these rules. Image decoding and authored-motion sanity checks belong here as well as topology and file availability.
2. Checks linked to a recorded human specification.
3. Checks linked to recorded application, agent or preset specifications.
4. Target-based checks whose source is unrecorded.
5. Checks whose basis is unclassified, including unknown external providers and old records without pack metadata.

A general rule explicitly mapped to a declared specification appears in the linked-specification category because its result is being used to support that requirement. If a check supports several requirements, it is still counted once; any recorded human link puts it in the human-linked row, followed by other known sources, then unrecorded sources. All links remain in `overview.json`. This does not certify that the mapping is relevant.

Review obligations are shown separately, because a recorded judgment is not another automatic check. Required/advisory counts are retained for each matrix group. A failure in an advisory comparison does not independently change the contract verdict. Counts of checks, requirements, assets and motion samples must not be added together.

## Recording a specification source

Existing contracts and review plans still work. Without provenance, the report says **source unrecorded**. It never treats an `explicit` review layer or configured numeric target as proof that a human supplied it. The built-in four-job preset is identified as a preset.

Contract v2 accepts an optional `report_context` containing `scene_name`. Each selected check can optionally carry:

```json
"specification_source": {
  "provided_by": "human",
  "reference": "Owner brief, motion requirement 2"
}
```

`provided_by` is one of `human`, `application`, `agent`, `preset`, `unrecorded`. The reference is a caller-supplied label, not an automatically loaded or authenticated source. Preserve actual supporting files through the existing evidence inputs when needed. Do not label an agent-created assumption as human input.

A caller-owned review plan can set the same source on each obligation, plus:

```json
"areas": ["motion"],
"coverage_declaration": {
  "extent": "partial",
  "reason": "Finite samples measure attachment gaps; continuous-time correctness still needs evidence."
}
```

Coverage extents are `full`, `partial`, `unreviewed`, with a required reason. These are reporting declarations, not new acceptance rules or a replacement for `review_required`. Declare any required unresolved judgment in the actual review plan. Existing review semantics continue to gate unknown obligations. The source/coverage declarations are included in the hashed contract or plan; changing them changes the recorded revision. Unsupported provenance values and unknown fields are rejected by the closed schemas.

If an obligation omits its source, the report inherits a source only when its mapped checks unanimously record the same source type; otherwise it stays unrecorded. The report retains the check-level sources as well. Explicit provenance is preferable for broader obligations.

## Coverage is separate from a passing result

| Situation | Report wording |
|---|---|
| General baseline with no task map | No task specification recorded; full-intent coverage is unknown |
| Configured target without a full requirement map | Target configured; complete specification not mapped |
| Obligation has no automated check | No automated coverage |
| Mapped evidence is unknown, errored, partial or has no applicable subjects | Automated evidence incomplete |
| Sampled checks run but a separate judgment is required | Partial automation; separate review required |
| Mapping review remains pending | Mapped checks ran; mapping review pending |
| Caller declares only partial coverage | Partial mapping declared by caller |
| Caller declares full mapping and no required separate review remains | Full mapping declared by caller — not independently certified |
| No coverage extent recorded | Mapped checks ran; coverage extent unreviewed |

The report may say **1/1 mapped checks produced assessed results** while a continuous-motion obligation remains UNKNOWN. This fraction describes execution of the map, not the percentage of the whole requirement satisfied. A failed comparison is assessed evidence, not missing coverage; it remains a failure. Warnings occupy their own category. Core admission/integrity failures remain separate from selected content-check counts.

“No human source recorded” means the input records do not establish one. It does not claim that the user never supplied a specification elsewhere. Without a declared map, missing or incorrectly mapped intent cannot be discovered automatically.

## Outputs and examples

In addition to the existing files, every report includes `overview.json`, `result-matrix.csv` and `specifications.csv`. Specification CSV rows name the evidence file and JSON pointer; combined review reports point to `assessment.json` or `core-result.json`. The matrix has one row per category, so it intentionally has no per-check evidence pointer. The JSON overview retains category membership and measured subject counts.

```sh
python evaluation/report-context-v1/run.py --out /tmp/scene-report-examples
```

Open `index.html` to compare general-only panel checks, a readable wrong texture, a pending continuous-motion review, and a separately labeled synthetic human-source control. The last example tests the reporting field; it is not evidence that a real human authored those requirements. All examples copy existing fixtures and preserve original bytes.

The scene hierarchy shows the first 32 prims at the first two levels; detailed inventory is separately labeled. No scene semantic description is invented from a filename. Zero authored transform animation does not rule out application-driven motion. USD metadata defaults are labeled as defaults, not authored intent.
