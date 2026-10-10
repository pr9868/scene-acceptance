"""Shared preparation/rebinding prerequisites; never a visibility judgment."""

from .model import ContractError
from .preflight import capture_budget


def apply_overrides(captures, overrides, prim_paths, duration):
    """Apply caller-owned replacements identically in preview and final scope."""
    if overrides is None:
        return
    lookup = {c["id"]: c for c in captures}
    used = set()
    for capture in overrides["requests"]:
        if capture["id"] not in lookup or capture["id"] in used:
            raise ContractError("Unknown or duplicate capture override ID")
        used.add(capture["id"])
        original = lookup[capture["id"]]
        if set(capture["targets"]) - set(prim_paths):
            raise ContractError("Capture override names unknown target")
        if any(t > duration + 1e-6 for t in capture["times_seconds"]):
            raise ContractError("Capture override exceeds scene duration")
        required = (
            "surface_materials"
            if original["evidence_kind"] == "textured_view"
            else "geometry"
        )
        if required not in capture["capabilities"]:
            raise ContractError("Capture override removes required fidelity")
        if (
            original["evidence_kind"] == "motion_frames"
            and len(capture["times_seconds"]) < 3
        ):
            raise ContractError("Motion override needs three or more timestamps")
        original.update(capture)


def capture_feasibility(
    captures, caps, reference_count, *, prim_paths=None, duration=None
):
    budget = min(caps["max_images"], 12 - reference_count)
    for capture in captures:
        gaps = []
        if prim_paths is not None and set(capture["targets"]) - set(prim_paths):
            gaps.append("Required target is absent from this candidate")
        if duration is not None and any(
            t > duration + 1e-6 for t in capture["times_seconds"]
        ):
            gaps.append(
                "Requested time is outside this candidate; requirement remains unchanged"
            )
        if set(capture["capabilities"]) - set(caps["capabilities"]):
            gaps.append("Caller lacks requested capture capability")
        if (
            capture["min_width"] > caps["max_width"]
            or capture["min_height"] > caps["max_height"]
        ):
            gaps.append("Requested resolution exceeds caller capability")
        if (
            capture["evidence_kind"] == "motion_frames"
            and len(capture["times_seconds"]) < 3
        ):
            gaps.append("Scene has no positive authored motion interval")
        if len(capture["times_seconds"]) > budget:
            gaps.append("This request exceeds the declared image budget")
        capture["feasibility_gaps"] = gaps
    return budget, capture_budget(captures, budget)
