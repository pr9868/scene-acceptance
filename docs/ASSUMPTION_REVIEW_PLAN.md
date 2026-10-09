# Plan: inspectable assumptions and review gates

**Status: triage, default low/medium/high review-risk buckets with owner overrides and human closure are implemented. Experimental audit can propose cited questions; native PDF provenance, process connectivity and external-engine transport are also implemented. Richer individual assumption records, domain-specific risk semantics and independent model-quality evaluation remain proposed.** The [triage guide](ASSUMPTION_TRIAGE.md) documents the supported operation. The [adopter guide](ACCEPTANCE_WORKFLOW.md) describes the current workflow and its limits.

The goal is to let a receiving user inspect what a delivery depends on: which requirements were checked, which producer choices were grounded in the brief, and which unresolved assumptions need a decision before release. The calling application enforces the owner's release policy.

## Build on what exists

The declared-scope layer already has explicit requirements, inferred necessities, producer decisions, delivery integration and intended-use evidence. Producer decision records include a choice, reason, alternatives, an array of assumption strings, affected paths and evidence files. Mapped decisions require separate review; missing required evidence or review prevents declared-scope acceptance. Unmapped declared decisions already create a scope gap. Reviews are tied to an assessment snapshot and become stale when relevant inputs change.

Those mechanisms do not discover decisions the producer omitted, establish whether the requirement map is relevant, or assess the engineering consequence of an assumption. Optional triage now recommends review for selected assessed items under explicit caller policy. It can apply qualitative low/medium/high review-risk buckets using built-in definitions or an owner override, with any owner minimum enforced, while keeping unsupported grades unrated. It does not assign a calibrated engineering risk score. Extend these records and gates instead of building a parallel approval system.

## Proposed increments

| Priority | Enhancement | What would change for an adopter | Completion evidence |
|---|---|---|---|
| 1 | Traceable requirement and assumption records | Each assumption has an ID, origin, basis, source references, linked requirements/objects and an evidence status. Existing decision records remain usable through explicit migration. | Source references resolve; unsupported derivations remain ungrounded; original records and revisions are retained. |
| 1 | Owner-defined consequence and review policy | The owner declares which kinds of unresolved assumptions require domain review. The report explains the rule that triggered a gate. | Missing mandatory review blocks acceptance; a positive judge opinion cannot clear it; advisory items remain visible without silently becoming required. |
| 1 | An inspectable assumption section in reports | Each row shows the choice, basis, affected subjects, possible consequence, evidence, responsible reviewer and closing action. Readers can follow the source links. | JSON and HTML agree; stale decisions and missing evidence are visible; scripted failures retain their existing effect. |
| Implemented; evaluation remains | Optional AI triage of selected declared items | A configured model recommends routine handling, human review or more context, with evidence and the caller's policy basis. Suspected undeclared assumptions are outside this operation. | Enforcement and transport tests cover the gates; independent assessment must still measure missed consequential cases and unnecessary escalations. |
| Implemented experimentally; evaluation remains | Optional audit for possible undisclosed assumptions | A configured reviewer compares the brief, declared choices and available scene evidence, proposing specific questions with citations. | Seeded omissions can be investigated; suspected assumptions are distinguished from confirmed findings; false concerns and missed cases are measured. |
| PDF provenance implemented; semantics remain | Better handling of multi-document briefs | Source IDs, page/image regions, authority and conflicts survive conversion into supported text/image inputs. | Conflicting dimensions remain unresolved; illustrative references do not silently become binding requirements; conversions preserve source lineage. |
| Bounded packs and transport implemented; target validation remains | Specialist packs and evidence adapters | Add the measurements required by a particular use, such as process connectivity, runtime behavior or applicable SimReady tests. | Each adapter states its provider/version, supported inputs, coverage and missing-evidence behavior, with passing and failing reference cases. |

Priority describes implementation order, not a release promise. Start with declared assumptions and explicit review policy, then assess whether automatic discovery adds useful findings.

## Keep the meanings separate

The proposed record should distinguish:

- **Origin:** supplied by the owner, declared by the producer, or proposed by a reviewer.
- **Basis:** explicit instruction, cited derivation, chosen default, discretionary choice, conflicting sources or unknown.
- **Evidence status:** supported, contradicted, missing or outside the evaluator's coverage.
- **Possible consequence:** an owner-defined category with a reason and affected use. Until assessed, consequence is unknown.
- **Enforcement:** required check, required review or advisory, selected by the owner's policy.
- **Decision:** pending, approved with stated scope, rejected or superseded, with a responsible reviewer and revision identity.

These are design fields, not a new accepted JSON schema. Do not add them to current closed-schema inputs until migration and validation are implemented. An approval is a recorded decision about use; it must not relabel an unsupported assumption as measured truth.

Model confidence belongs to the review record, if used at all. It cannot stand in for the consequence of a wrong assumption. A reviewer saying “this may be risky” without a source, affected use or specific question is insufficient to establish a defect. Conversely, lack of a detected concern cannot establish that all important assumptions were disclosed.

## Optional AI triage, separate from approval

The visual judge offers advisory opinions against a rubric. The implemented, separate triage operation adds a structured recommendation about whether a selected obligation or declared decision needs a person to decide. Discovery asks whether a choice may be ungrounded; triage asks what should happen next. The separate [experimental audit](EXTENSIONS.md#assumption-audit) implements question generation; reliable discovery has not been established.

Its inputs are an existing declared-scope assessment, caller-selected items, explicit text evidence, a pinned policy and a configured model CLI. Current response values are `routine_handling`, `human_review_needed` and `insufficient_context`. See the [API and policy schema](ASSUMPTION_TRIAGE.md). One item may contain several assumption strings; individual assumption IDs and automatic source-document extraction are still future work.

Recommendations cite their available basis; insufficient-context responses may have no usable citation. Each response explains the possible consequence, missing context and policy reason. Model confidence remains separate. The application applies deterministic policy to that recommendation:

- An owner-mandated review, a required script failure or missing required evidence cannot be downgraded by the model.
- A routine choice may proceed without per-item human review only when the owner's policy permits it and the required checks are satisfied.
- Missing context remains visible; the policy decides whether to request evidence, clarify scope or require a reviewer. It never becomes an automatic low-risk classification.
- A suspected hidden assumption remains a proposal until corroborated. Triage must not turn the producer's undisclosed intent into an established fact.

The report shows the AI recommendation alongside the actual policy decision and reason, including policy overrides. The application assigns a responsible actor and records the resulting decision. A configured specialist role could receive the review request; the harness should not invent a reviewer or send external messages on its own.

Test this against independent human assessments. Count consequential assumptions the model missed, routine choices it escalated unnecessarily, insufficient-context cases and time spent reviewing. Judge the added value by useful decisions and reviewer workload, rather than agreement with the producer or the number of flags emitted.

## Example of the proposed handoff

Consider an illustrative pump-layout brief containing a P&ID and a reference photograph but no confirmed duty point. The producer chooses a pump and records that the photograph guided its appearance.

| Proposed report field | Example |
|---|---|
| Assumption or choice | Pump model selected from the visual reference; process suitability unverified |
| Basis | Producer declaration; reference image supports appearance only |
| Affected use | Whether this particular model can support a process simulation |
| Missing evidence | Duty point and a suitable equipment reference |
| Owner's policy | Process-equipment suitability requires domain review for this use |
| Next action | Supply the equipment evidence or obtain a decision limiting the delivery to layout visualization |
| Acceptance effect | Review remains open for the simulation use; changing intended use requires an explicit scope change |

This example has not been implemented or demonstrated as automatic detection. Today an application can express the decision and required review in the declared-scope plan. The proposed extension would make the basis and consequences more explicit and could ask about a missing declaration. It would not infer process fitness from a rendered pump.

## Application and API behavior to preserve

Keep preparation, evaluation and release decisions separate. New records should use the existing application protocol and common report, with an explicit schema version and capability discovery. Existing CLI users should continue to work unless they opt into the new policy. A contract must never install or execute producer-supplied evaluator code.

For mandatory unresolved assumption review, preserve the current review outcome and `review_specification` or `review_finding` next action as appropriate. Provide the reason and affected items, rather than sending a generic `repair_scene` instruction. The application decides how to route work and must enforce the gate.

Changes to the brief, decision basis, evidence, policy or relevant scene state must invalidate dependent approvals. Unchanged decisions can be carried forward only under a tested, explicit dependency rule. Do not auto-approve because a source hash matches or the producer marks a task complete. Existing recorded reviewer identity is not authenticated; deployments needing authenticated approvals must have the calling application provide that control.

## Tests before calling it useful

Use controlled cases with known expected outcomes before a new delegated-build trial:

| Case | Required outcome |
|---|---|
| Explicit dimension missed by the scene | Existing measurement still fails; assumption review cannot override it. |
| Missing source for a declared operating parameter | Report the missing basis and apply the owner's review policy. Do not invent a value. |
| Conflicting authoritative documents | Leave the requirement unresolved and route the choice to the owner. |
| A decorative choice explicitly left to the producer | Preserve the allowed choice; do not invent a repair requirement. |
| Missing or stale review/evidence | No acceptance of the required obligation until the matching evidence and decision exist. |
| Producer omits a consequential choice | Measure whether optional audit raises a specific, supportable question; count misses and false alarms. |
| Model invents a concern or cites unrelated evidence | Reject unsupported attribution as a finding; retain it for reviewer-quality analysis. |
| Unsupported P&ID semantics or unavailable simulation | Coverage gap, with no process-validity or physical-safety pass. |
| Application attempts release despite an open gate | Host integration test rejects release; the CLI alone cannot enforce this. |

Then compare scripted checks alone, scripts plus declared-decision review, and the same workflow with optional assumption audit on preserved deliveries. Keep the brief and evidence consistent where comparison requires it. Report confirmed additional findings, false concerns, missed seeded cases, unresolved items, review effort and repair attempts with separate denominators. Repeat model reviews when variation affects the conclusion. Independent domain assessment is needed to judge engineering relevance.

A successful pilot would show which additional questions led to useful decisions, how often the reviewer was wrong, and whether the extra review burden was justified. A larger software-test count or a more elaborate report would not establish that outcome.
