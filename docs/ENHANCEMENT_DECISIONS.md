# Enhancement decisions

This development candidate prioritizes closing real review gates, turning two observed failure classes into explicit checks, and making cost and evaluation evidence easier to collect. New capabilities remain bounded by their declared inputs. The table records the disposition of all 33 suggestions.

| # | Suggestion | Decision and reason |
|---:|---|---|
| 1 | Specific triage next action | Implemented. Review/evidence actions retain their meaning when the original scope also needs review. |
| 2 | Non-UTF-8 text | Implemented. Invalid text evidence produces a contract error. |
| 3 | Model policy paraphrase | Implemented. Response 1.1 uses `model_policy_paraphrase`; explicit 1.0 and unversioned legacy responses remain accepted. Owner policy stays separate. |
| 4 | Configured Codex notices | Implemented. Empty by default, exact-match driver allowlist; new or changed notices fail. |
| 5 | Usage exit code | Already implemented: usage errors return 4 and rejection returns 2. No compatibility flag added to restore ambiguous routing. |
| 6 | Human closure of mandatory triage | Implemented through `resolve-triage`, using existing human-review records tied to current evidence and request identity. |
| 7 | Missing controls | Added UNKNOWN/ERROR, non-UTF-8, duplicate image bytes under different IDs and FPS-only end-to-end controls. |
| 8 | Measure triage value | Protocol, unlabeled case packet and scorer prepared. Original invocation receipts, matching inputs and three distinct run IDs are required; copied results cannot count as fresh repeats. Real model-quality runs still require domain labels first. |
| 9 | Independent producer trial | Retain the existing protocol. Needs an independently authored brief and outside assessment; another run by this implementation agent cannot supply that independence. |
| 10 | Validator + human baseline | Included in the evaluation protocol. Requires recorded human work, comparable scope and a separate reviewer/order control. |
| 11 | Cost per delivery | Application invocations record wall time, available provider usage and optional caller costs. The ledger validates original receipts, rejects duplicates, replay responses and invalid currency/cost data, and preserves unknown totals. Final acceptance remains owner-recorded. |
| 12 | Discover undeclared assumptions | Implemented experimental `audit`: a separate model operation proposing cited questions only. Input identity, citation and output controls are tested. Discovery quality and the blinded original-delivery holdout are not established; an empty question list is not acceptance. |
| 13 | State between events | Implemented `behavior.state.agreement` for internal scene consistency and `behavior.state.timeline` for owner-controlled expectations and activation in the contract. Caller must review and protect the expected schedule. |
| 14 | Clearance / interference | Implemented `geometry.clearance` for triangle/Cube distance, explicit clear zones and conservative translation sweeps. Closed solids need valid oriented geometry; unsupported representations, motion and exhausted budgets remain unknown. No bounding-box overlap is presented as exact mesh clearance. |
| 15 | Guaranteed moving connections | Implemented `motion.continuous.connection` for piecewise-linear translations with static other transforms. Convexity bounds the gap across every segment. Arbitrary rotation/deformation remains unknown; numerical margins are explicit. |
| 16 | Viewer performance | Implemented a named viewer evidence pack: machine/environment, resolution, camera path, warm-up, frame count, median FPS and p95 frame time. Draw callbacks cannot pass as rendered FPS. The caller runs the viewer. |
| 17 | Process connectivity | Implemented `process.connections.match` for tags, ports, direction and directed relationships against an explicit list. P&ID extraction, fluid simulation and physical connection geometry remain outside it. |
| 18 | SimReady / PhysX adapter | Implemented caller-owned `collect-engine` bridge plus a selected-test receipt pack for profile/runtime results. It retains native JSON and uses explicit status mappings. Synthetic transport controls passed; an actual SimReady/PhysX installation and runtime controls are still needed before claiming engine validation. |
| 19 | Ramp creep diagnosis | Executed twelve fixed-input solver sensitivity runs at two time steps. Higher impratio and noslip reduce high-friction creep; the low-friction control continues sliding. Results and reproduction script are in `evaluation/solver-drift-v1`; original acceptance policy is unchanged. |
| 20 | Color/orientation normalization | Implemented opt-in linear-sRGB source comparison with declared sRGB/linear-RGB8/embedded-ICC encoding and stored/EXIF orientation. Historical stored-pixel comparison remains available with its original meaning. |
| 21 | Broader USD composition | Implemented bounded local variants, payloads, instance proxies, inherits and specializes. Admission scans unselected branches as well. Value clips, dynamic formats, remote resolvers and packages remain unsupported. |
| 22 | Referenced-layer metadata | Implemented explicit `usd.layers.metadata` policy for root and referenced layers. Reports mismatches or absent evidence; it does not silently convert units or axes. |
| 23 | Dependency cross-check / UDIM | Implemented local UDIM tile expansion with file/directory budgets and `UsdUtils.ComputeAllDependencies` cross-checks. Additional/missing tiles invalidate identity; available tiles do not prove the intended tile set is complete. |
| 24 | Native USD isolation | Implemented `check-3d-isolated` and Python `invoke_isolated`, with supervised POSIX workers, time/output/process-tree memory/CPU monitoring and Linux resource limits. Monitor failure closes execution; this is not a hostile-code sandbox. |
| 25 | Native PDF briefs | Implemented native selected PDF pages/regions, embedded text, rendered evidence and original PDF/page/region citations through preparation and audit. No OCR, CAD importer or semantic P&ID extraction. Rotated pages require an explicit normalized source revision. |
| 26 | Three README paths | Implemented. Detailed reference moved under docs; checks, reviewed brief and full review each have a starting path. |
| 27 | PyPI and Linux | Linux/macOS reproduction CI and a manually dispatched PyPI trusted-publishing workflow are configured. The owner chose GitHub installation for now. The PyPI workflow remains inactive; registry publication is not claimed. |
| 28 | Kit / Blender integration | Implemented an experimental Blender 4.2+ client for saved-USD checks and brief preparation through the external CLI. Source compilation and harness transport are checked; live Blender UI validation remains outstanding. |
| 29 | Consumer CI | Added an example with read-only permissions, an explicit release pin and reports retained on failure. Consumer must protect acceptance policy. |
| 30 | Revision diff | Already present via `--previous-run`; now distinguishes regression and newly unresolved evidence under unchanged scope. Changed scope is not claimed as a fix. |
| 31 | Formatting / typing | Reformatted the source modules consistently, including the dense orchestration and follow-up modules, and added type annotations at key public boundaries. Functional verification is separate from formatting. |
| 32 | Helper consolidation | Consolidated JSON record writing and bounded image decoding while retaining caller-specific limits and status semantics. New continuous-motion operations share clock and transform handling; older helpers with deliberately different policies are not equated. |
| 33 | Fixture-only registry packs | Moved the incline worker and four-job preset out of the normal registry/catalog. Explicitly selected contracts still load them for frozen replay; `--include-examples` exposes their catalog. Third-party imports still require approval. |

The state and process controls are constructed regression cases. They do not rerun or independently assess the original large distribution-centre scene. The public two-scene evidence collection lacks the complete scenes and custom evaluator needed for that replay.


## Qualitative review risk

The owner requested low, medium and high beneath human review. Implemented in the development candidate with built-in definitions, an optional owner rubric override, optional per-item minimum, model reason/citations, separate applied level and pending-item counts. The request and result retain the active definitions and whether their source is built-in or owner-supplied; the original policy file is unchanged. Low still needs review. Unsupported grades and legacy responses without grades stay unrated; mandatory owner minimums remain enforceable. Human approval uses the same evidence-bound closure records. Published older schemas remain available. Deterministic tests check routing and integrity; no model risk-classification accuracy is established, and the binary pilot cannot supply that result.

## First-delivery usefulness

The next development increment adds [read-only polygon/implicit geometry, explicit clearance policy, selectors, executable preflight, mechanical relationships, caller helpers and bounded model context](USEFULNESS_UPGRADE.md). Deterministic controls and replays are separate from model-quality and reviewer-time evaluation. Current reports distinguish failures from unsupported measurements and capacity gaps. Retained earlier experiments still describe their original versions and acceptance policies.
