# Third-party dependencies

Scene Acceptance's own code and documentation use the MIT license in `LICENSE`. Dependencies are installed separately; their respective licenses continue to apply. This repository does not relicense them or imply endorsement by their maintainers.

| Dependency | Use | Upstream project |
|---|---|---|
| OpenUSD / `usd-core` | USD composition, schemas, geometry and validation | https://github.com/PixarAnimationStudios/OpenUSD |
| `jsonschema` | Contract and record validation | https://github.com/python-jsonschema/jsonschema |
| `usd-validation-nvidia` | Optional selected asset rules | https://github.com/NVIDIA-Omniverse/usd-validation-nvidia |
| Pillow | Diagnostic image decoding experiment | https://github.com/python-pillow/Pillow |
| MuJoCo | CPU behavior experiment | https://github.com/google-deepmind/mujoco |
| NumPy | Experiment numerical operations | https://github.com/numpy/numpy |
| pytest | Development tests | https://github.com/pytest-dev/pytest |

Pinned runtime and test dependencies, including transitive packages, are listed in `requirements-test.lock` and `requirements-articles.txt`. Inspect the installed distributions for their license files. Example scenes, contracts and diagram sources in this repository were constructed for this project.
