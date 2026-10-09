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
| 8 | Measure triage value | Protocol, unlabeled case packet and scorer prepared. Real model runs wait for domain labels fixed first. Software controls do not measure model quality. |
| 9 | Independent producer trial | Retain the existing protocol. Needs an independently authored brief and outside assessment; another run by this implementation agent cannot supply that independence. |
| 10 | Validator + human baseline | Included in the evaluation protocol. Requires recorded human work, comparable scope and a separate reviewer/order control. |
| 11 | Cost per delivery | Application invocations record elapsed time, available provider usage and optional caller cost context. A ledger groups all supplied attempts; unknown effort/cost stays null. Final acceptance remains owner-recorded. |
| 12 | Discover undeclared assumptions | Defer implementation until triage evaluation. A future `audit` proposes cited questions only. A diverter holdout must remove revealing captions, filenames, feedback and decision records, and include repaired/valid variants. |
| 13 | State between events | Implemented `behavior.state.agreement` for held discrete USD attributes and an optional activation condition. Caller must provide and justify the expected state. |
| 14 | Clearance / interference | Useful specialist extension. Requires representation, tolerance, approximation bounds and independent geometry controls; a bounding-box overlap is not mesh clearance. |
| 15 | Guaranteed moving connections | Defer until a sound conservative motion/error bound exists. Adaptive sampling alone cannot prove an arbitrary path stays connected. Keep existing sampled coverage explicit. |
| 16 | Viewer performance | Useful caller-evidence adapter next. Require named viewer, hardware, camera path, resolution, warm-up and measurement method. A prim count cannot predict FPS; draw callbacks are not necessarily rendered FPS. |
| 17 | Process connectivity | Implemented `process.connections.match` for tags, ports, direction and directed relationships against an explicit list. P&ID extraction, fluid simulation and physical connection geometry remain outside it. |
| 18 | SimReady / PhysX adapter | Fits the architecture. Requires access to a specific engine/profile and retained passing/failing runtime controls. Keep current fixed CPU example until a real adapter is validated. |
| 19 | Ramp creep diagnosis | Separate numerical study, not a retune of acceptance until it passes. Compare solver changes and settled behavior with frozen criteria and retain the original result. |
| 20 | Color/orientation normalization | Useful after defining comparison policy: raw pixels, displayed orientation or color-managed appearance. Do not silently change historical pixel-comparison semantics. |
| 21 | Broader USD composition | Valuable larger reader project. Add each feature with dependency, identity and negative tests; do not relax admission globally. |
| 22 | Referenced-layer metadata | Plan a declared-policy pack. Define how units/axis metadata affects composition versus caller-required conversion before reporting a mismatch as a scene defect. |
| 23 | Dependency cross-check / UDIM | Plan differential tests against OpenUSD plus explicit tile expansion budgets. Resolver dependencies and texture tiles need distinct coverage. |
| 24 | Native USD isolation | Important deployment hardening. Use a supervised process boundary and platform-specific resource limits; in-process deadlines are cooperative, not a sandbox. |
| 25 | Native PDF briefs | Useful ingestion extension with page/region provenance and rendering controls. Current text/image conversion remains explicit. |
| 26 | Three README paths | Implemented. Detailed reference moved under docs; checks, reviewed brief and full review each have a starting path. |
| 27 | PyPI and Linux | Linux added to the reproduction workflow. Packaging exists; PyPI publication remains a release task needing registry ownership and a tested distribution. No unperformed Linux or PyPI success claimed. |
| 28 | Kit / Blender integration | Defer UI-specific clients. The library/CLI and caller evidence contract should stabilize first; integrations should share that boundary. |
| 29 | Consumer CI | Added an example with read-only permissions, an explicit release pin and reports retained on failure. Consumer must protect acceptance policy. |
| 30 | Revision diff | Already present via `--previous-run`; now distinguishes regression and newly unresolved evidence under unchanged scope. Changed scope is not claimed as a fix. |
| 31 | Formatting / typing | Apply readable structure to new modules. Avoid an unrelated repository-wide rewrite in the correctness change. Broader formatting remains separate work. |
| 32 | Helper consolidation | Defer broad refactoring until shared semantics are proven. Decoder limits and comparison modes differ; merging similarly named helpers blindly can alter policy. |
| 33 | Fixture-only registry packs | Keep discoverable for frozen replay compatibility; they run only when selected, not in the default baseline. A later opt-in catalog migration needs explicit compatibility handling. |

The state and process controls are constructed regression cases. They do not rerun or independently assess the original large distribution-centre scene. The public two-scene evidence collection lacks the complete scenes and custom evaluator needed for that replay.
