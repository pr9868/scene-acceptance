"""Exact interval checks for authored, held USD token/string/bool state."""

from pathlib import Path
from bisect import bisect_right
import math

from pxr import Sdf

from .builtin_packs import obj, TEXT
from .model import ContractError, MissingEvidence
from .motion_timing import read_clock, elapsed_time_code
from .packs import CheckSpec, Outcome, Pack


def _state(stage, path, *, boolean=False):
    name = Sdf.Path(path)
    if not name.IsAbsolutePath() or not name.IsPropertyPath():
        raise ContractError("State must use an absolute USD attribute path")
    attribute = stage.GetAttributeAtPath(path)
    types = (
        (Sdf.ValueTypeNames.Bool,)
        if boolean
        else (
            Sdf.ValueTypeNames.Token,
            Sdf.ValueTypeNames.String,
            Sdf.ValueTypeNames.Bool,
        )
    )
    if not attribute or not attribute.HasAuthoredValueOpinion():
        raise MissingEvidence("Missing authored state attribute: " + path)
    if attribute.GetTypeName() not in types:
        raise MissingEvidence(
            "State intervals require held token/string/bool attributes: " + path
        )
    samples = attribute.GetTimeSamples()
    if len(samples) > 10000:
        raise MissingEvidence("State attribute exceeds 10000 authored transitions")
    return attribute, samples


def agreement(ctx, params):
    stage = ctx.artifact.stage
    clock = read_clock(stage)
    start_s, end_s = params["start_s"], params["end_s"]
    if end_s <= start_s:
        raise ContractError("State interval must have positive duration")
    start, end = (elapsed_time_code(clock, value) for value in (start_s, end_s))
    actual, actual_times = _state(stage, params["observed_attribute"])
    expected, expected_times = _state(stage, params["expected_attribute"])
    if actual.GetTypeName() != expected.GetTypeName():
        raise MissingEvidence("Compared state attributes must have the same USD type")
    active, active_times = (None, [])
    if params.get("active_attribute"):
        active, active_times = _state(stage, params["active_attribute"], boolean=True)
    return _compare(
        params,
        clock,
        start,
        end,
        actual,
        actual_times + expected_times + active_times,
        lambda time: (expected.Get(time), active.Get(time) if active else True),
        "scene_attributes",
    )


def timeline(ctx, params):
    """Compare saved state with an owner-reviewed schedule in the contract."""
    stage = ctx.artifact.stage
    clock = read_clock(stage)
    start_s, end_s = params["start_s"], params["end_s"]
    if end_s <= start_s or not math.isfinite(start_s + end_s):
        raise ContractError("State interval must be finite with positive duration")
    start, end = (elapsed_time_code(clock, value) for value in (start_s, end_s))
    actual, actual_times = _state(stage, params["observed_attribute"])
    entries = params["expected_timeline"]
    times = [entry["time_s"] for entry in entries]
    if (
        not times
        or times[0] != start_s
        or any(not math.isfinite(t) or t < start_s or t > end_s for t in times)
        or any(a >= b for a, b in zip(times, times[1:]))
    ):
        raise ContractError(
            "Expected timeline must start at start_s and increase strictly within the interval"
        )
    value_type = bool if actual.GetTypeName() == Sdf.ValueTypeNames.Bool else str
    if any(type(entry["value"]) is not value_type for entry in entries):
        raise ContractError(
            "Expected timeline values must match the observed USD state type"
        )
    codes = [elapsed_time_code(clock, t) for t in times]
    if any(a >= b for a, b in zip(codes, codes[1:])):
        raise ContractError(
            "Timeline transitions collapse at this stage clock precision"
        )

    def required(time):
        entry = entries[bisect_right(codes, time) - 1]
        return entry["value"], entry.get("active", True)

    return _compare(
        params,
        clock,
        start,
        end,
        actual,
        actual_times + codes,
        required,
        "contract_timeline",
    )


def _compare(params, clock, start, end, actual, times, required_at, reference_source):
    boundaries = sorted(
        {
            start,
            end,
            *(t for t in times if start < t < end),
        }
    )
    if len(boundaries) > 10000:
        raise MissingEvidence(
            "Combined state interval exceeds 10000 transition boundaries"
        )
    findings = []
    skipped = 0

    def seconds(time):
        return (time - clock["start_time_code"]) / clock["time_codes_per_second"]

    for index, left in enumerate(boundaries):
        right = boundaries[index + 1] if index + 1 < len(boundaries) else left
        required, enabled = required_at(left)
        observed = actual.Get(left)
        if enabled is None or (enabled and (observed is None or required is None)):
            raise MissingEvidence("State is unresolved at an interval boundary")
        if not enabled:
            skipped += 1
            continue
        findings.append(
            {
                "object": params["observed_attribute"],
                "start_s": seconds(left),
                "end_s": seconds(right),
                "interval": (
                    "closed endpoint" if left == right else "left-closed, right-open"
                ),
                "observed": observed,
                "expected": required,
                "status": "PASS" if observed == required else "FAIL",
            }
        )
    return Outcome(
        (
            "FAIL"
            if any(row["status"] == "FAIL" for row in findings)
            else "PASS" if findings else "UNKNOWN"
        ),
        "Compared every held-state interval and the final endpoint while the declared condition was active.",
        {
            "clock": clock,
            "findings": findings,
            "checked_intervals_and_endpoints": len(findings),
            "inactive_intervals_and_endpoints": skipped,
            "transition_boundaries": len(boundaries),
            "reference_source": reference_source,
            "coverage": "All authored state transitions for these named attributes inside the declared interval. "
            "Does not infer parcel occupancy, inspect rendered signs, prove motion or cover external runtime signals.",
        },
    )


def state_pack():
    number = {"type": "number", "minimum": 0}
    parameters = obj(
        {
            "observed_attribute": TEXT,
            "expected_attribute": TEXT,
            "active_attribute": TEXT,
            "start_s": number,
            "end_s": number,
        },
        required=["observed_attribute", "expected_attribute", "start_s", "end_s"],
    )
    return Pack(
        "behavior.state",
        "1.1.0",
        "Compare authored discrete state over declared intervals",
        {
            "agreement": CheckSpec(
                agreement,
                parameters,
                "Check internal consistency between two held scene attributes, optionally while an occupancy attribute is true",
                "Named USD token/string/bool state over every authored transition and the final endpoint",
                (
                    "Not a continuous geometry or physics proof",
                    "Both reference and activation come from the scene; matching values do not prove owner intent",
                ),
            ),
            "timeline": CheckSpec(
                timeline,
                obj(
                    {
                        "observed_attribute": TEXT,
                        "start_s": number,
                        "end_s": number,
                        "expected_timeline": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 10000,
                            "items": obj(
                                {
                                    "time_s": number,
                                    "value": {"type": ["string", "boolean"]},
                                    "active": {"type": "boolean"},
                                },
                                required=["time_s", "value"],
                            ),
                        },
                    }
                ),
                "Compare held scene state with an owner-reviewed contract timeline",
                "All observed and expected transitions and the final endpoint; activation is controlled by the contract",
                (
                    "The caller must review and protect the contract independently of the producer",
                    "Does not infer state from geometry or rendered indicators",
                ),
            ),
        },
        (str(Path(__file__)), str(Path(__file__).with_name("motion_timing.py"))),
        ("usd-core",),
    )
