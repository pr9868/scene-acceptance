# Public distribution notes

Prepared after publication approval. The frozen research submission and raw session trace remain unmodified in the private research archive.

This is a derived distribution, not a byte-identical dump of the producer workspace. The USD, GLB, texture dependency, geometry generator, USD finalizer and validation logic are preserved. The recorded manifest in `evidence/submission-manifest.json` identifies the original files; `MANIFEST.json` identifies this public distribution.

Changes:

- Local machine paths in textual records are replaced with named placeholders. The brief itself is unchanged. Prompt/environment changes are path redactions only; the original frozen input hashes remain evidence of the private record.
- `submission/scripts/rebuild.sh` uses relative virtual-environment defaults; `test_viewer.mjs` imports installed Playwright and accepts Chrome/localhost environment settings. The README explains these portable launch paths.
- PNG text metadata is stripped without changing image data. The Blender file's null-terminated file-browser directory is reset to `./`, using the same byte length. The file is reopened and checked during release verification. Scene geometry, materials and animation are not edited by packaging.
- Unused Three.js builds, an intermediate Blender snapshot and fetched package tarballs are omitted. Runtime dependencies and their licenses are retained.
- The raw producer event stream and final response are retained privately. The workflow groups their events and identifies their trace hash; it does not offer the raw trace as a public download.
- The run summary retains the CLI version as experimental provenance. Its public path references and archive note are adapted to this distribution. Original artifact hashes in the workflow describe the original submission, not any adapted public file.
- The compact article viewer was authored after submission. It uses the original delivered GLB and is not counted as producer work. The recorded producer viewer is retained separately.

The measured submission remains one coordinated exercise. A successful package replay does not establish general agent reliability or reproduce a fresh model generation. See the article for boundaries of each check.

## Release verification

The [publication check record](evidence/publication-verification.json) distinguishes the unchanged recorded artifacts from a rebuild in a disposable copy. The source reopened, the rebuild completed, the portable browser test passed, and the selected harness decision replayed. These used the existing Blender/OpenUSD environments, not a second clean installation. Full shader compliance remains incomplete.

The development-revision link was updated after correcting commit email metadata. The referenced development source tree is unchanged.
