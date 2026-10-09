"""Coverage is measured separately from a contract verdict and scene inventory."""

from scene_acceptance.usd_composition import prims as composed_prims
from collections import Counter
from pxr import Sdf, UsdGeom, UsdShade, UsdPhysics

SUBJECT_STATUSES = ("PASS", "FAIL", "WARNING", "UNKNOWN", "ERROR", "SKIPPED")


def assessment(unit, items, scope, **extra):
    """Each subject has one exclusive status; warning subjects are not clean passes."""
    counts = Counter(x["status"] for x in items)
    return dict(
        unit=unit,
        scope=scope,
        candidate_count=len(items),
        assessed_count=sum(counts[s] for s in ("PASS", "FAIL", "WARNING")),
        **{s.lower() + "_count": counts[s] for s in SUBJECT_STATUSES},
        items=items,
        **extra,
    )


def inventory(artifact):
    from .motion_timing import rate_metadata

    stage = artifact.stage
    types = Counter()
    counts = Counter()
    animated = []
    assets = []
    for p in composed_prims(stage):
        types[p.GetTypeName() or "(untyped)"] += 1
        counts["prims"] += 1
        if not p.IsActive():
            counts["inactive_prims"] += 1
        for name, cls in [
            ("meshes", UsdGeom.Mesh),
            ("boundables", UsdGeom.Boundable),
            ("materials", UsdShade.Material),
            ("shaders", UsdShade.Shader),
            ("joints", UsdPhysics.Joint),
            ("physics_scenes", UsdPhysics.Scene),
        ]:
            if p.IsA(cls):
                counts[name] += 1
        if p.HasAPI(UsdPhysics.RigidBodyAPI):
            counts["rigid_bodies"] += 1
        if p.HasAPI(UsdPhysics.CollisionAPI):
            counts["colliders"] += 1
        for a in p.GetAuthoredAttributes():
            n = a.GetNumTimeSamples()
            if n:
                counts["time_sampled_attributes"] += 1
                counts["authored_time_samples"] += n
                if a.GetName().startswith("xformOp:"):
                    animated.append(str(p.GetPath()))
            if a.GetTypeName() in (
                Sdf.ValueTypeNames.Asset,
                Sdf.ValueTypeNames.AssetArray,
            ):
                assets.append(str(a.GetPath()))
    # Explicit zero is known absence. Missing inventory (admission failure) is unknown.
    names = (
        "prims",
        "inactive_prims",
        "meshes",
        "boundables",
        "materials",
        "shaders",
        "joints",
        "physics_scenes",
        "rigid_bodies",
        "colliders",
        "time_sampled_attributes",
        "authored_time_samples",
    )
    result = {n: counts[n] for n in names}
    result.update(
        prim_types=dict(sorted(types.items())),
        animated_transform_prims=len(set(animated)),
        asset_attributes=len(assets),
        layers=len(artifact.layers),
        external_files=len(artifact.assets),
        missing_external_files=sum(v is None for v in artifact.assets.values()),
        closure_files=len(artifact.layers) + len(artifact.assets),
        scope="Composed prims, including instance proxies and inactive prims; unique files in the admitted closure. Inventory is not validation.",
    )
    hierarchy = []
    for p in composed_prims(stage):
        if p.GetPath().pathElementCount <= 2:
            if len(hierarchy) == 32:
                break
            hierarchy.append(
                dict(path=str(p.GetPath()), type=p.GetTypeName() or "(untyped)")
            )
    result["scene_structure"] = dict(
        default_prim=str(stage.GetDefaultPrim().GetPath()),
        meters_per_unit=UsdGeom.GetStageMetersPerUnit(stage),
        up_axis=str(UsdGeom.GetStageUpAxis(stage)),
        units_authored=stage.HasAuthoredMetadata("metersPerUnit"),
        up_axis_authored=stage.HasAuthoredMetadata("upAxis"),
        start_time_code=stage.GetStartTimeCode(),
        end_time_code=stage.GetEndTimeCode(),
        time_codes_per_second=stage.GetTimeCodesPerSecond(),
        **rate_metadata(stage),
        clock_authored=stage.HasAuthoredTimeCodeRange()
        and rate_metadata(stage)["rate_authored"],
        hierarchy=hierarchy,
        hierarchy_scope="First 32 composed prims at the first two hierarchy levels; not the complete tree.",
    )
    return result


def summarize_observations(item, record):
    obs = record.get("evidence", {}).get("observations", {})
    if not isinstance(obs, dict):
        return None
    if "assessment" in obs:
        a = obs["assessment"]
        try:
            if not isinstance(a["unit"], str) or not isinstance(a["scope"], str):
                return None
            if any(
                not isinstance(x["subject"], str) or x["status"] not in SUBJECT_STATUSES
                for x in a["items"]
            ):
                return None
            computed = assessment(a["unit"], a["items"], a["scope"])
            if any(a[k] != v for k, v in computed.items() if k.endswith("_count")):
                return None
            return a
        except (TypeError, KeyError, AttributeError):
            return None
    pack = item["pack"]
    # Native validators expose a stage result, not a visited-object denominator.
    if pack == "openusd" and "executed" in obs:
        rows = []
        for name in obs["executed"]:
            issues = [x for x in obs.get("issues", []) if x.get("validator") == name]
            statuses = {x.get("severity") for x in issues}
            status = (
                "FAIL"
                if "Error" in statuses
                else "WARNING" if "Warn" in statuses else "PASS"
            )
            rows.append(dict(subject=name, status=status, finding_count=len(issues)))
        return assessment(
            "stage-validator invocations",
            rows,
            "Native provider stage invocations; per-object coverage is not exposed. A clean stage invocation is not a count of passing assets.",
        )
    if (
        pack
        in (
            "materials",
            "motion",
            "motion.timing",
            "behavior.state",
            "process.connections",
        )
        and "findings" in obs
    ):
        rows = [
            dict(
                subject=x.get("object", x.get("property", "measurement")),
                status=x["status"],
                evidence_index=i,
            )
            for i, x in enumerate(obs["findings"])
            if "status" in x
        ]
        return assessment(
            "comparisons", rows, obs.get("coverage", "Selected requirement comparisons")
        )
    if pack == "textures.decode" and item["check"] == "image":
        return assessment(
            "selected texture attributes",
            [
                dict(
                    subject=item["parameters"]["asset_attribute"],
                    status=record["status"],
                )
            ],
            "One explicitly selected image; no appearance comparison.",
        )
    if pack == "motion.connection" and "samples" in obs:
        rows = [
            dict(
                subject=f"{x['elapsed_s']} s",
                status="PASS" if x["gap_m"] <= obs["max_gap_m"] else "FAIL",
                evidence_index=i,
            )
            for i, x in enumerate(obs["samples"])
        ]
        return assessment("connection samples", rows, obs["coverage"], connections=1)
    if pack == "physics.incline-worker":
        worker = obs.get("worker", {})
        return assessment(
            "simulation jobs",
            [
                dict(
                    subject=obs.get("job_sha256", "requested job"),
                    status=record["status"],
                )
            ],
            "Fixed incline adapter only. Job/trajectory validation is not physical calibration.",
            trajectory_samples=len(worker.get("trace", [])),
        )
    return None


def domain_for(item):
    pack = item["pack"]
    params = item.get("parameters", {})
    if pack == "brief.measurements":
        if item["check"] == "metadata" and any(
            k in params.get("values", {})
            for k in ("startTimeCode", "endTimeCode", "timeCodesPerSecond")
        ):
            return "motion_requirements"
        return (
            "texture_content"
            if item["check"] == "image_pixels"
            else "structure_geometry"
        )
    if pack == "brief.four-job":
        name = item["check"]
        if name == "panel.pixels":
            return "texture_content"
        if name == "panel.uv":
            return "uv_mapping"
        if name in ("panel.shader", "panel.equivalence"):
            return "material_delivery"
        if name.startswith("motion."):
            return "motion_requirements"
        if name.startswith("physics."):
            return "physics_structure"
        return "structure_geometry"
    if pack == "behavior.state":
        return "behavior_state"
    if pack == "process.connections":
        return "process_topology"
    if pack == "scene.audit":
        return {
            "files": "material_delivery",
            "textures": "texture_readability",
            "authored_motion": "authored_motion",
        }[item["check"]]
    if pack.startswith("textures."):
        return "texture_readability"
    if pack in ("motion", "motion.timing", "motion.connection"):
        return "motion_requirements"
    if pack.startswith("physics."):
        return "simulation"
    if pack == "materials":
        return "material_delivery"
    names = " ".join(params.get("validators", []) + params.get("rules", []))
    if "Physics" in names or "physics" in names:
        return "physics_structure"
    if "Material" in names or "Shade" in names or "MissingReference" in names:
        return "material_delivery"
    return "structure_geometry"


DOMAIN_NOTES = {
    "behavior_state": "Named held-state attributes over all authored transitions in a declared interval; no rendered or external runtime state proof.",
    "process_topology": "Named equipment, ports and saved relationships against a structured reference; no diagram extraction or engineering fitness proof.",
    "structure_geometry": "Selected USD/geometry rules only; no general dimensional or shape-intent acceptance.",
    "material_delivery": "Bindings/dependencies only; availability can depend on the target renderer runtime.",
    "texture_readability": "Selected image formats/limits; decoding does not establish the intended image, UVs or rendered appearance.",
    "texture_content": "Explicit reference-pattern comparisons only; this does not establish rendered appearance.",
    "uv_mapping": "Selected authored coordinate/interpolation/coverage rules; no renderer orientation observation.",
    "authored_motion": "Authored transform samples only; no target motion, contact, collision or continuous-time guarantee.",
    "motion_requirements": "Needs named objects/connection points, target values, timing and tolerances in the contract.",
    "physics_structure": "Authored physics schemas only; not simulation or physical behavior.",
    "simulation": "Needs a supported engine adapter, task criteria and matching runtime evidence.",
    "rendered_appearance": "Needs a renderer, suitable reference and an explicit comparison; none selected by the baseline.",
    "task_intent": "Coverage of the full task brief requires an independently supplied requirement map; it is not inferred from the scene.",
    "physical_reference": "Measured parameters and suitable real-world reference evidence are not supplied by the generic baseline.",
}


def enrich(report, scene_inventory=None):
    plan = report["coverage"].get("planned", [])
    by_id = {x["id"]: x for x in report["checks"]}
    rows = []
    for item in plan:
        r = by_id[item["id"]]
        a = summarize_observations(item, r)
        native_empty = {
            "usdPhysicsValidators:RigidBodyChecker": "rigid_bodies",
            "usdPhysicsValidators:ColliderChecker": "colliders",
            "usdPhysicsValidators:PhysicsJointChecker": "joints",
        }
        validators = item.get("parameters", {}).get("validators", [])
        if (
            scene_inventory is not None
            and len(validators) == 1
            and validators[0] in native_empty
        ):
            kind = native_empty[validators[0]]
            if scene_inventory[kind] == 0 and r["status"] == "PASS":
                a = assessment(
                    kind,
                    [],
                    "Stage validator invoked; inventory contains no matching physics-schema prims.",
                )
        index = report["checks"].index(r)
        obs = r.get("evidence", {}).get("observations", {})
        if not isinstance(obs, dict):
            obs = {}
        finding_counts = Counter(
            x.get("severity", "UNKNOWN")
            for x in obs.get("issues", [])
            if isinstance(x, dict)
        )
        row = dict(
            id=r["id"],
            pack=item["pack"],
            check=item["check"],
            domain=domain_for(item),
            required=r["required"],
            contract_status=r["status"],
            status=r["status"],
            reason=r["reason"],
            evidence_pointer=f"/checks/{index}",
            finding_counts=dict(finding_counts),
            unit=a["unit"] if a else "not reported",
            scope=(
                a["scope"]
                if a
                else "Provider did not expose an assessed-subject denominator."
            ),
            counts={k: v for k, v in a.items() if k.endswith("_count")} if a else None,
        )
        if a:
            if a["candidate_count"] == 0 and r["status"] == "PASS":
                row["status"] = "NO_APPLICABLE_SUBJECTS"
            elif r["status"] == "PASS" and (a["unknown_count"] or a["skipped_count"]):
                row["status"] = "PARTIAL_COVERAGE"
            elif r["status"] == "PASS" and a["warning_count"]:
                row["status"] = "PASS_WITH_WARNINGS"
        elif finding_counts.get("WARNING", 0) or finding_counts.get("Warn", 0):
            if r["status"] == "PASS":
                row["status"] = "PASS_WITH_WARNINGS"
        rows.append(row)
    domains = []
    for name, note in DOMAIN_NOTES.items():
        selected = [r for r in rows if r["domain"] == name]
        if not selected:
            status = "NOT_SELECTED"
        elif all(r["status"] == "NO_APPLICABLE_SUBJECTS" for r in selected):
            status = "NO_APPLICABLE_SUBJECTS"
        elif any(
            r["status"] in ("UNKNOWN", "ERROR", "PARTIAL_COVERAGE") for r in selected
        ):
            status = "INCOMPLETE"
        else:
            status = (
                "CHECKED_WITH_FINDINGS"
                if any(r["status"] in ("FAIL", "PASS_WITH_WARNINGS") for r in selected)
                else "CHECKED_IN_STATED_SCOPE"
            )
        domains.append(
            dict(
                domain=name,
                status=status,
                checks=[r["id"] for r in selected],
                note=note,
            )
        )
    report["coverage"]["inventory"] = scene_inventory
    report["coverage"]["audit"] = {
        "version": "1.0",
        "selected_checks": len(rows),
        "check_outcomes": dict(Counter(r["status"] for r in rows)),
        "required_checks": sum(r["required"] for r in rows),
        "advisory_checks": sum(not r["required"] for r in rows),
        "rows": rows,
        "domains": domains,
        "counting_note": "Object counts apply within one check. Do not sum them across rules: subjects can repeat. Inventory, findings, samples and check outcomes have different units. Missing counts mean unknown, never zero.",
    }
    return report
