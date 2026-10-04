# Bounded producer-to-acceptance trial

Status: prepared, not executed. An independently supplied edit brief and an external assessment are still needed. The harness tests and constructed timing controls are not substitutes for either. Do not mark this trial independent on the basis of a second calculation written by the evaluator's author.

## Question

Can a producer deliver the requested edit under an unchanged application contract, and does access to the same acceptance checks before submission improve the work through acceptance?

Begin with one bounded task supported by the reader and selected packs. Do not expand the pack catalogue to make the trial appear broad. Keep the intended use, baseline, units, timing, permitted edits and protected properties explicit.

## Freeze before production

1. Obtain the brief from the owner or another source independent of the harness test design. Record its source and original text.
2. Map every mandatory requirement to a check, supplied reference or explicit uncovered condition. Have the owner review the mapping before running the producer. A missing mapping remains an open requirement; a schema-valid contract does not close it.
3. Freeze the baseline, dependencies, approved contract, expected outcomes and allowed tools by hash. Protect the authoritative copies in the calling application; a hash alone is not access control.
4. Define the external assessment independently of the producer's success message. Retain the reviewer identity/role, assessment criteria and outcome. Do not claim human review-time savings without recorded review time.
5. Pin the requested model identifier, available tool versions and evaluation environment. Record any provider-reported model identity without inventing an unavailable backend snapshot.

## Trial arms

Use the same brief and acceptance requirements for both arms. The producer may read the contract in each; only access to prechecking differs.

| Arm | During production | Application acceptance |
|---|---|---|
| Prechecking | Producer can invoke the approved harness before submitting. Retain every invocation and its inputs. | Rerun on the delivered revision using the authoritative contract. |
| Feedback after submission | Producer uses its approved authoring tools without invoking the harness. | Evaluate the submitted revision and return the same structured findings. |

Plan two fresh initial attempts per arm, with order fixed before execution. Allow at most one repair after a rejected submission in each attempt. Do not repair an accepted result merely to search for a failure. Missing owner evidence and evaluator errors take their own paths; they are not automatically new production requests.

A competent deterministic script plus review is the baseline on this bounded job. Record its scope and preparation effort. Four producer attempts on one brief constitute a pilot, not a model ranking or a reliable estimate of failure prevalence.

## Record each attempt

Retain the exact prompt/brief, baseline and authoritative contract hashes, tool requests and responses, producer prechecks, submitted artifact/dependency hashes, application report, external assessment, revision requests and final disposition. Include failed infrastructure attempts separately rather than discarding them.

Record wall time and available token/compute usage for every stage. If price or active human review time was not measured, leave it unavailable. Do not translate unmeasured effort into a claimed saving.

## Judge the result

Report first-attempt acceptance and final independently accepted jobs per attempted brief. Compare the harness verdict with the external assessment to identify false acceptance and unnecessary blocking. Record unresolved requirements, repair attempts and total elapsed time/usage per accepted job, including failed attempts.

Separate content defects, specification gaps, evaluator errors and infrastructure failures. A wrong artifact that passes an incomplete contract is evidence to improve that contract, not automatically a model hallucination. Reusing the same validator on both sides does not provide independent evidence that its requirements or implementation are correct.

Only revise the acceptance definition after the recorded trial. Treat changed requirements as a new protocol version and rerun retained regression cases plus cases held out of development. The evaluator never edits the submitted scene; the caller owns producer attempts and release.
