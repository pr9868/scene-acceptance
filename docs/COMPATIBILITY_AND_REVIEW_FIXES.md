# Compatibility and review fixes

October 3, 2026. Compatibility fixes developed after commit `52e412f6ab97e098e2ee9d191281111999efc2a8` and included in release 0.5.0. The public v0.3 release and retained historical experiment reports are unchanged. These fixes are exercised by constructed regression controls, not a new scene-generation or model-accuracy study.

| Area | What changed | Boundary retained |
|---|---|---|
| Connected texture inputs | Resolve supported static input connections to an admitted file and retain the connection path. | Cycles, multiple sources, computed outputs and animated inputs stay unresolved. No new file can bypass dependency admission. |
| MDL source identity | Read the source asset and source subidentifier for `sourceAsset` shaders. | This inspects authoring; it does not compile MDL or validate a render. |
| Renderer libraries | A missing declared MDL source library is UNKNOWN by default; upstream error text remains in evidence. `scene.audit.files` accepts `runtime_libraries: require_local` to make local delivery mandatory. | Ordinary missing assets, including textures, still fail. If an asset is also used as an ordinary dependency, that stricter requirement wins. No external resolver is contacted. |
| Brief reference images | RGB/RGBA PNG/JPEG up to 8 MiB and 16 million pixels each, 32 MiB combined; preserve alpha, ICC and EXIF metadata without conversion. | This is visual-reference admission. It is not a claim of color-managed equivalence or rendered visibility. |
| Exact pixel comparison | Optional included/excluded rectangles, black/white mask and per-channel mean limit, alongside the existing maximum limit. Evidence retains selected and whole-image diagnostics. | RGB only, 1 MiB and 262,144 pixels per image. No resampling or color-space conversion. Choose the mask before inspecting failures. |
| Timing | Use authored FPS fallback according to USD effective-rate precedence; tolerate endpoint roundoff from seconds conversion; do not fail valid extra keys merely for lying outside playback. | Wholly implicit clock remains UNKNOWN under the explicit-rate policy. Actual out-of-range requests stay unresolved. Finite values and sample budgets still apply. |
| Motion metric | Report per-coordinate position tolerance and descriptive Euclidean error. Connection checks use Euclidean distance. | Finite sampling cannot guarantee continuity or swept-volume clearance. |
| Scope approval | Freeze the full general baseline and selected pack implementation identities with the requirements. Policy-changing migration records a diff and requires fresh approval. | Ordinary scene repair preserves the approved scope. Older packets lacking `evaluation_policy` need new preparation and approval. |
| Default judge | Select applicable general visual questions and explicitly report excluded areas as unassessed. | Required brief/custom questions are not removed. Judge-only is advisory; unsupported physics cannot be approved by an image opinion. |
| CPU worker | Verify worker, adapter and fixed-profile identities before and after execution and in returned evidence. | Trusted installed code, same operating-system user, bounded two-box model. Hashes do not authenticate an arbitrary remote simulator or validate physical assumptions. |
| Reproduction | Use explicit verification errors and derive summary flags from checked reports, identities and observations. | `python -O` cannot disable the integrity checks. Historical evidence is preserved, not retrospectively regenerated. |

At the compatibility-fix snapshot, the baseline kept 27 check IDs and advanced its policy version to 1.1.0. At that local snapshot, individual pack versions remained pinned for unreleased fixtures and implementation digests identified the code. The later [0.5 release](INTEGRATION_RELEASE_0_5.md) assigns new versions to changed packs and upgrades pins only in recorded replay copies; the frozen inputs retain their original versions.

## Image comparison parameters

`brief.measurements.image_pixels` retains its existing required fields. Add `regions` or `excluded_regions` as arrays of `{ "x": 0, "y": 0, "width": 16, "height": 16 }` in image pixels. `mask_image` names a declared RGB black-and-white reference: white includes a pixel, black excludes it. `max_mean_channel_error` limits the mean absolute error in each RGB channel over the selected pixels. `max_channel_error` limits any selected channel difference. The selection must be nonempty, within bounds and the same size as the reference when a mask is supplied.

For the earlier 256×256 quadrant policy, retain `max_channel_error: 32`, set `max_mean_channel_error: 4`, and exclude the vertical and horizontal strips from coordinate 120 through 135. That illustrates the parameters; it does not make this mask suitable for photographic texture, text or fine boundary markings.

## Supported input boundary

Admission now includes bounded local variants, payloads, inherits, specializes, instance proxies and UDIM sets. Value clips, packages, resolver URLs and dynamic formats remain unsupported; an unsupported representation is not proof of a defective scene. `check-3d-doctor` discloses the active boundary and limits. See [extended capabilities](EXTENSIONS.md) for the supervised native worker and explicit layer-policy checks.

Regression sources: `tests/test_mdl_support.py`, `test_texture_reference_policy.py`, `test_motion_boundaries.py`, `test_scope_policy.py`, `test_judge_applicability.py`, `test_worker_identity.py` and `test_reproduce_integrity.py`. The retained fresh-wheel run belongs with its recorded revision; older counts and reports are evidence only for their recorded versions.
