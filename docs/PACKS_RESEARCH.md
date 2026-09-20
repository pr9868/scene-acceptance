# Pack implementation: upstream choices and tested boundaries

Research and implementation on 19 September 2026 Pacific / 20 September UTC. The installed implementation and package metadata are stronger evidence for exact API availability than unversioned documentation.

## Reuse decisions

**OpenUSD 25.11.** Retained the existing pinned version and native `UsdValidation.ValidationRegistry`. The native adapter selects validator IDs explicitly and records their issues. `UsdShade.MaterialBindingAPI.ComputeBoundMaterial` supplies composed binding resolution; `UsdGeom.XformCache` evaluates requested world transform origins. These are measurements of declared scene state, not proof of external truth. The native catalog is retained with the evaluation environment.

Sources: [OpenUSD validation framework](https://openusd.org/release/api/md_pxr_usd_validation_usd_validation__r_e_a_d_m_e.html), [material binding API](https://openusd.org/release/api/class_usd_shade_material_binding_a_p_i.html). Live documentation can describe APIs newer than this pinned runtime.

**NVIDIA USD Validation 1.20.0.** First inspected the publicly installable older `omniverse-asset-validator==1.18.0`, whose standalone module differs from the old Kit API. The newer public `usd-validation-nvidia==1.20.0` exposes `usd_validation_nvidia.ValidationEngine(init_rules=False, variants=False)` and `CategoryRuleRegistry`. The adapter uses this pinned version, enables only the requested rules and never invokes `IssueFixer`. It preserves `ERROR` versus `FAILURE` and makes warning treatment a contract parameter. Package installation and catalog evidence are retained. The deprecated older package is excluded from the clean release environment.

Sources: [NVIDIA Asset Validator documentation](https://docs.omniverse.nvidia.com/kit/docs/asset-validator/latest/index.html), [public versioned package](https://pypi.org/project/usd-validation-nvidia/1.20.0/). Exact execution was checked against the installed package source and a fresh packaged install, not inferred from the web documentation. Discoverable rule count is not a claim that every rule has been exercised on every admitted representation.

**SimReady.** Public metadata confirms `simready-validate==2026.7.1` is available on PyPI at the time of this check. An older inspected guide still describes internal distribution; preserve that source history, but do not repeat it as the current availability conclusion. A dependency-resolution dry run found the new validator and profile libraries. This project does not yet load SimReady profile definitions or run its benchmarks. Those need approved specifications, a pinned environment and a consuming task. No certification is inferred from the NVIDIA rule adapter.

Sources: [public versioned package](https://pypi.org/project/simready-validate/2026.7.1/), [SimReady Foundation](https://github.com/NVIDIA/simready-foundation), [versioned benchmark guide](https://nvidia.github.io/simready-foundation/2026.06.0/guides/benchmark/benchmark.html). The public metadata and dry-run dependency record are retained in the evaluation evidence.

**Third-party extensions.** [Python distribution entry points](https://packaging.python.org/en/latest/specifications/entry-points/) supply installed pack discovery. Metadata discovery does not import the factory; an explicit caller allowlist loads it. A complete separate polygon-budget package tests the real install/discovery path. Pack provenance includes versions, declared source hashes, parameter schemas and dependency identity. These are inspectable records for trusted code, not a hostile-plugin sandbox.

## Why this core remains small

The added value being tested is combining consuming requirements, preserving evidence and identifying uncovered obligations across providers. Native USD validity, a particular shader binding and a polygon budget can all matter to one use, without being the same check. A small script remains a credible solution to a stable single-purpose task. Reusability does not prove a cost or accuracy advantage.

The local implementation deliberately stops short of a plugin marketplace, renderer deployment, distributed scheduler, universal hallucination score or automatic repair loop. Those would add work without establishing more acceptance evidence in this experiment.
