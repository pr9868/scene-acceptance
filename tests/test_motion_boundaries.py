"""Regression controls for valid USD timing boundaries and tolerance meaning."""
import math
from types import SimpleNamespace

import pytest
from pxr import Gf, Usd, UsdGeom

from scene_acceptance import builtin_packs
from scene_acceptance.coverage import inventory
from scene_acceptance.followups.packs import connection
from scene_acceptance.model import MissingEvidence
from scene_acceptance.motion_timing import elapsed_time_code, positions, read_clock
from scene_acceptance.scene_audit import authored_motion


def stage_context(start=0, end=7, rate=25):
    stage = Usd.Stage.CreateInMemory()
    stage.SetStartTimeCode(start)
    stage.SetEndTimeCode(end)
    stage.SetTimeCodesPerSecond(rate)
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    thing = UsdGeom.Xform.Define(stage, '/World/Thing')
    artifact = SimpleNamespace(stage=stage, layers={}, assets={})
    return stage, thing, SimpleNamespace(artifact=artifact)


def position_parameters(seconds):
    return {'path': '/World/Thing', 'tolerance_m': 0,
            'samples': [{'elapsed_s': seconds, 'world_origin_m': [0, 0, 0]}]}


def test_decimal_second_endpoint_passes_without_broadening_requested_interval():
    stage, thing, context = stage_context()
    thing.AddTranslateOp().Set(Gf.Vec3d(0))
    result = positions(context, position_parameters(.28))
    assert result.status == 'PASS'
    assert result.evidence['findings'][0]['time_code'] == 7
    with pytest.raises(MissingEvidence, match='beyond'):
        positions(context, position_parameters(.280000000001))
    # Explicit time-code requests do not receive the conversion allowance.
    with pytest.raises(MissingEvidence, match='range'):
        builtin_packs.motion(context, {'path': '/World/Thing', 'tolerance_m': 0,
            'samples': [{'time_code': 7.000000000001, 'world_origin_m': [0, 0, 0]}]})


@pytest.mark.parametrize('start,rate,seconds', [(0, 25, .28), (120, 25, .28), (-10, 25, .28), (1001, 29.97, 2)])
def test_endpoint_roundoff_allowance_tracks_floating_point_precision(start, rate, seconds):
    stage, _, _ = stage_context(start, start + seconds * rate, rate)
    clock = read_clock(stage)
    value = elapsed_time_code(clock, seconds)
    assert start <= value <= stage.GetEndTimeCode()
    with pytest.raises(MissingEvidence):
        elapsed_time_code(clock, seconds + 1e-8)


def test_authored_fps_fallback_is_shared_by_timing_and_inventory():
    stage, thing, context = stage_context()
    thing.AddTranslateOp().Set(Gf.Vec3d(0))
    stage.ClearMetadata('timeCodesPerSecond')
    stage.SetFramesPerSecond(25)
    clock = read_clock(stage)
    assert clock['time_codes_per_second'] == 25
    assert (clock['rate_metadata'], clock['rate_layer']) == ('framesPerSecond', 'root')
    structure = inventory(context.artifact)['scene_structure']
    assert structure['clock_authored'] and structure['rate_authored']
    assert structure['rate_metadata'] == 'framesPerSecond'
    assert positions(context, position_parameters(.28)).status == 'PASS'


def test_rate_provenance_follows_usd_precedence_not_layer_strength_alone():
    stage, _, _ = stage_context()
    stage.GetSessionLayer().framesPerSecond = 60
    assert read_clock(stage)['rate_metadata'] == 'timeCodesPerSecond'
    assert read_clock(stage)['rate_layer'] == 'root'
    stage.GetSessionLayer().timeCodesPerSecond = 50
    clock = read_clock(stage)
    assert clock['time_codes_per_second'] == 50 and clock['rate_layer'] == 'session'


def test_wholly_implicit_rate_remains_unassessed_not_invalid_usd():
    stage, _, context = stage_context()
    stage.ClearMetadata('timeCodesPerSecond')
    structure = inventory(context.artifact)['scene_structure']
    assert structure['time_codes_per_second'] == 24
    assert not structure['clock_authored'] and structure['rate_metadata'] == 'schema_default'
    with pytest.raises(MissingEvidence, match='implicit default'):
        read_clock(stage)


@pytest.mark.parametrize('outside_bad', [False, True])
def test_authored_keys_outside_playback_are_valid_but_still_checked_for_finiteness(outside_bad):
    stage, thing, context = stage_context(0, 2, 1)
    op = thing.AddTranslateOp()
    for time, x in [(-1, 0), (0, 0), (2, 1), (3, math.nan if outside_bad else 1)]:
        op.Set(Gf.Vec3d(x, 0, 0), time)
    result = authored_motion(context, {'max_samples_per_prim': 100, 'max_total_samples': 100})
    row = result.evidence['assessment']['items'][0]
    assert result.status == ('FAIL' if outside_bad else 'PASS')
    assert row['authored_keys_outside_playback'] == [-1, 3]
    assert row['interval_sample_time_codes'] == [0, 1, 2]
    assert row['samples_checked'] == 5
    if outside_bad:
        assert row['failed_time_codes'] == [3]


def test_motion_and_connection_expose_their_distinct_error_metrics():
    stage, thing, context = stage_context(0, 1, 1)
    thing.AddTranslateOp().Set(Gf.Vec3d(.001, .001, .001))
    UsdGeom.Xform.Define(stage, '/World/Origin')
    motion = positions(context, {**position_parameters(0), 'tolerance_m': .001})
    row = motion.evidence['findings'][0]
    assert motion.status == 'PASS'
    assert row['maximum_coordinate_error_m'] == .001
    assert row['euclidean_error_m'] == pytest.approx(math.sqrt(3) * .001)
    assert motion.evidence['tolerance_metric'] == 'per_coordinate_metres'
    gap = connection(context, {'a': {'path': '/World/Thing', 'local_point': [0, 0, 0]},
        'b': {'path': '/World/Origin', 'local_point': [0, 0, 0]}, 'interval_s': [0, 1],
        'segments': 1, 'schedule': 'uniform', 'max_gap_m': .001})
    assert gap.status == 'FAIL' and gap.evidence['tolerance_metric'] == 'euclidean_distance_metres'
