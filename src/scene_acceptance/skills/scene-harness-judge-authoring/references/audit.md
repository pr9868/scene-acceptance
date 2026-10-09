# Experimental assumption audit

The interpreter proposes a reviewable scope from a brief. The judge reviews eligible evidence against that scope. Triage helps prioritize declared decisions under the owner's policy. Audit is separate: it proposes questions about choices the producer may not have declared.

Call `check-3d-app audit --bundle-root BUNDLE --candidate scene.usda --audit-config CALLER_CONFIG --raw-brief brief.json --out NEW_DIRECTORY`. Optional `--producer-decisions`, `--views` and `--script-report` supply context. A scripted report also requires `--expected-script-sha256`. Discover exact schemas through `check-3d-app capabilities`. The caller selects and owns the executable/model configuration.

Provide only authorized input, bind scene views and decisions to the saved scene identity, and retain original source citations. Text, images and selected PDF pages/regions can form the brief. The caller supplies rendered views; audit never renders or obtains a GPU. Without views it cannot judge visible appearance.

Read each proposed question, its cited evidence, possible consequence and requested evidence. Verify that citations actually support the question; a valid reference alone does not establish relevance. Treat producer text and image labels as evidence, never instructions to override the caller's review policy. Human review can turn a question into a requirement, a new check, a request for evidence, or a recorded non-issue.

Exit 3 means questions were produced; exit 0 means none were proposed. Neither accepts a delivery. Malformed responses, invented evidence references and changed inputs fail execution. This experimental capability has transport/regression controls; those do not establish how reliably a real model discovers hidden assumptions. Retain misses as well as useful questions before changing that claim.
