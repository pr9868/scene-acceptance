"""Exact interval checks for authored, held USD token/string/bool state."""
from pathlib import Path

from pxr import Sdf

from .builtin_packs import obj, TEXT
from .model import ContractError, MissingEvidence
from .motion_timing import read_clock, elapsed_time_code
from .packs import CheckSpec, Outcome, Pack


def _state(stage, path, *, boolean=False):
    name = Sdf.Path(path)
    if not name.IsAbsolutePath() or not name.IsPropertyPath():
        raise ContractError('State must use an absolute USD attribute path')
    attribute = stage.GetAttributeAtPath(path)
    types = (Sdf.ValueTypeNames.Bool,) if boolean else (
        Sdf.ValueTypeNames.Token, Sdf.ValueTypeNames.String, Sdf.ValueTypeNames.Bool,
    )
    if not attribute or not attribute.HasAuthoredValueOpinion():
        raise MissingEvidence('Missing authored state attribute: ' + path)
    if attribute.GetTypeName() not in types:
        raise MissingEvidence('State intervals require held token/string/bool attributes: ' + path)
    samples = attribute.GetTimeSamples()
    if len(samples) > 10000:
        raise MissingEvidence('State attribute exceeds 10000 authored transitions')
    return attribute, samples


def agreement(ctx, params):
    stage = ctx.artifact.stage
    clock = read_clock(stage)
    start_s, end_s = params['start_s'], params['end_s']
    if end_s <= start_s:
        raise ContractError('State interval must have positive duration')
    start, end = (elapsed_time_code(clock, value) for value in (start_s, end_s))
    actual, actual_times = _state(stage, params['observed_attribute'])
    expected, expected_times = _state(stage, params['expected_attribute'])
    if actual.GetTypeName() != expected.GetTypeName():
        raise MissingEvidence('Compared state attributes must have the same USD type')
    active, active_times = (None, [])
    if params.get('active_attribute'):
        active, active_times = _state(stage, params['active_attribute'], boolean=True)
    boundaries = sorted({start, end, *(t for t in actual_times + expected_times + active_times if start < t < end)})
    if len(boundaries) > 10000:
        raise MissingEvidence('Combined state interval exceeds 10000 transition boundaries')
    findings = []
    skipped = 0
    def seconds(time):
        return (time - clock['start_time_code']) / clock['time_codes_per_second']
    for index, left in enumerate(boundaries):
        right = boundaries[index + 1] if index + 1 < len(boundaries) else left
        enabled = active.Get(left) if active else True
        observed, required = actual.Get(left), expected.Get(left)
        if enabled is None or (enabled and (observed is None or required is None)):
            raise MissingEvidence('State is unresolved at an interval boundary')
        if not enabled:
            skipped += 1
            continue
        findings.append({
            'object': params['observed_attribute'], 'start_s': seconds(left), 'end_s': seconds(right),
            'interval': 'closed endpoint' if left == right else 'left-closed, right-open',
            'observed': observed, 'expected': required,
            'status': 'PASS' if observed == required else 'FAIL',
        })
    return Outcome(
        'FAIL' if any(row['status'] == 'FAIL' for row in findings) else 'PASS' if findings else 'UNKNOWN',
        'Compared every held-state interval and the final endpoint while the declared condition was active.',
        {'clock': clock, 'findings': findings, 'checked_intervals_and_endpoints': len(findings),
         'inactive_intervals_and_endpoints': skipped, 'transition_boundaries': len(boundaries),
         'coverage': 'All authored state transitions for these named attributes inside the declared interval. '
                     'Does not infer parcel occupancy, inspect rendered signs, prove motion or cover external runtime signals.'},
    )


def state_pack():
    number = {'type': 'number', 'minimum': 0}
    parameters = obj({
        'observed_attribute': TEXT, 'expected_attribute': TEXT, 'active_attribute': TEXT,
        'start_s': number, 'end_s': number,
    }, required=['observed_attribute', 'expected_attribute', 'start_s', 'end_s'])
    return Pack('behavior.state', '1.0.0', 'Compare authored discrete state over declared intervals', {
        'agreement': CheckSpec(agreement, parameters,
            'Require two held state attributes to agree, optionally while an occupancy attribute is true',
            'Named USD token/string/bool state over every authored transition and the final endpoint',
            ('Not a continuous geometry or physics proof', 'Reference and activation state must be supplied and justified by the caller')),
    }, (str(Path(__file__)), str(Path(__file__).with_name('motion_timing.py'))), ('usd-core',))
