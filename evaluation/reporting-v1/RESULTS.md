# Reporting and integrated article checks — local development verification

This implementation adds explicit subject accounting, scene inventory, coverage by area, a 27-check reusable baseline, built-in article packs and portable HTML/Markdown/CSV/JSON reports. Original contract verdict semantics are preserved; report display distinguishes warnings, provider skips and absent subjects. Batch reports retain process failures as evaluation errors.

- Full suite: **304 passed, 3 skipped** (the optional external studio_mesh_pack example is absent).
- All **26 preserved article controls** reproduced their expected decisions under the integrated implementation. The 51 article regression tests are included in the full suite, not additional independent trials.
- Provider parity tests compare all seven instrumented NVIDIA rules against direct provider execution on mixed passing/failing geometry. The missing-normal regression caught an early instrumentation error; fixed callbacks preserve the original provider identity and findings.
- Reports verify all exported pointers and file hashes in regression fixtures. Count equations reconcile, no-mesh cases contribute zero mesh passes, unsupported images and missing motion clocks remain visible, and third-party providers without denominators remain unmeasured.
- A fresh wheel supplied the baseline profile, all bundled article packs and the isolated worker. Valid/corrupt textures, a separated connection, and passing/failing simulations matched expectations. Third-party runtime dependencies were reused from the pinned development environment; this is not a fresh dependency-resolution test.
- An isolated Chrome session checked the report at desktop/mobile widths, a filtered result, attention filtering, JavaScript errors and document overflow. Separate owner-specific saved-scene replay evidence remains private outside this repository.

The compact [verification record](verification.json) and [full suite output](tests-final.txt) are retained here. Replay with the commands in [REPORTING.md](../../docs/REPORTING.md). These are assistant-authored development tests, not independent validation or a model reliability benchmark. No release or publication occurred.

## Development correction retained

The first attempted callback instrumentation used a subclass. Upstream requirement registration rejected that identity; a subsequent attempt preserved issue identity but upstream filtering then omitted the finding. The existing missing-normal rejection test caught both failures. The implemented approach observes the original class callback under a lock and restores it in a finally block. Direct-provider parity tests verify that instrumentation does not change the original issues. Neither failed approach was used in the completed saved-scene replay.
