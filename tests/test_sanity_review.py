"""Caller settings, repair coverage and adapter replay must stay consistent."""

from copy import deepcopy
import json
import pytest

from scene_acceptance.model import ContractError
from scene_acceptance.preparation import prepare_scene
from scene_acceptance.review_context import save
from test_preparation import bundle, setup
from test_public_adapter import module, request


@pytest.mark.parametrize(
    "limit,resolution,ready,attempts", [(64, 64, True, 0), (1024, 2048, False, 1)]
)
def test_revision_preflight_uses_caller_capture_overrides(
    bundle, tmp_path, limit, resolution, ready, attempts
):
    kw = setup(tmp_path, bundle)
    adapter = tmp_path / "interpreter.py"
    adapter.write_text(adapter.read_text().replace("min_width=64", "min_width=128"))
    caps = json.loads(kw["capture_capabilities"].read_text())
    caps["max_width"] = limit
    save(kw["capture_capabilities"], caps)
    capture = dict(
        id="label-view",
        purpose="Inspect label",
        targets=["/World/Panel"],
        times_seconds=[0],
        camera_guidance="Front close-up",
        view_role="front",
        sharing_group=None,
        camera_id=None,
        projection=None,
        capabilities=["geometry", "surface_materials"],
        min_width=resolution,
        min_height=64,
        limitations=["Visible face only"],
    )
    overrides = tmp_path / "overrides.json"
    save(
        overrides,
        dict(schema_version="1.0", id="caller", version="1.0.0", requests=[capture]),
    )
    result = prepare_scene(**kw, capture_overrides=overrides, plan_revision_attempts=1)
    log = json.loads((kw["out"] / "revision-attempts.json").read_text())
    assert len(log["attempts"]) == attempts
    assert result["readiness"]["ready_for_capture"] is ready
    if attempts:
        feedback = json.loads(
            (kw["out"] / "interpreter-revision-1/full-context.json").read_text()
        )["plan_revision"]["feedback"]
        assert feedback["captures"][0]["min_width"] == resolution
        assert feedback["readiness"]["ready_for_capture"] is False


def test_interpreter_cannot_change_its_configuration_during_preparation(
    bundle, tmp_path
):
    kw = setup(tmp_path, bundle)
    adapter = tmp_path / "interpreter.py"
    adapter.write_text(
        "from pathlib import Path\n"
        + f"Path({str(kw['interpreter_config'])!r}).write_text('{{}}')\n"
        + adapter.read_text()
    )
    with pytest.raises(ContractError, match="changed|Interpreter failed"):
        prepare_scene(**kw)


@pytest.mark.parametrize("field", ["version", "instruction"])
def test_public_replay_refuses_changed_protocol(field):
    original = request()
    provider = dict(
        identity=dict(model="control"), command=["unused"], timeout_seconds=1
    )
    record = dict(
        reuse_key=module.reuse_key(original, provider),
        request_sha256=original["request_sha256"],
        response=dict(request_sha256=original["request_sha256"], answer="old"),
    )
    changed = deepcopy(original)
    changed["model_protocol"][field] += " changed"
    with pytest.raises(ValueError, match="does not match"):
        module.exchange(changed, provider, replay=record)
