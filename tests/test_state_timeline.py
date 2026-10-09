"""Owner-controlled expectations cannot be satisfied by editing scene reference state."""

import pytest
from pxr import Sdf
from scene_acceptance.model import ContractError
from scene_acceptance.state_intervals import timeline
from test_extensions_geometry import scene, context
from test_semantic_packs import bundle

PARAMS = dict(
    observed_attribute="/World.indicator",
    start_s=0,
    end_s=10,
    expected_timeline=[
        dict(time_s=0, value="A"),
        dict(time_s=4, value="B"),
        dict(time_s=8, value="A"),
    ],
)


def state(stage, values):
    a = stage.GetPrimAtPath("/World").CreateAttribute(
        "indicator", Sdf.ValueTypeNames.Token
    )
    for time, value in values:
        a.Set(value, time)
    return a


@pytest.mark.parametrize(
    "fault", ["none", "between", "endpoint", "both-wrong", "inactive-scene"]
)
def test_owner_timeline_checks_every_transition(tmp_path, fault):
    def build(stage):
        a = state(stage, [(0, "A"), (4, "B"), (8, "A")])
        if fault == "between":
            a.Set("A", 5.001)
            a.Set("B", 5.002)
        elif fault == "endpoint":
            a.Set("B", 10)
        elif fault in ("both-wrong", "inactive-scene"):
            a.Clear()
            a.Set("WRONG")
            stage.GetPrimAtPath("/World").CreateAttribute(
                "route", Sdf.ValueTypeNames.Token
            ).Set("WRONG")
            stage.GetPrimAtPath("/World").CreateAttribute(
                "occupied", Sdf.ValueTypeNames.Bool
            ).Set(False)

    report, row = bundle(tmp_path, "behavior.state", "timeline", PARAMS, build)
    assert row["status"] == ("PASS" if fault == "none" else "FAIL"), report
    assert row["evidence"]["observations"]["reference_source"] == "contract_timeline"
    if fault == "between":
        failed = [
            r
            for r in row["evidence"]["observations"]["findings"]
            if r["status"] == "FAIL"
        ]
        assert len(failed) == 1
        assert failed[0]["start_s"] == 5.001 and failed[0]["end_s"] == 5.002


@pytest.mark.parametrize(
    "entries",
    [
        [],
        [dict(time_s=1, value="A")],
        [dict(time_s=0, value="A"), dict(time_s=0, value="B")],
        [dict(time_s=0, value="A"), dict(time_s=11, value="B")],
        [dict(time_s=0, value="A"), dict(time_s=float("nan"), value="B")],
        [dict(time_s=0, value=True)],
    ],
)
def test_invalid_owner_schedule_is_contract_error(tmp_path, entries):
    stage = scene(tmp_path)
    state(stage, [(0, "A")])
    with pytest.raises(ContractError):
        timeline(context(stage, tmp_path), dict(PARAMS, expected_timeline=entries))


@pytest.mark.parametrize("kind", ["token", "string", "bool"])
def test_owner_controls_activation_and_value_type(tmp_path, kind):
    stage = scene(tmp_path)
    value = True if kind == "bool" else "OK"
    stage.GetPrimAtPath("/World").CreateAttribute(
        "indicator", getattr(Sdf.ValueTypeNames, kind.title())
    ).Set(value)
    params = dict(
        PARAMS,
        expected_timeline=[
            dict(time_s=0, value=value, active=False),
            dict(time_s=4, value=value),
        ],
    )
    row = timeline(context(stage, tmp_path), params)
    assert (
        row.status == "PASS" and row.evidence["inactive_intervals_and_endpoints"] == 1
    )
    params["expected_timeline"] = [dict(time_s=0, value=value, active=False)]
    assert timeline(context(stage, tmp_path), params).status == "UNKNOWN"
