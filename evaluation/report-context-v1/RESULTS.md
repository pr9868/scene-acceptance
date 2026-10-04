# Scene and specification report verification

The report now explains the scene/revision and observed structure, separates general diagnostics from checks linked to supplied specifications, records provenance without inferring human authorship, and shows specification coverage separately from outcomes. Existing check/verdict semantics and original fixtures are preserved.

| Verification | Result |
|---|---|
| Full suite from an installed wheel | 394 passed, no skips; includes 14 new reporting controls |
| General panel example | 27 general checks; no task specification map or human source invented |
| Wrong readable texture | Decode passes; preset pixel-content check fails and artifact rejects |
| Motion review | Required sampled checks pass; continuous-motion obligation remains UNKNOWN and declared scope NEEDS_REVIEW |
| Synthetic human-source example | Two explicit provenance fields produce two human-linked check entries; labeled as a software control, not actual human requirements |
| Missing evidence / scene | Candidate identity retained where known, inventory unavailable rather than zero, unknown checks remain unknown |
| Unknown/legacy provider | Unclassified, rather than assumed general or human-specified |
| Partial coverage | A completed mapped check does not turn a partial/unreviewed map into full coverage |
| Compatibility replays | All 22 provider, 32 mesh, 17 timing and 21 consolidation outcomes matched; existing article evidence replay passed |
| Browser | One overview, five matrix categories; search works; desktop 1440 px and phone 390 px with contained table scrolling, no document overflow or JavaScript errors |

Four fresh example report directories are produced by `run.py`. It hashes and verifies 67 original fixture files unchanged, writes to new directories, and never runs producer code. The full `reproduce.py` workflow now includes these examples. Test counts overlap the replay cases and are not independent experiments.

See `verification.json` and `tests-final.txt` for compact final receipts. The latter omits the temporary JUnit output location; the original log remains in private working evidence. Source digest: `3693b11cf12411d7a122154cab254cda5fb6c831ca8770f350af93aa8841d409`. The main package was installed from a wheel, while previously pinned dependency installations were reused rather than freshly resolved.

Provenance labels and coverage extents are caller declarations. They are included in hashed inputs but are not authenticated or independently judged for relevance. General checks can be selected by a human; “general” means no task-specific target is needed. A native rule used to support a declared specification appears in its linked-specification category. Review obligations remain separate from automatic-check counts. Missing specification maps and unrecorded sources are not treated as complete coverage or proof that no brief exists elsewhere.

This is a local development change. No new model call, GPU job, site edit, push, release or publication occurred.
