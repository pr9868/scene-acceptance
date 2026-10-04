# Supplemental checks in the installed package

`brief.four-job` 1.0.0 contains 21 named checks ported from the retained four-job experiment. It is available from the default registry, with no separate plugin installation. Install `.[article_checks]` for NumPy/Pillow and the existing simulation worker dependencies. These are explicitly selected example requirements, not general requirements inferred for every scene. They are **not** added to `usd-delivery-baseline`.

Every check takes exactly `{"job": "…"}`. The schema accepts only compatible jobs: `tray-baseline`, `tray-translated`, `panel-png`, `panel-jpeg`, `motion`, `physics-022`, `physics-042`, `physics-068`. Paths, targets and tolerances below are fixed by this preset. For another brief, select or implement an appropriate pack with its own explicit parameters; renaming an arbitrary scene does not make this example a suitable acceptance policy.

| Checks | Declared target and comparison | What a reader gets / limitation |
|---|---|---|
| `common.metadata` | Authored metre units, Z-up, default prim | Delivery convention readback; one stage comparison |
| `common.geometry` | Mesh/Cube geometry, valid mesh indices, subdivision `none`, finite authored numeric values | Issues and geometry paths; not general geometric validity |
| `tray.dimensions` | `/World/Tray` local bounds `[-.15,-.1,0]` to `[.15,.1,.08]` m | Outer dimensions, tolerance 1 µm |
| `tray.cavity` | Eleven prescribed axis-aligned surfaces: inner opening .280 × .180 m, floor Z=.010 m, rim Z=.080 m | Surface area errors, unmatched triangles and triangle count; no general self-intersection/CAD certificate |
| `tray.closure` | Oppositely directed paired edges; signed material volume .001272 m³, tolerance 1e-8 m³ | Boundary/volume evidence; not manufacturing certification |
| `tray.transform` | Identity baseline or +.400 m world-X translation | Observed matrix versus target; translated job requires `--baseline` |
| `tray.fixture` | `/World/Fixture` world bounds `[-.3,-.04,0]` to `[-.2,.04,.04]` m | Protected fixture position and dimensions |
| `tray.preserved` | Every root-layer authored field except `/World/Tray.xformOp:translate` default | Changed spec paths; exact authoring preservation, not composed-scene equivalence |
| `panel.dimensions` | `/World/Panel`, .240 × .160 m in XY at Z=0, area .0384 m² | X/Y offset remains free, as the brief permits |
| `panel.shader` | `/World/Looks/Label`: PreviewSurface diffuse → named Texture RGB; UVTexture `st` from an `st` primvar reader | Connected authored graph and named PNG/JPEG reference; does not replace the separate material-binding check |
| `panel.uv` | Flattened vertex/varying/faceVarying `st`, full [0,1] range, area 1 and affine full-panel mapping | Authored UV evidence; no rendered orientation or appearance observation |
| `panel.pixels` | `textures/label.png` or `.jpg`: single-frame 256×256 RGB; red/green/blue/white quadrants in top-left image coordinates | PNG exact pixels. JPEG masks rows/columns 120–135: interior maximum ≤32 and each channel's mean ≤4. Whole-image maximum is reported separately, not constrained to 1 |
| `panel.equivalence` | `reference.usda` sibling root-layer fields equal except named image filename | Declare the sibling in `evidence_sources`; missing sibling is UNKNOWN |
| `motion.clock` | Authored time-code interval 12–156 at 48/s | Exact saved clock requirement |
| `motion.lengths` | `/World/Mechanism/`: crank centre (0,0,.1), radius .042 m, rod .140 m; slider Y=0/Z=.1 | Errors at 514 diagnostic times, 1 µm tolerance; no continuous guarantee |
| `motion.cycle` | 25° start; counterclockwise sampled progression, positive slider branch, one cycle, loop error ≤1 µm | Variable speed is allowed; sampled progression cannot exclude unsampled excursions |
| `motion.trajectory` | Constant-speed positive-branch crank-slider reference, position error ≤.5 mm and loop ≤1 µm | **Advisory in supplied contracts**: uniform angular speed was not required by the brief |
| `motion.connections` | Rod local endpoints (0,0,0) and (.14,0,0), crank/slider named pins, gap ≤.5 mm | Both attachment errors at 514 times; finite evidence only |
| `motion.geometry` | Geometry descendants under named Crank/Rod/Slider components | Authored geometry presence; visibility and rendering are not evaluated |
| `physics.parameters` | `/World/Block` mass 1.25 kg; `/World/Contact` static/dynamic friction .22/.42/.68 | Requested saved parameters; assumptions are not physical measurements |
| `physics.preserved` | Supplied `physics-base.usda` fields equal except those three values | Extra/changed authoring caught; does not replace runtime simulation or calibration |

The two motion schedules are `3*i/256` and `3*(i+.37)/257`, each for i=0…256. Length/connection/trajectory reports expose one outcome per sampled mechanism time; cycle assessment is a whole-sequence comparison. Other checks report one selected requirement comparison, not an invented count of passing assets. Subject identities, values and units remain in JSON; `subjects.csv` points to exact evidence rows. Do not add counts across checks.

The preset stops with UNKNOWN beyond 10,000 prims, 100,000 authored time samples or 150,000 face indices. Image checks enforce 1 MiB and 65,536 pixels before decoding. These are bounded trusted-local examples, not a general resource sandbox. Core admission and the caller's dependency-file budget still apply.

Checks execute separately: missing image content cannot hide passing dimensions/UVs; missing reference evidence cannot suppress parameter checks. A missing required target is unresolved evidence, never a pass. Explicit failures remain failures. Contract schema errors or unavailable optional libraries are evaluation errors.

Example contract selection:

```json
{
  "id": "label-content",
  "pack": "brief.four-job",
  "check": "panel.pixels",
  "required": true,
  "parameters": {"job": "panel-png"}
}
```

Add `"brief.four-job": {"version": "1.0.0"}` to the contract's `packs`. Preserve a digest pin when exact implementation identity matters. `check-3d-packs` exposes all parameter schemas and implementation/dependency hashes. The original `fresh.brief` identifier was experiment-local and is not silently aliased: the replay script migrates copied contracts explicitly and records new hashes.

For more checks, follow [PACKS_API.md](PACKS_API.md). This preset is a reference for bounded comparisons, not an obligation to add domain-specific criteria to the generic baseline.
