# What each test checks

The catalog describes available capabilities. A run report separately records what actually ran, subjects assessed, outcomes and missing evidence. `check-3d --list-tests` returns the same rule IDs and provider descriptions as JSON; `check-3d --capabilities` describes the invocation and evidence schemas.

The optional [assumption-triage operation](ASSUMPTION_TRIAGE.md) is a separate model-assisted review step. It classifies selected assessed obligations or declared decisions under caller policy; it adds no rule to the 27-check baseline and is not a new scene measurement.

## General baseline: 27 selected rules

These do not need task-specific dimensions or a user brief. Current baseline policy is `usd-delivery-baseline@1.2.0`; earlier saved reports retain their original policies. Physics declarations are schema checks, not simulation. Native provider scope and per-subject counts remain in the report. Prepared scope approval pins this baseline and the resolved pack identities.

| ID | Rule | What it tests |
|---|---|---|
| `usd.00` | `usdValidation:CompositionErrorTest` | Validator aims at providing all composition errors, which were generated while composing the stage. |
| `usd.01` | `usdValidation:StageMetadataChecker` | Stages that can be consumed as referenceable assets must have a valid 'defaultPrim' specified. |
| `usd.02` | `usdGeomValidators:StageMetadataChecker` | All stages must declare their 'upAxis' and 'metersPerUnit'. |
| `usd.03` | `usdGeomValidators:EncapsulationChecker` | Validates there are no nested Gprims. |
| `usd.04` | `usdGeomValidators:SubsetParentIsImageable` | Validates that GeomSubset prims are direct descendants of an Imageable prim. |
| `usd.05` | `usdGeomValidators:SubsetFamilies` | Validates all of the geom subset families authored beneath an Imageable prim. |
| `usd.06` | `usdShadeValidators:MaterialBindingRelationships` | All properties named 'material:binding' or in that namespace should be relationships. |
| `usd.07` | `usdShadeValidators:MaterialBindingApiAppliedValidator` | Verify a prim has the MaterialBindingAPI applied if it has a material binding relationship. |
| `usd.08` | `usdShadeValidators:MaterialBindingCollectionValidator` | Verify that a collection defining a material binding is well-formed |
| `usd.09` | `usdShadeValidators:SubsetMaterialBindFamilyName` | Geom subsets with authored material bindings should have the 'materialBind' family name. |
| `usd.10` | `usdShadeValidators:SubsetsMaterialBindFamily` | Geom subsets of the 'materialBind' family should have a restricted family type. |
| `usd.11` | `usdShadeValidators:EncapsulationRulesValidator` | Connectable prims (e.g. Shader, Material, etc) can only be nested inside other Container-like Connectable prims. Container-like prims include Material, NodeGraph, Light, LightFilter. Shader is not a Container-like prim. |
| `usd.12` | `usdUtilsValidators:MissingReferenceValidator` | The composed USD stage should not contain any unresolvable asset dependencies (in every possible variation of the asset), when using the default asset resolver. |
| `usd.13` | `usdPhysicsValidators:RigidBodyChecker` | Validates all of the UsdPhysicsRigidBodyAPIs applied to a prim. |
| `usd.14` | `usdPhysicsValidators:ColliderChecker` | Validates all of the UsdPhysicsCollisionAPIs applied to a prim. |
| `usd.15` | `usdPhysicsValidators:PhysicsJointChecker` | Validates all of the UsdPhysicsJoint prims. |
| `usd.16` | `usdPhysicsValidators:ArticulationChecker` | Validates all of the UsdPhysicsArticulationRootAPIs applied to a prim. |
| `nv.00` | `ValidateTopologyChecker` | Validate the topology of a mesh on all time samples. |
| `nv.01` | `ExtentsChecker` | Boundable prims have the extent attribute. For point based prims, the value of the extent must be correct at each time sample of the point attribute |
| `nv.02` | `NormalsValidChecker` | Check that all normals have unit length, and that there are no non-finite values. Also checks that the supplied number of normal values agrees with the interpolation. |
| `nv.03` | `NormalsExistChecker` | Check that meshes have normals. All meshes should have normals unless they have the subdivision scheme set. Meshes cannot have both normals and subdivision set. |
| `nv.04` | `NormalsWindingsChecker` | Check that the mesh has normals that are consistent with the face windings, taking into account the 'orientation' attribute. We define the meaning of agreement between a normal attribute value and the reference normal of a face (quite loosely) as the two having a positive inner product. We then sum these inner products, and if the sum is positive, it would be a relatively large number (close to the area of the surface) and this would indicate that the winding is right-handed. Otherwise, the sum would be a relatively large negative number to indicate a left-handed rule having been used for generation of normals. Works on non time varying geometry. |
| `nv.05` | `ZeroAreaFaceChecker` | Faces with zero area can be removed. May produce welding after removal. Works on non time varying geometry. |
| `nv.06` | `UsdDanglingMaterialBinding` | Rule ensuring that the bound material exists in the scene. |
| `audit.files` | `audit.files` | Check referenced local dependency files are present. |
| `audit.textures` | `audit.textures` | Decode discovered image files within byte/pixel limits; no UV or visual comparison. |
| `audit.authored_motion` | `audit.authored_motion` | Inspect authored transform samples, boundaries and midpoints for usable timing and finite values; no intended path or continuous guarantee. |

## Configurable check types

These run only when selected by a contract, mapped brief or supported preset. Provider-selector entries below expose the same baseline validators as well as explicitly selected additional rules; they are not extra default tests. The JSON catalog includes each parameter schema.

| Check type | What it tests | Coverage and limits |
|---|---|---|
| `openusd.validators` | Run explicit native validators | Named native validator scope. Local USD admission limits apply. |
| `geometry.contract` | Evaluate an existing v1 contract | Existing cube/polygon/edit/evidence scope. Fixed topology/indexing for shape preservation; no collision or rendering |
| `materials.delivery` | Check resolved bindings, shader IDs and external files | Named material structure and dependency existence. No rendered appearance, image decoding, UV correctness or physical parameters |
| `motion.positions` | Compare world origins at explicit time codes | Only named positions at supplied times. No continuous-time guarantee, collision, orientation or physics |
| `nvidia.asset-validator.rules` | Run explicit NVIDIA rules without fixes | Named upstream rules only. No simulator execution or SimReady profile certification |
| `motion.timing.clock` | Check authored stage duration and optionally require an exact clock rate | Authored stage time range converted to seconds. Does not infer active motion duration; an authored positive timeCodesPerSecond or framesPerSecond rate and complete time range are required |
| `motion.timing.positions` | Compare named world origins at elapsed seconds from the authored stage start | Named world origins at the requested elapsed seconds. No continuous-time, orientation, collision or physics proof; Requires authored clock and time range |
| `textures.decode.image` | Verify and load one required image | Selected static image bytes. No UV, color-management, rendered appearance or hostile-input isolation claim |
| `motion.connection.distance` | Compare the gap between two task-named points | World-space distances at explicit times. Points are caller-defined, not inferred joints; finite sampling can miss motion defects |
| `physics.incline-worker.displacement` | Verify installed worker/adapter/profile identities, run the fixed incline model and compare displacement | Source identities verified before/after execution and against returned evidence; trajectory rechecked. One-body CPU fixture, not a general USD physics importer or hostile-code sandbox. Assumed friction does not establish real-world task validity |
| `scene.audit.files` | Check discovered external files | Admitted external dependencies.  |
| `scene.audit.textures` | Decode discovered PNG/JPEG dependencies | Discovered image files; other formats remain unknown.  |
| `scene.audit.authored_motion` | Check finite authored world transforms | Explicitly bounded samples; no motion intent.  |
| `brief.four-job.common.metadata` | Authored metre units, Z-up, default prim | Delivery convention readback; one stage comparison |
| `brief.four-job.common.geometry` | Mesh/Cube geometry, valid mesh indices, subdivision `none`, finite authored numeric values | Issues and geometry paths; not general geometric validity |
| `brief.four-job.tray.dimensions` | `/World/Tray` local bounds `[-.15,-.1,0]` to `[.15,.1,.08]` m | Outer dimensions, tolerance 1 µm |
| `brief.four-job.tray.cavity` | Eleven prescribed axis-aligned surfaces: inner opening .280 × .180 m, floor Z=.010 m, rim Z=.080 m | Surface area errors, unmatched triangles and triangle count; no general self-intersection/CAD certificate |
| `brief.four-job.tray.closure` | Oppositely directed paired edges; signed material volume .001272 m³, tolerance 1e-8 m³ | Boundary/volume evidence; not manufacturing certification |
| `brief.four-job.tray.transform` | Identity baseline or +.400 m world-X translation | Observed matrix versus target; translated job requires `--baseline` |
| `brief.four-job.tray.fixture` | `/World/Fixture` world bounds `[-.3,-.04,0]` to `[-.2,.04,.04]` m | Protected fixture position and dimensions |
| `brief.four-job.tray.preserved` | Every root-layer authored field except `/World/Tray.xformOp:translate` default | Changed spec paths; exact authoring preservation, not composed-scene equivalence |
| `brief.four-job.panel.dimensions` | `/World/Panel`, .240 × .160 m in XY at Z=0, area .0384 m² | X/Y offset remains free, as the brief permits |
| `brief.four-job.panel.shader` | `/World/Looks/Label`: PreviewSurface diffuse → named Texture RGB; UVTexture `st` from an `st` primvar reader | Connected authored graph and named PNG/JPEG reference; does not replace the separate material-binding check |
| `brief.four-job.panel.uv` | Flattened vertex/varying/faceVarying `st`, full [0,1] range, area 1 and affine full-panel mapping | Authored UV evidence; no rendered orientation or appearance observation |
| `brief.four-job.panel.pixels` | `textures/label.png` or `.jpg`: single-frame 256×256 RGB; red/green/blue/white quadrants in top-left image coordinates | PNG exact pixels. JPEG masks rows/columns 120–135: interior maximum ≤32 and each channel's mean ≤4. Whole-image maximum is reported separately, not constrained to 1 |
| `brief.four-job.panel.equivalence` | `reference.usda` sibling root-layer fields equal except named image filename | Declare the sibling in `evidence_sources`; missing sibling is UNKNOWN |
| `brief.four-job.motion.clock` | Authored time-code interval 12–156 at 48/s | Exact saved clock requirement |
| `brief.four-job.motion.lengths` | `/World/Mechanism/`: crank centre (0,0,.1), radius .042 m, rod .140 m; slider Y=0/Z=.1 | Errors at 514 diagnostic times, 1 µm tolerance; no continuous guarantee |
| `brief.four-job.motion.cycle` | 25° start; counterclockwise sampled progression, positive slider branch, one cycle, loop error ≤1 µm | Variable speed is allowed; sampled progression cannot exclude unsampled excursions |
| `brief.four-job.motion.trajectory` | Constant-speed positive-branch crank-slider reference, position error ≤.5 mm and loop ≤1 µm | **Advisory in supplied contracts**: uniform angular speed was not required by the brief |
| `brief.four-job.motion.connections` | Rod local endpoints (0,0,0) and (.14,0,0), crank/slider named pins, gap ≤.5 mm | Both attachment errors at 514 times; finite evidence only |
| `brief.four-job.motion.geometry` | Geometry descendants under named Crank/Rod/Slider components | Authored geometry presence; visibility and rendering are not evaluated |
| `brief.four-job.physics.parameters` | `/World/Block` mass 1.25 kg; `/World/Contact` static/dynamic friction .22/.42/.68 | Requested saved parameters; assumptions are not physical measurements |
| `brief.four-job.physics.preserved` | Supplied `physics-base.usda` fields equal except those three values | Extra/changed authoring caught; does not replace runtime simulation or calibration |
| `brief.measurements.metadata` | Authored stage metadata matches specified values | Selected authored metadata fields. No active motion or world-coordinate interpretation claim |
| `brief.measurements.bounds` | Named geometry size and centre | World Cube/Mesh bounds at one time. No shape equivalence |
| `brief.measurements.children` | Required direct-child count | One parent and type. Count does not establish function or dimensions |
| `brief.measurements.axis_gap` | Required directed axis gap | Two named Cube/Mesh world bounding boxes. Not a walkability or safety test |
| `brief.measurements.image_pixels` | Delivered texture matches a reference image under saved regions/mask and maximum/optional mean channel-error limits | RGB source pixels only; 1 MiB/262,144 pixels per image. Reports included/excluded counts and whole-image diagnostics; excluded pixels are unassessed. No colour conversion or rendered-appearance proof |

## Optional model review: selected criteria and disclosed exclusions

A caller can supply a versioned custom rubric with `--rubric`. Without one, general preset version `2.0.0` selects criteria from authored inventory as shown below. Prepared scopes retain that selection across repairs. Brief visual/combined requirements are added separately; script-only and unresolved requirements remain in their respective report layers. Opinions are consistent, concern or unknown, never measured passes.

| Item | General-preset selection | Required evidence | Limit |
|---|---|---|---|
| `review.layout` | Included: visible arrangement and disconnected/implausibly placed components | `scene_view` | Shown surfaces only; no hidden geometry, dimensions, collision or function proof. |
| `review.readability` | Included: distinguishable components and relationships | `scene_view` | View-dependent readability, not an undeclared user preference or full scene audit. |
| `review.material-use` | Included when materials or shaders are authored | `textured_view` | Source pixels and schematic colours do not prove visible surface mapping. |
| `review.motion` | Included when time-sampled attributes are authored | `motion_frames` | At least three declared same-camera timestamps; no continuous, speed, orientation or collision proof. |
| Physical validation | Outside the default visual preset; an explicit brief/custom criterion is retained | `physical_validation` | No supported judge evidence adapter. An explicit request stays unknown and requires review. |

`judge.unassessed_areas` and the HTML list preset exclusions as unassessed, never passing. Named `static-visual` and `animated-visual` profiles also disclose their exclusions; custom criteria are not silently removed. Schematic projections cannot satisfy a selected material-use item. The default verdict-withheld review cannot re-measure numeric brief checks; when those are routed for review, they remain unknown unless script evidence is explicitly included. Three frames at one identical timestamp do not count as motion evidence.

## Software tests for the interface

| Control | What it establishes |
|---|---|
| Six mode/brief combinations | Scene-only and brief-aware checks, judge, and combined runs have consistent envelopes. |
| Isolation | Checks-only cannot call a model; judge-only cannot execute content-check packs. |
| Existing invocation parity | The legacy stdout and measured outcomes remain compatible. |
| Evidence suitability | Missing views, schematic-only materials and repeated timestamps remain unassessed. |
| Provenance and integrity | Wrong scene/image hashes, escaping paths, coordinate disagreement and unknown prims cannot reach the model. |
| Model disagreement | A favourable model opinion cannot clear a measured rejection or approve a review obligation. |
| Partial execution | Timeout, malformed output, stale requests and invalid citations preserve completed script reports. |
| Read-only inputs | Changes during a run invalidate the combined evaluation rather than mixing revisions. |
| Scope policy migration | Changed general checks, enforcement flags or selected pack identities invalidate old approval; new policy requires explicit review. Ordinary repairs preserve scope. |
| Worker identity | Missing/stale worker, adapter or profile hashes and changed installed files invalidate simulation evidence. |
| Applicable review scope | Static scenes can complete selected visual review; excluded areas are disclosed, while explicit unsupported physics and missing requested frames still require review. |
| Image policy | 1080p/RGBA references are admitted for visual interpretation; exact comparison separately enforces regions/masks, maximum and mean limits, source identities and its smaller decoder budget. |

Deterministic adapters test implementation and boundaries. Real model reviews and known-case comparisons are separate empirical evidence; passing these software tests does not establish that model opinions are correct.

## Raw-brief preparation and adopter skills

The automatic interpreter selects the bounded types exposed by `check-3d --capabilities`: geometry and layer policy, state and connection checks, process connectivity, timing, materials and source-image comparisons. External-engine jobs and arbitrary code are never generated from a model response. Unsupported intent stays visible and the owner must review the scope. See [extended capabilities](EXTENSIONS.md) for parameters, boundaries and test evidence.


## Explicit state and process topology (development candidate)

| Check | Evaluator | Caller input | Reports | Boundary |
|---|---|---|---|---|
| `behavior.state.agreement` | Script | Two scene-authored held-state attributes, optional activation attribute, interval | Internal consistency over every active authored interval and final endpoint | Matching scene values do not prove owner intent |
| `behavior.state.timeline` | Script | Observed scene attribute and owner-reviewed expected timeline in the contract | Every expected/observed transition and final endpoint; contract-controlled activation | No rendered sign inspection, occupancy inference or external controller verification |
| `process.connections.match` | Script | Equipment tags, port names/directions, directed edges and extra-edge policy | Equipment/port/edge totals plus each comparison | Structured graph only; no drawing extraction, physical pipe connection or process-engineering certification |

Both are contract-selected, outside the general baseline. See [parameters and controls](SEMANTIC_CHECKS.md). Model interpretation does not automatically create these checks from a P&ID. Review the explicit reference and its mapping to saved scene metadata.
