# Two scene builds: findings, feedback and repair

A dairy plant and a larger distribution-centre scene produced three different acceptance problems. The distribution-centre trial preserved the first delivery before findings went back to the builder, then checked the repaired delivery against the same scripted scope.

| Finding | Evidence | What changed |
|---|---|---|
| Dairy material bindings pointed at missing materials | One generator defect affected three objects; the saved diagnostic names the missing targets | The producer repaired its generator and reran the checks |
| Distribution-centre meshes lacked authored normals under the selected delivery policy | All 24 brief-derived scripted checks passed, but one general rule failed across 121,602 mesh subjects; the brief had not stated this policy | The producer authored normals; all 52 scripted rows then passed |
| A route indicator disagreed with the parcel's path | Separate geometry review found the mismatch between named events, despite passing endpoint timing checks | The producer revised the indicator and schedule; matched RTX views and separate measurements support the repair |

The useful distinction is what needs to change: the delivery, the brief's delivery policy, or the coverage of the checks and review.

## Inspect the evidence

- [Article: What Two Scene Builds Revealed About 3D Acceptance](https://roughcut.dev/projects/what-two-scene-builds-revealed-about-3d-acceptance/)
- [Rendered evidence collection](https://roughcut.dev/downloads/two-scene-acceptance/)
- [Dairy brief](public/downloads/two-scene-acceptance/briefs/dairy-requirements.md) and [distribution-centre brief](public/downloads/two-scene-acceptance/briefs/distribution/01-requirements-brief.md), including supplied reference images
- [Result excerpts](public/downloads/two-scene-acceptance/results.html) and [measurements](public/downloads/two-scene-acceptance/measurements.json)
- [Redacted feedback](public/downloads/two-scene-acceptance/distribution-feedback.html), [producer response](public/downloads/two-scene-acceptance/distribution-response.html) and [coverage](public/downloads/two-scene-acceptance/coverage.html)
- [File manifest and recorded transformations](public/downloads/two-scene-acceptance/manifest.json)

The `public/` directory mirrors the website's selected evidence and media. Its manifest records file sizes and SHA-256 hashes relative to that directory. Display derivatives retain the disclosed renderer provenance; the paired indicator stills use the same camera and timestamp. Original reference PNGs and the producer's explanation video retain their bytes. The feedback is labeled as redacted, with all eight finding/request bodies preserved.

## Scope

These are fictional facilities made for the trials. The dairy used the released harness; the distribution-centre trial used an unreleased development build with higher input limits and a custom measurement pack. This evidence publication does not add those capabilities to version 0.5.0. Complete scene deliveries, the development evaluator and custom pack are not included, so this is a record to inspect, not a complete execution replay.

The original failing dairy scene was not preserved. Its producer also planted fourteen faults to probe coverage; those controls are separate from the observed binding defect. The distribution-centre coordinator prepared both the brief and the checks, had seen some draft code, and withheld findings until the first package was archived. This was not a blinded experiment or a controlled model comparison.

Separate review supplied the route-state and other repair findings; it did not use the harness's optional judge path. Producer-recorded Blender viewport observations raise a usability concern but do not establish full-cycle interaction performance. Physical operation and final owner acceptance remain unverified. [Records and reproduction limits](public/downloads/two-scene-acceptance/records.html) explain the boundary in detail.
