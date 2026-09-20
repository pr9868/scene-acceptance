# Static boxes and polygon meshes: scope frozen before implementation

19 September 2026. Same-assistant development evaluation, not independent validation, a model benchmark or proof of general 3D reliability. Existing v0.1 fixtures, raw model outputs and results stay unchanged. New source release: 0.2.0.

## Intended capability

The new `usd-static-geometry-v1` profile accepts static Cube and polygon Mesh prims together, plus Xform/Scope hierarchy. Meshes must resolve `subdivisionScheme` to `none`. Triangles, quads and general polygon faces are supported for vertex bounds, not arbitrary collision or rendered-surface equivalence. Subdivision, USD holeIndices, animation, instancing and previously unsupported composition remain unknown. The legacy cube profile still abstains on meshes.

`mesh` must be a required check for the new profile. It invokes OpenUSD's `UsdGeom.Mesh.ValidateTopology`, checks finite points, nonempty faces, at least three distinct indices per face and nonzero polygon vector area. Zero-area/canceling faces fail; self-intersection, planarity, concavity tessellation, normals, UVs and materials are not certified. The vector-area numerical floor is relative to each face size, not the layout acceptance tolerance. A missing array or unsupported representation is unknown; a supplied invalid array is a violation. Stage-wide limits bound parsed points, faces and indices (250,000 / 250,000 / 1,000,000), without claiming parser/process isolation.

Bounds use transformed referenced vertices and authored units, ignoring authored extents and unused points. Containment against a convex cell box and an aisle half-plane needs these extrema; this is not pairwise collision detection. A consumer may require particular meshes to have closed, consistently directed edge incidence. This checks two opposite uses per edge, not watertightness, vertex manifoldness, self-intersection or physical solidity. Open surfaces are accepted when closure is not required.

Optional required `shape` check with `mode: translation_only` and explicit prim paths compares candidate with a saved baseline, allowing world translation only. Cubes compare the eight centered corners; meshes require identical face counts/indices and corresponding centered points within the contract tolerance. Thus scaling, rotation that changes those positions, interior shape changes and topology edits fail even when AABBs match. This intentionally conservative indexed-mesh check can reject equivalent reindexed/remeshed exports or a Cube-to-Mesh conversion. It is not a general surface-distance algorithm. Missing baseline or unsupported shape coverage is unknown. A missing requested candidate prim fails. Only consumer-declared paths are checked.

## Required development cases

Accept equivalent cube, quad mesh and triangle mesh layouts; accept a mixed scene with an open tray, a planar surface without closure, and a concave polygon for the stated bounds-only purpose. Accept a translated mesh with unchanged shape and a rotated centimetre hierarchy with analytically specified target/bounds. Ignore forged extent and unused points for actual face bounds. Reject an aisle intrusion, wrong requested destination, invalid indices/count sums, non-finite points, repeated-index/zero-area faces, open edges when closure is required, and inconsistent edge direction. Keep subdivision and holeIndices unknown. Reject shape shrinkage, a rotation that keeps the AABB, and an interior change that keeps the AABB. A missing baseline is unknown; a missing target fails; a shape contract without its required check is a configuration error.

## Existing model evidence

Use the already saved ordinary-layout Astra output unchanged under an explicitly stronger contract. Separately convert Cube prims to equivalent polygon meshes deterministically and label this as a coordinator conversion, not a new model generation. Use the earlier coordinator-shrunk derivative unchanged under an upgraded shape contract to show closure of that specific known gap. Preserve the old contract, original accepted result and supplemental audit. No new model calls, hidden repairs, hallucination attribution or aggregate model success rate.

## Reporting and regression

Freeze input hashes and expected labels before running the new implementation. Record every run, including failures; do not overwrite results or relabel cases after seeing a verdict. New code must still match the 30 old expected labels and pass existing robustness tests. Preserve an installable source snapshot of 0.1.0 because old receipts pin its checker digest. Test 0.2 from a noneditable installation. Record exact versions, checker digest, commands and limitations. Compare native topology results to added task requirements; a native topology pass is not a task acceptance result. Do not count the old simple script's unsupported mesh cases as errors or assert review-time savings.
