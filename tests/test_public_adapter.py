"""Public adapter reuse is explicit and tied to actual projected context."""

import importlib.util
from pathlib import Path
from copy import deepcopy
import sys
import pytest
from scene_acceptance.model_protocol import prepare_request

spec = importlib.util.spec_from_file_location(
    "public_adapter", Path(__file__).parents[1] / "examples/json-cli-adapter/adapter.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def request(path="/one/image.png", limit=16):
    r = dict(
        evidence=[dict(image_path=path)],
        scene=dict(prim_paths=[f"/Part{i}" for i in range(30)], inventory={}),
    )
    schema = dict(
        type="object",
        properties={"request_sha256": {"type": "string"}, "answer": {"type": "string"}},
        required=["request_sha256", "answer"],
        additionalProperties=False,
    )
    prepare_request(r, "judge", schema, limit, {path: "1" * 64})
    return r


def test_public_schema_fresh_and_explicit_replay(tmp_path):
    script = tmp_path / "provider.py"
    script.write_text(
        'import json,sys\np=json.load(sys.stdin)\nassert p["response_schema"]["required"]==["request_sha256","answer"]\nprint(json.dumps(dict(request_sha256=p["request"]["request_sha256"],answer="control")))\n'
    )
    provider = dict(
        identity=dict(model="test-control", effort="none", adapter_version="1"),
        command=[sys.executable, str(script)],
        timeout_seconds=5,
    )
    response, record = module.exchange(request(), provider)
    assert record["mode"] == "fresh"
    relocated = request("/two/image.png")
    response, replay = module.exchange(relocated, provider, replay=record)
    assert response["request_sha256"] == relocated["request_sha256"]
    assert replay["mode"] == "replay"
    for changed, config in [
        (request(limit=24), provider),
        (relocated, dict(provider, identity=dict(model="changed"))),
    ]:
        with pytest.raises(ValueError, match="does not match"):
            module.exchange(changed, config, replay=record)
    corrupt = deepcopy(record)
    corrupt["response"]["request_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="transport"):
        module.exchange(relocated, provider, replay=corrupt)
