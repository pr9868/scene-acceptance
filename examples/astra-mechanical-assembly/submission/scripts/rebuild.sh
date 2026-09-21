#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
BLENDER_PYTHON="${BLENDER_PYTHON:-.venv-blender/bin/python}"
USD_PYTHON="${USD_PYTHON:-.venv-usd/bin/python}"
mkdir -p logs output
"$BLENDER_PYTHON" scripts/build_scene.py > logs/build.log 2>&1
"$USD_PYTHON" scripts/finalize_usd.py > logs/usd-finalize.log 2>&1
"$USD_PYTHON" scripts/validate_usd.py > logs/usd-validation.log 2>&1
"$USD_PYTHON" scripts/check_usd_compliance.py > logs/usd-compliance.log 2>&1
node scripts/validate_glb.cjs > logs/gltf-validation.log 2>&1
echo 'Rebuilt and checked output/. Run the local server and scripts/test_viewer.mjs for browser checks.'
