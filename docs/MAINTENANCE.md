# Keeping the harness consistent

The README describes the current development checkout and names the latest tagged release separately. A capability on `main` does not make it available in an older release. Consumer applications should pin a reviewed commit or tag.

## Sources of truth

| Subject | Authoritative source | What must agree |
|---|---|---|
| Package version and dependency requirements | `pyproject.toml` | Runtime version, test locks and installed metadata |
| Check behavior and parameters | Pack declarations and evaluator code | Generated catalog, public schemas, controls and current guides |
| CLI and application response | Parsers and application schemas | README commands, protocol guide and packaged skills |
| Original study result | That study's retained inputs, protocol and reports | Claims about that study; never replace them with today's results |
| Current capability and limitations | README and linked adopter guides | Avoid a second inventory in the detailed reference |
| Model quality and usefulness | Frozen cases, independent labels and measured runs | Passing software tests do not establish model accuracy or time saved |

Historical design proposals and release records retain their dates and versions. Their status lines must point readers to current instructions. Correct stale present-tense guidance; do not rewrite old failures, approval identities or experimental outcomes.

## Before merging a behavior change

1. Add a regression that exercises the caller-visible failure and a passing control. Keep scene defects, missing evidence and evaluator errors distinct.
2. Update the runtime version. Bump affected pack versions when their measurement semantics change. Existing scope and implementation pins must remain explicit; use reviewed migration rather than silent upgrades.
3. Regenerate schemas and catalog when declarations change: `python scripts/update-public-schemas.py`. Run `python scripts/check-maintenance.py` for version/lock/catalog/schema consistency and local links in current guides and packaged skills. This checks mechanical consistency, not the truth of prose.
4. Review the README path, relevant guide, example and packaged skill together. Exercise changed commands. Check preparation readiness separately from saved-proposal status, scope approval and acceptance.
5. Audit exact dependencies against current advisories in a separate audit environment. Revalidate changes deliberately; do not automatically float runtime dependencies. The current lock is tested with Python 3.12 on macOS and Linux. Other Python/platform combinations are not established by `requires-python` alone.
6. Review every new public file for private evidence, credentials and local paths. Verify author/committer metadata uses the approved public identity, including after merges. Update the distribution manifest only after reviewing the file list. Then build both archives and run `python scripts/verify-distributions.py dist/*.tar.gz dist/*.whl`.
7. Install the built wheel in a clean environment and run `reproduce.py` from the source archive. No failures or skipped tests are allowed in full reproduction. Verify the corresponding macOS/Linux CI run before calling the change published and tested.

The GitHub Actions workflows pin reviewed action commits and install the built wheel before replay. The PyPI workflow is manual and remains unused; installation is through GitHub. Updating an action pin needs review of its release notes and a passing run.

## Open maintenance and adoption risks

| Priority | Risk | Next useful work |
|---|---|---|
| High before making model-value claims | Triage calibration, independent audit discovery and reviewer-time savings are unmeasured. Small rendered-sign controls establish only their stated cases. | Collect owner/domain labels before repeated model runs; retain holdouts and active review time. |
| High for an untrusted service | Packs, adapters and native readers run trusted local code. Supervision is not filesystem/network isolation. | A service adopter supplies OS/container boundaries and controls model credentials and uploaded inputs. |
| Medium before engine-specific claims | External engine transport is tested; a specific SimReady/PhysX installation and live Blender workflow still need qualification. | Run compliant, violating and missing-evidence cases in that actual application/version. |
| Medium as orchestration grows | Preparation, triage and report modules still combine several responsibilities. Shared capture planning now removes one duplicated policy path. | Extract one coherent seam when behavior changes require it, with caller-level regressions; avoid a broad rewrite during a correctness release. |
| Medium for long-term support | The development candidate moves faster than the latest tag. Tested dependencies are pinned and can acquire advisories. | Review advisories and compatibility at each release; tag a supported release only after its qualification, rather than relabelling the candidate. |

Known build/test advisories prompted updating setuptools and pytest. Sources: [setuptools advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-h35f-9h28-mq5c), [pytest patch release](https://github.com/pytest-dev/pytest/releases/tag/9.0.3). A clean dependency scan means no known advisory was returned for those queried versions; it is not a security certification.
