# Checking the first delivery

The development upgrade reduces the preparation needed to measure ordinary saved geometry. It leaves source scenes untouched. Requirements, delivery policy and measurement capability remain separate: a usable evaluator should not send a producer back to change topology just to satisfy its implementation.

| Change | Caller benefit | Limit |
|---|---|---|
| Planar polygon conversion | Quads and valid concave polygons are triangulated in memory | Nonplanar, self-intersecting and degenerate faces remain unresolved; no arbitrary renderer tessellation claim |
| Implicit geometry | Cylinder and Sphere bounds; bounded tessellation for named-time clearance | Approximation error is reported; near-threshold results can remain unknown. Continuous sweeps still require Cube/Mesh |
| Surface/solid policy | An open sign can participate as a surface without being sealed | Solid-containment requirements still require oriented closed solids |
| Contact policy | A zone can explicitly allow boundary contact | Policy is owner-held; the harness does not silently shrink a zone |
| Subject selectors | Paths, subtrees, USD collections or exact tag values, with recorded exclusions | Counts are bounded; exhausted discovery remains unresolved and keeps already measured findings |
| Material attribution | Missing files are assigned to the connected material network | General dependency checks still assess the whole delivery |
| Brief measurements | Partial bounds, typed values, endpoint displacement and scalar rotation rate | Unconstrained axes are null; rendered appearance, intermediate paths and composed rotation are separate questions |
| Mechanical relationships | Declared attachment, sliding travel and projected engagement | Translation-only continuous proof; projected overlap is not load-bearing contact |
| Preparation preflight | Unsupported geometry and aggregate capture-budget gaps appear before capture | Older packs without callbacks explicitly report unavailable preflight |
| Caller tools | Content identity, preflight and image-manifest/receipt packaging through the application CLI | Caller still renders, supplies camera/visibility assertions and owns their provenance |

## Select obstacles without enumerating them

A `geometry.clearance.clear_zone` check accepts either `obstacles` or `selector`:

```json
{
  "selector": {"root": "/World/Equipment", "exclude": ["/World/Equipment/AllowedFixture"], "max_subjects": 4096},
  "zone_min_m": [0, 0, 0], "zone_max_m": [2, 1, 2],
  "time_s": 0, "representation": "surfaces", "contact_policy": "allow",
  "numeric_margin_m": 0.0005, "max_triangle_pairs": 250000
}
```

This declares the selected subtree. It does not establish that equipment outside that subtree is irrelevant. Hidden geometry is included; render visibility is not an exemption. The report records selected and excluded paths. New deliveries resolve selection again, so a new obstacle under the subtree participates automatically.

`contact_tolerance_m` is an optional physical boundary allowance, permitted only with `contact_policy: "allow"`. Its default is zero. For example, an owner-selected 0.001 m allowance permits that boundary band while checking the remaining interior. It is separate from numerical uncertainty; it must not be chosen merely to obtain a pass. The report retains the original volume and evaluated interior.

`representation` defaults to `closed-solids` and `contact_policy` to `forbid`, preserving existing contracts. Changing either changes acceptance policy. Keep that separate from a geometry repair when comparing results.

## Declare the relationship you need

`mechanical.relationships.attachment` compares two owner-chosen local anchor points over an interval. `sliding` allows motion along a declared world unit axis while bounding lateral separation and signed travel. `engagement` bounds overlap of the parts' projections onto that axis. Combine projected engagement with alignment/clearance as appropriate; overlap alone does not establish physical connection.

The continuous argument applies to saved piecewise-linear translations with static other transforms. Unsupported rotation, splines and deformation remain unresolved. A passed relationship covers its named parts, anchors and interval, not every connection in an assembly.

## Use the public caller tools

```sh
check-3d-app identify --bundle-root delivery --candidate scene.usda
check-3d-app preflight --bundle-root delivery --candidate scene.usda --checks-file caller/checks.json
check-3d-app package-evidence --preparation prepared --expected-plan-sha256 HASH --view-spec caller/views.json
```

`checks.json` is an array of selected check records (`id`, `pack`, `check`, `parameters`). Preflight inspects prerequisites without granting acceptance. The evidence specification has `views` (the public view schema, omitting generated hashes) and `requests` (capture request ID → view ID list). Paths are relative to the specification file. The helper copies and hashes images, generates the scene-bound manifest and receipt, then runs the same evidence validation used during evaluation. Missing evidence remains unresolved. Camera, time, renderer and visible-target declarations still come from the caller.

The same operations are available through `scene_acceptance.application.invoke`. Every operation uses the existing run history unless an explicit output is supplied.

## Model transport and context

All four optional roles receive `model_protocol` version 1.1 containing their role and complete response JSON Schema. A generic JSON adapter reads one request on stdin and returns one JSON response on stdout; it needs no private Python imports. Packaged interpreter, judge, triage and audit response schemas remain available for client development.

Repeated per-view target lists are referenced once through `declared_subject_sets`, retaining every declared target. Large inventory lists and script observation lists are bounded by `max_context_items` (default 512). Requirements, source text and owner policy are retained. Omitted counts and paths are explicit, full context is retained beside the model request, and truncated required measurement evidence cannot become an available measurement for judge acceptance. The original input context and response schema have separate hashes. `semantic_input_sha256` replaces only admitted file locations with their content hashes and binds the role/schema; relocation does not change that identity. `request_sha256` still identifies the concrete transport request. Raise the context limit only within the overall request-byte budget. This reduces payload size; it is not evidence of better model judgment or lower end-to-end latency.

`--max-prims` controls admission (default 10,000, maximum 250,000). A capacity stop reports UNKNOWN and the observed lower bound. It does not discard objects or relax a geometric tolerance. File, dependency, check-specific and model budgets still apply. Raising a ceiling is not a performance qualification at that scene size.

## Evidence still needed

The numerical and protocol controls test deterministic behavior. Human-labelled triage calibration, visual-judge/audit detection rates and independent reviewer-time savings are separate studies. No improvement in those outcomes follows from adding checks or reducing request bytes. Targeted-view instructions are available; their incremental model value remains to be measured on frozen cases.
