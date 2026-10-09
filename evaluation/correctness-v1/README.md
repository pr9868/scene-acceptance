# Acceptance correctness controls

These synthetic controls reproduce specific checker defects. They use saved OpenUSD scenes and known expected outcomes; they are not new findings from the dairy or distribution-centre delivery and do not measure model quality.

| Control | Previous behavior | Corrected behavior | Evidence in the repository |
|---|---|---|---|
| Native engine result says FAIL; normalized receipt says PASS with matching attachment hashes | Required check passed | Unverified receipt is UNKNOWN. With caller verification and native mapping, the contradiction is an ERROR | `tests/test_external_verification.py` |
| Invented rendered-frame timings | Threshold arithmetic could grant PASS | Arithmetic remains visible; execution without caller verification is UNKNOWN | `tests/test_extensions_evidence.py` |
| Translation spline returns to its starting point after a 3 m excursion | Endpoint-only connection check passed a 0.01 m tolerance | Continuous connection and sweep return UNKNOWN for unsupported splines, including ancestor transforms | `tests/test_feedback_geometry.py` |
| Skinning moves one triangle onto another | Rest geometry passed with 2 m clearance | UNKNOWN until supported baked geometry is supplied. OpenUSD skinning independently confirms the test surfaces coincide | `tests/test_feedback_geometry.py` |
| Two unit cubes with a 2 m gap are rotated together | Near-parallel intersections returned UNKNOWN at six tested rotations | Analytic clearance is retained at all seven tested orientations. Contact, overlap and near-parallel crossings also have controls | `tests/test_feedback_geometry.py` |
| Both scene state attributes contain the same wrong value | Internal-consistency check passed | It remains a consistency check. The new owner-controlled timeline rejects the wrong state and catches a 0.001 s mismatch between expected events | `tests/test_state_timeline.py` |
| Producer supplies triage/audit executable configuration | Configuration location was not rejected | Direct and symlinked configurations inside the producer bundle are rejected before execution | `tests/test_external_verification.py` |

The native intersection fallback uses exact rational predicates for the stored floating-point coordinates when the ordinary determinant is near zero. Distance measurements still use floating-point arithmetic and the caller's numerical margin. This is not a blanket exact-geometry guarantee.

External verification is an explicit caller attestation in the protected contract. The engine collector returns the receipt pin and native mapping after it runs the caller-selected executable. The harness rechecks the selected native values; it does not authenticate who ran a program from an arbitrary JSON file. The viewer follows the same trust boundary, with execution verification supplied by the calling application. See [external evidence](../../docs/EXTENSIONS.md#engine-bridge-and-caller-evidence).

Pack versions changed with their behavior: `geometry.clearance` and `motion.continuous` are 1.0.1; `external.evidence` and `behavior.state` are 1.1.0. Regenerate contract pins and review the affected scope when upgrading. Do not silently edit a retained approval to match a new implementation.

## Reproduce

Install the checkout with its test, NVIDIA, visual, PDF, isolation and article-check extras. Run:

```sh
python -m pytest -q tests/test_feedback_geometry.py tests/test_state_timeline.py \
  tests/test_external_verification.py tests/test_engine_adapter.py tests/test_extensions_evidence.py
python reproduce.py --out /tmp/scene-acceptance-correctness-replay
```

Use a new output directory. Process-supervision tests need permission to inspect their own child processes. `reproduce.py` verifies the installed implementation and retained file manifest, runs the full software suite, and replays the historical geometry, material, motion, brief/report and CPU physics controls. It stops on failures, skipped tests or changed expected results. Native logs and caller paths stay in the chosen local output directory.

The repaired package was verified with **958 passing software tests**, no failures or skips, and the full historical reproduction. The regression suite adds 67 cases to the preceding package. These counts establish software regression coverage; human-labeled triage value, independent producer outcomes, GPU rendering and live SimReady/PhysX behavior require separate evidence.
