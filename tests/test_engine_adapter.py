"""A real subprocess exercises the bridge; the engine itself is a test double."""

import sys
import pytest

from scene_acceptance.application import invoke
from scene_acceptance.model import sha, strict_json
from test_extensions_geometry import scene
from test_review import save


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("pass", 0),
        ("fail", 2),
        ("missing", 3),
        ("mutate", 4),
        ("exit", 4),
        ("symlink", 4),
        ("structured-status", 4),
    ],
)
def test_caller_owned_engine_bridge(tmp_path, mode, expected):
    root = tmp_path / "bundle"
    root.mkdir()
    stage = scene(root)
    stage.GetRootLayer().Save()
    original = sha(root / "scene.usda")
    adapter = tmp_path / "engine.py"
    adapter.write_text("""import json,sys
from pathlib import Path
scene,report,mode=sys.argv[1:]
if mode=='exit':sys.exit(9)
if mode=='mutate':Path(scene).write_text('modified')
if mode=='symlink':
 Path(report).symlink_to(scene);sys.exit(0)
Path(report).write_text(json.dumps({} if mode=='missing' else {'tests':{'contact':[] if mode=='structured-status' else 'PASS' if mode=='pass' else 'FAIL'}}))
""")
    config = tmp_path / "adapter.json"
    save(
        config,
        dict(
            schema_version="1.0",
            executable=sys.executable,
            args=[str(adapter), "{scene}", "{report}", mode],
            provider="physx",
            engine=dict(
                name="synthetic-engine", version="1", environment_sha256="a" * 64
            ),
            profile_id="synthetic-contact",
            profile_sha256="b" * 64,
            native_report="native.json",
            successful_exit_codes=[0],
            tests=[
                dict(
                    id="contact",
                    phase="runtime",
                    status_pointer="/tests/contact",
                    status_mapping={"PASS": "PASS", "FAIL": "FAIL"},
                )
            ],
            wall_seconds=5,
            memory_mib=512,
            cpu_seconds=5,
        ),
    )
    out = tmp_path / "collected"
    result = invoke(
        "collect-engine",
        bundle_root=root,
        candidate="scene.usda",
        out=out,
        adapter_config=config,
    )
    assert result["exit_code"] == expected, result
    assert sha(root / "scene.usda") == original
    assert (out / "adapter-execution.json").is_file()
    if expected != 4:
        receipt = strict_json(out / "engine-receipt.json")
        assert receipt["attachments"][0]["sha256"] == sha(out / "native.json")
        assert result["data"]["acceptance_decision"] is None


def test_producer_cannot_supply_executable_policy(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    stage = scene(root)
    stage.GetRootLayer().Save()
    save(root / "config.json", {})
    result = invoke(
        "collect-engine",
        bundle_root=root,
        candidate="scene.usda",
        out=tmp_path / "out",
        adapter_config=root / "config.json",
    )
    assert (
        result["exit_code"] == 4
        and "outside the producer" in result["errors"][0]["message"]
    )
