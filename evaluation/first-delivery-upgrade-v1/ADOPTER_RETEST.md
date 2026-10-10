# Reading the adopter retest

The same original conveyor, process-skid and rack deliveries became assessable without producer repairs when the adopter explicitly selected subtree coverage, surface semantics and allowed boundary contact with a 1 mm band. Their expanded checklists passed 24/24, 13/13 and 14/14 rows respectively. Counts are check rows, not assets. This was a retrospective policy revision after seeing earlier results; it is not evidence that unchanged requirements suddenly passed.

The retained twelve controls mix different questions:

| Control | Observed outcome | Type of evidence |
|---|---|---|
| Incorrect route-indicator window | Fail | Detection against an owner-held state timeline |
| Lowered duct | Fail | Newly measurable zone intrusion |
| Mirrored sign UVs | Pass; defect missed | Known limit of source-image comparison |
| Rotated source image | Fail | Pixel comparison |
| Late parcel | Fail | Timing |
| Wrong belt material | Fail | Binding requirement |
| Skinned posts | Unknown, named | Honest unsupported-geometry outcome |
| Rotated but clear duct | Pass | Clear-geometry control |
| Missing sign texture | General rejection; unrelated belt passes | Correct attribution; the texture requirement remains unresolved |
| 12,327 prims | Default capacity unknown; raised budget evaluates | Capacity behavior, not defect detection |
| Unlisted stray carton | Fail under the new subtree selector | Coverage expansion |
| Rack row pushed into aisle | Fail | Newly measurable zone intrusion |

The reported “11/12” combines detection, a clear pass, an expected unknown and a capacity result. Some original expectations intentionally predicted misses, and the initial freeze did not include all later large-scene cases. It should not be called independent detection accuracy or a single preregistered score. The later [rendered-sign controls](../model-workflow-v1/README.md) address the visual blind spot on a separate constructed fixture, not a re-evaluation of this exact conveyor sign.

Timing also needs its workload: the smaller migrated rack checklist took about 1.8 seconds, whole-row selection about 27 seconds, and the 12,327-prim scene about 54 seconds on the retest host. The separate developer comparison of 135 to 2.31 seconds used a different host/workload. None is a general throughput claim.

The adopter reported 997 passing tests and three skips. Its retained log did not identify the skipped tests, so we cannot assert why they skipped. Local development verification now retains `pytest -rs` and JUnit output. Fresh judge/audit/triage accuracy and independent human review savings were not measured by this retest.
