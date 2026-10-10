"""Caller-only contracts: no private imports inside the executable adapter."""

import json
from pathlib import Path
import sys
import pytest
from scene_acceptance.application import invoke, parser
from scene_acceptance.judge import run_request
from scene_acceptance.model import digest_json
from test_extensions_geometry import scene


@pytest.mark.parametrize("role", ["judge", "interpreter", "triage", "audit"])
def test_json_cli_gets_public_schema_for_every_role(tmp_path, role):
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        'import json,sys\nr=json.load(sys.stdin)\np=r["model_protocol"]\nassert p["response_schema"]["properties"]["role"]["const"]==p["role"]\nprint(json.dumps({"role":p["role"],"request_sha256":r["request_sha256"]}))\n'
    )
    config = dict(
        driver="json-cli",
        executable=sys.executable,
        args=[str(adapter)],
        model="deterministic-protocol-control",
        effort="none",
        timeout_seconds=10,
    )
    schema = {
        "type": "object",
        "properties": {"role": {"const": role}, "request_sha256": {"type": "string"}},
        "required": ["role", "request_sha256"],
        "additionalProperties": False,
    }
    request = {"instruction": "Protocol control"}
    request["request_sha256"] = digest_json(request)

    def validate(response, req):
        from jsonschema import validate as valid

        valid(response, schema)
        assert response["request_sha256"] == req["request_sha256"]

    result = run_request(
        request,
        {},
        [],
        config,
        tmp_path / "run",
        role=role,
        response_schema=schema,
        response_validator=validate,
    )
    assert result["error"] is None, result
    assert result["response"]["role"] == role
    assert (tmp_path / "run/response-schema.json").is_file()


def test_identify_cli_api_and_copy_identity(tmp_path):
    import shutil

    root = tmp_path / "source"
    root.mkdir()
    s = scene(root)
    s.GetRootLayer().Save()
    copied = tmp_path / "relocated"
    shutil.copytree(root, copied)
    a = invoke("identify", bundle_root=root, candidate="scene.usda", out=tmp_path / "a")
    b = invoke(
        "identify", bundle_root=copied, candidate="scene.usda", out=tmp_path / "b"
    )
    assert a["status"] == b["status"] == "completed"
    assert a["data"]["scene_sha256"] == b["data"]["scene_sha256"]
    assert (
        parser()
        .parse_args(
            ["identify", "--bundle-root", str(root), "--candidate", "scene.usda"]
        )
        .operation
        == "identify"
    )


def test_evidence_helper_missing_views_stays_unresolved(tmp_path):
    from PIL import Image
    from scene_acceptance.preparation import prepare_scene
    from scene_acceptance.caller_tools import package_evidence

    root = tmp_path / "source"
    root.mkdir()
    s = scene(root)
    s.GetRootLayer().Save()
    caps = tmp_path / "caps.json"
    caps.write_text(
        json.dumps(
            dict(
                schema_version="1.0",
                capabilities=["geometry"],
                max_images=8,
                max_width=1920,
                max_height=1080,
                limitations=["synthetic control"],
            )
        )
    )
    prep = tmp_path / "prepared"
    plan = prepare_scene(
        bundle_root=root,
        candidate="scene.usda",
        out=prep,
        review_profile="static-visual",
        capture_capabilities=caps,
    )
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (1024, 768), "white").save(images / "one.png")
    view = dict(
        id="one",
        path="one.png",
        camera_id="main",
        camera="front",
        projection="perspective",
        time_seconds=0,
        method="synthetic test control",
        producer="test",
        capabilities=["geometry"],
        limitations=["Blank control; not evidence of visibility"],
        covered_prims=["/World"],
        view_roles=["front"],
    )
    spec = images / "spec.json"
    spec.write_text(json.dumps(dict(views=[view], requests={})))
    r = package_evidence(
        preparation=prep,
        view_spec=spec,
        expected_plan_sha256=plan["plan_sha256"],
        out=tmp_path / "packaged",
    )
    assert r["exit_code"] == 3, r
    assert all(c["status"] != "supplied" for c in r["validation"]["capture_requests"])


def test_preflight_can_retain_output_beside_caller_specification(tmp_path):
    root = tmp_path / "delivery"
    root.mkdir()
    s = scene(root)
    s.GetRootLayer().Save()
    selected = tmp_path / "checks.json"
    selected.write_text("[]")
    result = invoke(
        "preflight",
        bundle_root=root,
        candidate="scene.usda",
        checks_file=selected,
        out=tmp_path / "preflight",
    )
    assert result["status"] == "completed", result
    assert result["data"]["checks"] == []
