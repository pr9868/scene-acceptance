# Scene and specification reporting protocol

2026-10-02. Improve the report without changing existing check or acceptance semantics.

Required report sections: scene identity/revision and observed structure; general diagnostics versus specification-influenced checks and review; supplied specification origin and coverage by area; a simple results matrix; detailed evidence still accessible.

Do not infer human authorship from configured parameters or a field named explicit. Support explicit provenance and bounded coverage declarations in hashed contract/review inputs. Absent provenance means unrecorded, not human; absent specification maps mean coverage unknown, not complete or zero. Unknown custom checks remain unclassified. Runtime evidence is an execution method and can belong to a specification check; do not count it again as a separate test category.

Freeze expected checks: classification groups partition selected checks; warnings/unknowns/errors/no-applicable are distinct; required/advisory preserved; mapped requirements cannot become fully covered merely because checks pass; unknown check IDs and unsupported declarations are rejected. Preserve all current fixtures and expected verdicts. Test scene identity when admission fails, no task spec, explicit human/preset origin, incomplete mapping, finite motion plus unresolved continuous requirement, and legacy reports.

Verify JSON/CSV/HTML/Markdown consistency, safe escaping, phone/desktop layouts and installed-package operation. Use fresh output directories for examples; preserve prior reports. No original scene repair, new model/GPU work, release or publication.
