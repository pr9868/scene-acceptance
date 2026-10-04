# Scene Acceptance 0.5.0

October 3, 2026. This package combines the earlier local compatibility fixes with the adopter integration fixes below. The source and installable wheel are available in the [0.5.0 release](https://github.com/pr9868/scene-acceptance/releases/tag/v0.5.0). The public v0.3.0 release and pinned timing revision remain unchanged. Older experiment counts and scene-generation results retain their original runtime and scope.

## What callers can now distinguish

| Situation | Result and next action | Evidence retained |
|---|---|---|
| Caller rejects the proposed interpretation | `NEEDS_REVIEW`, exit 3, `review_specification` | Reviewer, reason and separate script verdict/findings. Rejection of the brief mapping is not a command to repair the scene. |
| Malformed command or execution failure | Exit 4, with error details | Actual failures; no fabricated acceptance. Legacy `check-3d` usage errors also use 4. |
| Scene fails approved requirements | `REJECT`, exit 2, `repair_scene` in prepared reports | Per-check expected/observed evidence and subject coverage. |
| Repair introduces material/motion areas absent from the approved judge scope | Judge/both acceptance pauses for new preparation/review | Original rubric preserved, new applicability and missing questions disclosed. Checks-only reports the visual omission separately. |
| Renderer provides an MDL library absent from the local bundle | Explicit caller-attested policy can satisfy dependency availability for the pinned target environment | Full scoped receipt/hash and original native resolver issue. It does not establish shader compilation or rendered quality. |

The receipt format, checks-only and prepared examples, freshness and hash requirements are in [Runtime dependency evidence](RUNTIME_DEPENDENCIES.md). The default remains local-only: unresolved renderer libraries are unknown; ordinary missing textures fail. A `require_local` rule cannot be relaxed by a receipt. Renderer attestation is an explicit caller trust decision, not a claim of independently observed GPU execution.

Prepared scopes pin the trust policy and target environment. Enabling caller attestation during preparation requires explicit approval even without a brief. Evaluation takes the receipt, not a policy override; repaired scenes require matching fresh receipts. A different target environment needs a new preparation and approval.

## Changed versions

| Component | Current version | Change |
|---|---|---|
| Harness package | 0.5.0 | Application routing, scope drift, target-runtime receipt, release replay |
| General baseline profile | 1.2.0 | Updated evaluator identities and dependency policy support |
| `openusd`, `materials` | 1.1.0 | MDL source/dependency classification and optional caller-runtime evidence |
| `motion` | 1.1.0 | Explicit reported coordinate metric and observations |
| `nvidia.asset-validator` | 1.1.0 | Updated coverage-aware adapter distribution |
| `motion.timing` | 1.1.0 | Authored FPS fallback and timing-boundary compatibility |
| `scene.audit` | 1.1.0 | Runtime dependencies and valid out-of-playback key handling |
| `brief.measurements` | 1.2.0 | Declared pixel regions/masks and mean-error limits |
| `textures.decode` | 0.2.0 | Supported connected texture-input resolution |
| `physics.incline-worker` | 0.2.0 | Verified worker/adapter/profile identities |

Geometry, sampled connection and supplemental four-job check semantics retain their existing versions. Each pack descriptor also records implementation and dependency digests. The available catalog describes the installed providers, not an assertion that every check ran.

## Existing contracts and evidence

Exact version pins remain enforced. The evaluator does not silently migrate old contracts. Prepare/bind migration handles a changed approved application scope explicitly. For standalone historical contract examples, propose version changes in a new copied bundle:

```bash
python -m scene_acceptance.contract_upgrade \
  --bundle-root evaluation/packs-v1/fixtures/material_correct \
  --out /tmp/material-upgrade-01
# Inspect contract-upgrades.json and approve the chosen policy in your application.
check-3d --bundle-root /tmp/material-upgrade-01 \
  --contract contract.json --candidate scene.usda --out /tmp/material-report-01
```

This proposal updates only known old version strings. It preserves numerical targets, enforcement flags, arbitrary unknown versions and implementation digest pins. Updating a pinned implementation remains an explicit policy decision. The proposal is not an approval record.

The current replay runners use separate copies and retain upgrade records. The older consolidation and declared-scope example also record their explicit `fresh.brief` provider migration. Original fixtures, protocols and historical reports remain unchanged. New results identify current code and contracts; matching an old outcome does not imply the old runtime had new capabilities.

## Verification and distribution

Build a noneditable wheel and install the pinned replay dependencies, then run the advertised command from the extracted source package:

```bash
python reproduce.py --out /tmp/scene-acceptance-replay-01
```

The output must be new and outside the source package. The command verifies the complete distribution manifest and installed checker identity, runs all software tests with no failures/errors/skips allowed, executes the retained replay groups and compares their outcomes and numerical physics observations. Its `verification.json` reports the actual test and replay counts. No model call or GPU render is part of this replay.

The release review packet must include the complete source ZIP, wheel, manifest, changes relative to the base commit including new files, dependency/environment identities and final reproduction output. A tracked-files-only diff is insufficient. Package-level tests establish these implementation controls; they do not establish judge accuracy, broad simulation validity or production savings.
