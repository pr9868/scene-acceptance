"""Clock requirements and sampled positions in elapsed seconds.

The original motion pack keeps its explicit-time-code contract. This pack reads
an authored clock and checks requirements relative to the stage's start time.
It does not infer when an object starts or stops moving.
"""

from pathlib import Path
import math

from . import builtin_packs
from .model import ContractError, MissingEvidence
from .packs import CheckSpec, Outcome, Pack


def read_clock(stage):
    if not stage.HasAuthoredMetadata("timeCodesPerSecond"):
        raise MissingEvidence("An authored timeCodesPerSecond is required; fallback rates are not accepted")
    if not stage.HasAuthoredTimeCodeRange():
        raise MissingEvidence("An authored start and end time code are required")
    rate = stage.GetTimeCodesPerSecond()
    start, end = stage.GetStartTimeCode(), stage.GetEndTimeCode()
    if not math.isfinite(rate) or rate <= 0:
        raise MissingEvidence("The authored time-code rate must be finite and positive")
    if not all(math.isfinite(x) for x in (start, end)) or end < start:
        raise MissingEvidence("The authored time range must be finite and ordered")
    duration = (end - start) / rate
    if not math.isfinite(duration):
        raise MissingEvidence("The authored duration cannot be represented as finite seconds")
    return {
        "time_codes_per_second": rate,
        "start_time_code": start,
        "end_time_code": end,
        "duration_s": duration,
    }


def clock(ctx, params):
    observed = read_clock(ctx.artifact.stage)
    delta = abs(observed["duration_s"] - params["duration_s"])
    findings = [{
        "object": "/",
        "property": "stage_duration_s",
        "observed": observed["duration_s"],
        "expected": params["duration_s"],
        "tolerance_s": params["tolerance_s"],
        "status": "PASS" if delta <= params["tolerance_s"] else "FAIL",
    }]
    if "time_codes_per_second" in params:
        findings.append({
            "object": "/",
            "property": "timeCodesPerSecond",
            "observed": observed["time_codes_per_second"],
            "expected": params["time_codes_per_second"],
            "status": "PASS" if observed["time_codes_per_second"] == params["time_codes_per_second"] else "FAIL",
        })
    return Outcome(
        "FAIL" if any(x["status"] == "FAIL" for x in findings) else "PASS",
        "Authored stage duration and optional exact time-code rate compared with the contract.",
        {"clock": observed, "findings": findings,
         "coverage": "Authored stage interval only; not the onset, completion or continuous path of object motion."},
    )


def positions(ctx, params):
    observed_clock = read_clock(ctx.artifact.stage)
    elapsed = [sample["elapsed_s"] for sample in params["samples"]]
    if any(a >= b for a, b in zip(elapsed, elapsed[1:])):
        raise ContractError("Elapsed-second samples must be strictly increasing")
    if any(t > observed_clock["duration_s"] for t in elapsed):
        raise MissingEvidence("Requested elapsed seconds extend beyond the authored stage duration")
    converted = []
    for sample in params["samples"]:
        t = observed_clock["start_time_code"] + sample["elapsed_s"] * observed_clock["time_codes_per_second"]
        if not math.isfinite(t):
            raise MissingEvidence("Elapsed seconds cannot be converted to a finite time code")
        converted.append({"time_code": t, "world_origin_m": sample["world_origin_m"]})
    result = builtin_packs.motion(ctx, {
        "path": params["path"],
        "tolerance_m": params["tolerance_m"],
        "samples": converted,
    })
    evidence = {**result.evidence, "clock": observed_clock,
                "elapsed_seconds": elapsed, "seconds_origin": "authored stage startTimeCode",
                "coverage": "Named world origins at requested elapsed seconds; no orientation, continuous-path, collision or physics proof."}
    reason = result.reason
    if "findings" in result.evidence:
        evidence["findings"] = [
            {**finding, "elapsed_s": seconds}
            for finding, seconds in zip(result.evidence["findings"], elapsed)
        ]
        reason = "World origins compared at elapsed seconds measured from the authored stage start."
    return Outcome(result.status, reason, evidence)


def timing_pack():
    nonnegative = {"type": "number", "minimum": 0}
    return Pack(
        "motion.timing", "1.0.0",
        "Authored clock requirements and world-origin samples in elapsed seconds",
        {
            "clock": CheckSpec(
                clock,
                builtin_packs.obj({
                    "duration_s": nonnegative,
                    "tolerance_s": nonnegative,
                    "time_codes_per_second": {"type": "number", "exclusiveMinimum": 0},
                }, required=["duration_s", "tolerance_s"]),
                "Check authored stage duration and optionally require an exact clock rate",
                "Authored stage time range converted to seconds",
                ("Does not infer active motion duration; an authored positive clock and complete time range are required",),
            ),
            "positions": CheckSpec(
                positions,
                builtin_packs.obj({
                    "path": builtin_packs.TEXT,
                    "tolerance_m": nonnegative,
                    "samples": {
                        "type": "array", "minItems": 1, "maxItems": 1000,
                        "items": builtin_packs.obj({"elapsed_s": nonnegative, "world_origin_m": builtin_packs.VEC3}),
                    },
                }),
                "Compare named world origins at elapsed seconds from the authored stage start",
                "Named world origins at the requested elapsed seconds",
                ("No continuous-time, orientation, collision or physics proof", "Requires authored clock and time range"),
            ),
        },
        (str(Path(__file__)), str(Path(builtin_packs.__file__))),
        ("usd-core",),
    )
