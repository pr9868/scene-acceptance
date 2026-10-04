# Renderer-provided MDL dependencies

Some USD scenes refer to an MDL library that the consuming renderer supplies,
such as `OmniPBR.mdl`. A local file check cannot establish that the target runtime
has it. By default, the harness leaves a recognized unresolved MDL source asset
`UNKNOWN`; it does not search outside the admitted bundle or launch a renderer.

A calling application can opt into **caller-attested dependency availability**.
The application must independently select the target environment identity and
supply a receipt for the exact saved scene and authored MDL references. The
harness checks the receipt's identity, completeness for each dependency,
freshness and file integrity. It does not independently verify the caller's
assertion, compile the shader or inspect a render.

## Calling the application boundary

For a direct check, pass the target environment SHA separately from the receipt:

```sh
check-3d-app check --bundle-root ./scene --candidate scene.usda --out ./report \
  --runtime-dependency-policy caller-attested \
  --runtime-environment-sha256 "$TARGET_ENVIRONMENT_SHA256" \
  --runtime-dependency-evidence ./renderer-dependencies.json
```

The equivalent library call is
`evaluate_scene(bundle_root=..., candidate=..., out=...,
runtime_dependency_policy="caller-attested",
runtime_environment_sha256=..., runtime_dependency_evidence=...)`.
The optional mapped brief uses the same receipt handling. `invoke("check", ...)`
adds the application JSON envelope and optional verified replay.

For prepared work, select the trust policy and environment when preparing:

```sh
check-3d-app prepare --bundle-root ./scene --candidate scene.usda --out ./prepared \
  --runtime-dependency-policy caller-attested \
  --runtime-environment-sha256 "$TARGET_ENVIRONMENT_SHA256"

# Review the generated scope and use its actual scope_sha256 in this command.
check-3d-app approve --preparation ./prepared --out ./approval.json \
  --expected-scope-sha256 "$SCOPE_SHA256" --reviewer "Application owner" \
  --reason "Reviewed the requirements and the selected target-runtime trust policy"

check-3d-app evaluate --preparation ./prepared --out ./run \
  --approval ./approval.json \
  --runtime-dependency-evidence ./renderer-dependencies.json
```

The policy and environment are part of the approved scope, including when no
brief is supplied. Evaluation accepts a new receipt but cannot change those
scope values. A missing or rejected approval prevents acceptance. To select a
different environment or trust policy, prepare a new scope and approve it.
Binding a repaired candidate preserves the policy and environment; the receipt
must be refreshed for the repaired scene's identity.

## Receipt format

The packaged schema is `runtime-dependency-receipt-v1.schema.json`. This is an
illustration, not usable evidence: replace every placeholder with values recorded
by the calling application in its target runtime.

```json
{
  "schema_version": "1.0",
  "kind": "renderer-mdl-dependency-attestation",
  "scene_sha256": "<artifact-set SHA256 from the preparation or scene inventory>",
  "environment_sha256": "<independently selected target-environment SHA256>",
  "renderer": {"name": "<renderer>", "version": "<exact version>"},
  "runtime": {"name": "<runtime>", "version": "<exact version>"},
  "provenance": {
    "attested_by": "<application or operator identity>",
    "source": "<how and where the resolver observation was obtained>",
    "observed_at_utc": "<UTC ISO timestamp, including Z or +00:00>",
    "expires_at_utc": "<UTC expiry after the observation>"
  },
  "dependencies": [{
    "layer": "scene.usda",
    "attribute": "/World/Material/Shader.info:mdl:sourceAsset",
    "identifier": "OmniPBR.mdl",
    "source_type": "mdl",
    "resolved_identifier": "<identifier reported by the target runtime>",
    "library_sha256": "<SHA256 of the library observed by that runtime>"
  }]
}
```

The scene hash covers the admitted USD/dependency closure, including missing
dependencies. It is not just the root `.usda` file hash. Layer and attribute paths
are the exact authored paths, including referenced-layer paths before namespace
remapping. Every unresolved authored reference to a dependency needs a matching
receipt row before that dependency can pass under this policy. A receipt may
cover only some dependencies; the others remain unresolved.

The application chooses and manages its environment identity, for example the
SHA256 of a canonical environment manifest containing renderer/runtime versions,
resolver configuration and library inventory. Pass the expected identity from
the application's selected target environment; copying it blindly from an
untrusted receipt defeats the identity check. The harness checks the pin against
the receipt. It does not attest to the environment manifest itself or
authenticate the receipt's author.

## What changes in the report

| Condition | Result |
|---|---|
| Default `local-only` policy, recognized missing MDL library | `UNKNOWN`; further evidence is needed |
| Opt-in policy, no receipt or incomplete coverage | Uncovered dependency remains `UNKNOWN` |
| Exact scene, target environment and authored references match a fresh caller receipt | Availability can pass as `caller_attestation` |
| Pack explicitly requires local libraries with `runtime_libraries: "require_local"` | Missing local file still fails |
| Missing texture, ordinary asset, unrelated native error or wrong shader identity | Still fails; an MDL receipt cannot clear it |
| Malformed, duplicate, mismatched, expired, future-dated or modified receipt | Evaluation error; no acceptance |
| Judge-only mode | Dependency policy is not assessed; supplying a dependency receipt is a usage error |

The full receipt, its file SHA, environment pin, provenance and accepted
dependency count appear in `evaluation.json` and the HTML report. Native USD
messages retain their original severity and text. An accepted missing-library
condition adds a separate policy assessment and the receipt supporting it; it
does not rewrite the original local-resolver error or claim that a file exists
in the bundle.

Receipts are limited to 256 KiB and 256 reference rows. Observation and expiry
must include UTC; future observations and expired receipts are rejected. The
same freshness and hash checks apply when reusing a completed application run.
If a receipt expires during evaluation, the run cannot succeed.

This route establishes only the availability condition the caller attested to.
Rendered appearance, shader compilation, texture correctness and simulation
behavior still require their own evidence and checks.
