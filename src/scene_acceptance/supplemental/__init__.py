"""Explicit four-job example requirements, separate from the generic baseline."""

from scene_acceptance.usd_composition import prims as composed_prims
from pathlib import Path
from scene_acceptance.coverage import assessment
from scene_acceptance.model import MissingEvidence
from scene_acceptance.packs import CheckSpec, Outcome, Pack

JOBS = (
    "tray-baseline",
    "tray-translated",
    "panel-png",
    "panel-jpeg",
    "motion",
    "physics-022",
    "physics-042",
    "physics-068",
)
COMMON = ("common.metadata", "common.geometry")
GROUPS = {
    "tray": (
        "tray.dimensions",
        "tray.cavity",
        "tray.closure",
        "tray.transform",
        "tray.fixture",
        "tray.preserved",
    ),
    "panel": (
        "panel.dimensions",
        "panel.shader",
        "panel.uv",
        "panel.pixels",
        "panel.equivalence",
    ),
    "motion": (
        "motion.clock",
        "motion.lengths",
        "motion.cycle",
        "motion.trajectory",
        "motion.connections",
        "motion.geometry",
    ),
    "physics": ("physics.parameters", "physics.preserved"),
}
LIMITS = (
    "Fixed four-job paths, targets and tolerances; selecting a job explicitly adopts that scope.",
    "No general CAD certificate, rendered appearance, continuous-time proof or physical calibration.",
    "Preservation compares root-layer authored fields; it does not prove composed dependency equivalence.",
)


def checks_for(job):
    if job not in JOBS:
        raise ValueError("Unknown four-job preset: " + job)
    names = COMMON + GROUPS[job.split("-")[0]]
    return tuple(n for n in names if n != "tray.preserved" or job == "tray-translated")


def subject_for(name, job):
    if name == "panel.pixels":
        return "textures/label." + ("png" if job.endswith("png") else "jpg")
    if name == "tray.fixture":
        return "/World/Fixture"
    if name.startswith("tray."):
        return "/World/Tray"
    if name.startswith("panel."):
        return "/World/Panel"
    if name.startswith("motion."):
        return "/World/Mechanism"
    if name.startswith("physics."):
        return "/World/Block and /World/Contact"
    return "candidate stage"


def run_check(name, ctx, params):
    job = params["job"]
    subject = subject_for(name, job)
    scope = "One selected requirement comparison under the four-job preset: " + name
    try:
        from . import readbacks

        stage = ctx.artifact.stage
        # Explicit upper bounds for these small example jobs, not a large-scene profiler.
        prim_count = samples = indices = 0
        for p in composed_prims(stage):
            prim_count += 1
            for a in p.GetAuthoredAttributes():
                samples += a.GetNumTimeSamples()
            a = p.GetAttribute("faceVertexIndices")
            if a:
                indices += len(a.Get() or [])
            if prim_count > 10000 or samples > 100000 or indices > 150000:
                raise MissingEvidence(
                    "Four-job readback budget exceeded (10000 prims, 100000 keys, 150000 face indices)"
                )
        if name.startswith("common."):
            result = readbacks.common(stage, name)
        elif name.startswith("tray."):
            if job == "tray-translated" and ctx.baseline is None:
                raise MissingEvidence(
                    "Translated-tray preset requires an admitted baseline"
                )
            result = readbacks.tray(
                stage, name, ctx.baseline.stage if job == "tray-translated" else None
            )
        elif name.startswith("panel."):
            if name == "panel.equivalence" and "reference.usda" not in ctx.sources:
                raise MissingEvidence(
                    "Declare reference.usda in evidence_sources for sibling comparison"
                )
            result = readbacks.panel(stage, ctx.bundle, job.split("-")[1], name)
        elif name.startswith("motion."):
            result = readbacks.motion(stage, name)
        else:
            if name == "physics.preserved" and "physics-base.usda" not in ctx.sources:
                raise MissingEvidence(
                    "Declare physics-base.usda in evidence_sources for preservation"
                )
            result = readbacks.physics(
                stage, ctx.bundle, int(job.split("-")[1]) / 100, name
            )
    except MissingEvidence as exc:
        result = Outcome("UNKNOWN", str(exc))
    evidence = dict(result.evidence)
    unit = "declared comparisons"
    items = [dict(subject=subject, status=result.status, reason=result.reason)]
    sample_keys = {
        "motion.lengths": (
            (
                "centre_error_m",
                "radius_error_m",
                "rod_length_error_m",
                "slider_line_error_m",
            ),
            1e-6,
        ),
        "motion.connections": (("crank_gap_m", "slider_gap_m"), 0.0005),
        "motion.trajectory": (
            ("crank_trajectory_error_m", "slider_trajectory_error_m"),
            0.0005,
        ),
    }
    if name in sample_keys and "samples" in evidence:
        keys, limit = sample_keys[name]
        unit = "mechanism samples"
        items = [
            dict(
                subject=f"{r['elapsed_s']} s",
                status="PASS" if max(r[k] for k in keys) <= limit else "FAIL",
                reason="Selected positional errors/gaps compared at this time",
                sample_index=i,
                maximum_error_m=max(r[k] for k in keys),
                limit_m=limit,
            )
            for i, r in enumerate(evidence["samples"])
        ]
        scope = "Finite diagnostic samples for one mechanism; cycle closure and continuous motion are separate obligations."
    evidence["assessment"] = assessment(unit, items, scope)
    evidence["preset"] = job
    evidence["limits"] = list(LIMITS)
    return Outcome(result.status, result.reason, evidence)


def four_job_pack():
    names = COMMON + tuple(n for values in GROUPS.values() for n in values)
    checks = {}
    for name in names:
        jobs = [j for j in JOBS if name in checks_for(j)]
        parameters = {
            "type": "object",
            "properties": {"job": {"enum": jobs}},
            "required": ["job"],
            "additionalProperties": False,
        }
        checks[name] = CheckSpec(
            lambda ctx, params, name=name: run_check(name, ctx, params),
            parameters,
            "Four-job preset: " + name,
            "Explicit named comparison; see docs/SUPPLEMENTAL_CHECKS.md for every fixed target.",
            LIMITS,
        )
    return Pack(
        "brief.four-job",
        "1.1.0",
        "Bounded supplemental requirements for the frozen four-job example",
        checks,
        (
            str(Path(__file__)),
            str(Path(__file__).with_name("readbacks.py")),
            str(Path(__file__).parent.parent / "usd_composition.py"),
        ),
        ("usd-core", "numpy", "Pillow"),
    )
