# Evaluation packs: version 0.3.0 results

19 September 2026 Pacific / 20 September UTC. Local development evidence, not independent validation or a model benchmark.

## What was implemented and exercised

Contract v2 selects checks from versioned packs. The local core validates their parameters, handles prerequisites, records provider/input identity, rejects invalid output and produces common JSON/HTML findings. A separately packaged `studio.mesh-budget` extension was installed and explicitly enabled without editing the core.

Five bundled packs cover native OpenUSD validators, the legacy geometry/edit evaluator, material structure, sampled motion and selected NVIDIA USD Validation rules. The NVIDIA dependency is optional. The catalog found 25 OpenUSD validator entries and 40 NVIDIA rules in the tested installation; those counts describe discovery, not verified coverage of every rule.

## Executed checks

| Verification | Observed result | Evidence |
|---|---|---|
| Fresh non-editable wheel, Python 3.12 / macOS arm64 | 195 automated tests passed; includes the original 137 and new conformance/case tests | [Test log](evidence/scene-packs-final-tests.txt), [verification record](evidence/verification.json) |
| Frozen pack cases | 22/22 expected decisions matched: 9 accept, 7 reject, 2 insufficient, 4 evaluation error | [Case report](runs/final/index.html), [summary](runs/final/summary.json) |
| Existing mesh cases | All 32 decisions and per-check statuses unchanged | [Replay](runs/mesh-regression/summary.json) |
| Base install without NVIDIA or the example extension | Material pass and motion failure worked; requested missing providers returned evaluation errors | [Base-install record](evidence/scene-packs-base-install-verification.json) |
| Third-party extension and installed CLI | Combined profile accepted with all six pack families represented across the catalog; this profile selects five packs | [Installed CLI report](evidence/installed-cli-report/report.html), [catalog](evidence/scene-packs-installed-catalog.json) |
| Source snapshot | Original v0.2 source/schema digest preserved; installed v0.3 code matches staged source | [Verification](evidence/verification.json); original v0.2 source archive retained separately |

These counts overlap. The 195 software tests include the demonstration fixtures and prior regression cases; they are not 195 independent agent trials. The combined profile uses OpenUSD, materials, motion, NVIDIA and the external budget pack; geometry compatibility is exercised separately.

## Retained failure and fix

The first 22-case replay matched 19 expected decisions. Three cases incorrectly accepted: a missing texture, missing texture without a material check, and an undeclared texture dependency. The reader used layer-level dependency APIs that did not enumerate the asset path authored in a shader attribute.

The fix explicitly inspects asset-valued attributes, including arrays and time samples, before stage composition. Referenced paths must be declared and local; missing files are retained as missing evidence. The material-delivery check reports an absent referenced file as a failure. The original fixtures and expected labels did not change. The [first reports](runs/first/index.html) and [corrected replay](runs/texture-fix/index.html) are retained.

This is a harness implementation defect found with constructed scenes. It is not a model hallucination.

## Distinct observations for future articles

- **Materials:** the wrong resolved binding rejects under the material requirement, yet accepts under the otherwise identical format-only requirements. The evaluator cannot supply an omitted requirement. See [wrong binding](runs/final/material_wrong_binding/report.html) and [omitted requirement](runs/final/omitted_material_requirement/report.html).
- **Motion:** an incorrect midpoint rejects when sampled; the same midpoint error accepts when only the two correct endpoints are checked. Samples do not establish continuous coverage. See [midpoint failure](runs/final/motion_wrong_midpoint/report.html) and [endpoint-only acceptance](runs/final/endpoints_miss_midpoint/report.html).
- **NVIDIA reuse:** selected upstream rules found missing stage metadata and absent normals. Original rule names, severities and issues remain in the common result; no fixer was invoked. See [missing normals](runs/final/nvidia_missing_normals/report.html).
- **Third-party policy:** the separately installed polygon-budget pack accepts a mesh within its limit and rejects it above the limit. Installation without caller approval does not load the pack and cannot pass its required check. See [budget rejection](runs/final/third_party_budget_exceeded/report.html).
- **Core behavior:** required unknowns, exceptions, malformed outputs, prerequisites, invalid parameters, changed inputs and changed pack identity remain visible. A required failure can coexist with unresolved checks; that result rejects but reports incomplete evidence.

## What this does not establish

The same coordinator designed the harness and labeled these cases. No new agent-generation, renderer, simulation or robot-training run occurred. Material delivery is not rendered appearance. Sampled origins do not establish collision-free or physically possible motion. A selected upstream physics rule would establish only its own configuration requirement, not parameter provenance or real-world accuracy. The SimReady profile library and runtime benchmark are not integrated by this release.

The original competent-script comparison still ties within shared scope. No measured productivity, latency, review-time or general detection advantage is claimed. The pack architecture demonstrates reuse and extension mechanics; broader practical benefit needs consuming tasks and independently supplied briefs.

The in-process API accepts trusted installed code. File and layer mutation checks do not provide a hostile-plugin sandbox, resource scheduling or per-check enforced timeouts. Those belong in a future execution boundary before adding untrusted or expensive runtime providers.

Publication note: this public copy resolves the included evidence links. The separately retained v0.2 source archive is outside this distribution; its preservation result and digest are recorded in the verification record.
