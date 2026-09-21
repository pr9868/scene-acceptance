# Animated assembly: recorded producer delivery

One fresh tool-using Astra task produced this crank-slider on September 20, 2026. The coordinator supplied the synthetic brief and tool environment; the producer selected and used tools, built the scene and viewer, inspected exports and corrected defects within that task. This is one worked example, not a representative benchmark.

- [Article and interactive views](https://roughcut.dev/projects/astra-animated-mechanical-assembly)
- [Brief](brief.txt), [recorded workflow](evidence/producer-workflow.json), [run summary](evidence/run-summary.json)
- [Launch, rebuild and producer checks](submission/README.md)
- [Public distribution changes and evidence limits](PUBLICATION.md)

From this folder, `python3 -m http.server 8765 --bind 127.0.0.1` serves the original viewer at `/submission/viewer/` and the compact article controls at `/article-viewer/`. For the producer's browser test, run `python3 scripts/serve.py` from `submission/`; its viewer then lives at `/viewer/`.

The original source and recorded outputs are in `submission/`. Review scripts and results are separate. The USD and GLB match the frozen submission hashes. The Blender file and render have privacy-only metadata changes. The local launch scripts were adapted for portability.

## What passed and what remains open

The producer recorded 961 USD and 481 browser pose checks. The coordinator inspected nine planned times, and a separate selected harness profile checked metadata, four material bindings and four-second duration. The coordinator's nine samples would have missed the producer's initial subframe rotation-wrap defect. Full USD shader compliance remains incomplete; physics, collision clearance and manufacturing fitness were not established.

The selected profile requires the separate [0.4 development revision](https://github.com/pr9868/scene-acceptance/tree/33e57211a1ddd2f624be07b8eeae9cfbb1cd5b6d); it is not part of the released v0.3 harness. Copy `submission/output/crank_slider.usdc` as `scene.usdc` and its `textures/` directory into a new bundle, along with `review/harness-bundle/contract.json`. Run `check-3d --contract contract.json --candidate scene.usdc --bundle-root <bundle> --out <report>` using that development environment. Kinematics and browser checks remain separate from that profile's decision.

Project-authored material is under the repository MIT license. Three.js and glTF Validator retain their own license and notice files under `submission/viewer/vendor/` and `submission/tools/gltf-validator/`.
