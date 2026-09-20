# Example external mesh-budget pack

This separate package demonstrates the public pack API. Install the core first, then install this directory with `python -m pip install .`. Discover it using `check-3d-packs`; enable it for a run using `--allow-pack studio.mesh-budget`.

Its `faces` check compares named static mesh polygon counts against a per-mesh budget. It does not prove valid topology or rendering performance. The implementation, parameter schema, explicit source file declaration and packaging entry point are all in this directory. The combined and third-party cases under `evaluation/packs-v1` exercise its real installed behavior.
