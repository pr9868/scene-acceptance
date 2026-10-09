"""Checks return explicit evidence; providers cannot turn exceptions into passes."""

import math
from pxr import UsdGeom, UsdValidation, Tf
from .model import check, MissingEvidence, ContractError, validate, strict_json

UPSTREAM_NAMES = (
    "usdValidation:CompositionErrorTest",
    "usdValidation:StageMetadataChecker",
    "usdGeomValidators:StageMetadataChecker",
)


def upstream(scene):
    registry = UsdValidation.ValidationRegistry()
    issues = []
    executed = []
    for name in UPSTREAM_NAMES:
        validator = registry.GetOrLoadValidatorByName(name)
        if validator is None:
            raise RuntimeError("Required OpenUSD validator unavailable: " + name)
        mark = Tf.Error.Mark()
        mark.SetMark()
        try:
            found = validator.Validate(scene.stage)
            if not mark.IsClean():
                raise RuntimeError(
                    "OpenUSD validator emitted errors: " + str(list(mark.GetErrors()))
                )
        finally:
            mark.Clear()
        executed.append(name)
        for err in found:
            issues.append(
                {
                    "validator": name,
                    "id": str(err.GetIdentifier()),
                    "severity": str(err.GetType()),
                    "message": err.GetMessage(),
                }
            )
    failed = any(
        x["severity"].endswith(".Error") or x["severity"] == "Error" for x in issues
    )
    return check(
        "usd",
        "FAIL" if failed else "PASS",
        "Native OpenUSD checks executed; their scope is format/composition metadata.",
        {"executed": executed, "issues": issues},
    )


def close(a, b, tolerance):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y, tolerance) for x, y in zip(a, b))
    if (
        isinstance(a, (int, float))
        and not isinstance(a, bool)
        and isinstance(b, (int, float))
        and not isinstance(b, bool)
    ):
        return math.isclose(a, b, rel_tol=0, abs_tol=tolerance)
    return a == b


def profile(ctx):
    s = ctx.scene
    return check(
        "profile",
        "UNKNOWN" if s.unsupported else "PASS",
        (
            "Supported declared static geometry profile."
            if not s.unsupported
            else "Some content is outside the supported profile."
        ),
        {
            "unsupported": s.unsupported,
            "cube_count": len(s.cubes),
            "mesh_count": len(s.meshes),
            "declared_profile": s.profile,
            "artifact_set_sha256": s.artifact_set_sha256,
        },
    )


def metadata(ctx):
    stage = ctx.scene.stage
    c = ctx.contract
    observed = {
        "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "authored_meters_per_unit": stage.HasAuthoredMetadata("metersPerUnit"),
        "authored_up_axis": stage.HasAuthoredMetadata("upAxis"),
    }
    valid = (
        observed["authored_meters_per_unit"]
        and observed["authored_up_axis"]
        and observed["meters_per_unit"] == c["stage"]["meters_per_unit"]
        and observed["up_axis"] == c["stage"]["up_axis"]
    )
    return check(
        "metadata",
        "PASS" if valid else "FAIL",
        "Compare authored stage metadata, not reader defaults.",
        {"observed": observed, "expected": c["stage"]},
    )


def require_geometry(scene):
    if scene.mesh_issues:
        raise MissingEvidence("Mesh violations prevent complete geometry readback")
    if scene.unsupported:
        raise MissingEvidence(
            "Complete geometry coverage unavailable: " + "; ".join(scene.unsupported)
        )


def layout(ctx):
    s = ctx.scene
    c = ctx.contract
    spec = c["layout"]
    require_geometry(s)
    tol = c["tolerance_m"]
    prim = s.stage.GetPrimAtPath(spec["root"])
    children = sorted(p.GetName() for p in prim.GetChildren()) if prim else []
    cubes = s.under(spec["root"])
    violations = []
    if children != sorted(spec["required_children"]):
        violations.append("Equipment identity set differs")
    if not cubes:
        violations.append("No geometry under layout root")
    for name, box in cubes.items():
        if any(
            box["min"][i] < spec["cell_min_m"][i] - tol
            or box["max"][i] > spec["cell_max_m"][i] + tol
            for i in range(3)
        ):
            violations.append(name + ": outside cell bounds")
        if box["min"][1] < spec["aisle_min_y_m"] - tol:
            violations.append(name + ": intrudes into aisle")
    return check(
        "layout",
        "FAIL" if violations else "PASS",
        "World-space bounds from cube corners or referenced mesh vertices; no pairwise collision claim.",
        {
            "children": children,
            "violations": violations,
            "bounds": cubes,
            "requirements": spec,
        },
    )


def target(ctx):
    require_geometry(ctx.scene)
    spec = ctx.contract["target"]
    box = ctx.scene.geometry.get(spec["path"])
    if not box:
        return check(
            "target",
            "FAIL",
            "Required target geometry is missing.",
            {"path": spec["path"]},
        )
    valid = close(box["center"], spec["center_m"], ctx.contract["tolerance_m"])
    return check(
        "target",
        "PASS" if valid else "FAIL",
        "Compare saved world-space center with the agreed target.",
        {
            "path": spec["path"],
            "observed_m": box["center"],
            "expected_m": spec["center_m"],
            "tolerance_m": ctx.contract["tolerance_m"],
        },
    )


def preserved(ctx):
    if ctx.baseline is None:
        raise MissingEvidence("Protected-state check requires the baseline")
    require_geometry(ctx.scene)
    require_geometry(ctx.baseline)
    c = ctx.contract
    spec = c["protected"]
    a = ctx.baseline.under(spec["root"])
    b = ctx.scene.under(spec["root"])
    differences = []
    for excluded in spec.get("exclude_paths", []):
        a = {
            p: v
            for p, v in a.items()
            if p != excluded and not p.startswith(excluded + "/")
        }
        b = {
            p: v
            for p, v in b.items()
            if p != excluded and not p.startswith(excluded + "/")
        }
    if not a:
        raise MissingEvidence("Baseline has no geometry under protected root")
    if a.keys() != b.keys():
        differences.append("Protected geometry identity set changed")
    for path in a.keys() & b.keys():
        for prop in spec["properties"]:
            keys = ["min", "max"] if prop == "world_bounds" else ["display_color"]
            if any(
                not close(
                    a[path][k],
                    b[path][k],
                    c["tolerance_m"] if prop == "world_bounds" else 0,
                )
                for k in keys
            ):
                differences.append(path + ": " + prop + " changed")
    return check(
        "preserved",
        "FAIL" if differences else "PASS",
        "Only the declared protected properties are compared.",
        {
            "properties": spec["properties"],
            "root": spec["root"],
            "excluded": spec.get("exclude_paths", []),
            "differences": differences,
        },
    )


def claims(ctx):
    if ctx.claims is None:
        raise MissingEvidence("Claims input not supplied")
    validate(ctx.claims, "claims")
    ids = [x["id"] for x in ctx.claims["claims"]]
    if len(ids) != len(set(ids)):
        raise ContractError("Claim IDs must be unique")
    if ctx.claims["artifact_set_sha256"] != ctx.scene.artifact_set_sha256:
        return check(
            "claims",
            "FAIL",
            "Claims refer to another candidate/dependency revision.",
            {"expected_artifact_set_sha256": ctx.scene.artifact_set_sha256},
        )
    observations = []
    by_id = {x["id"]: x for x in ctx.claims["claims"]}
    for required in ctx.contract.get("required_claims", []):
        submitted = by_id.get(required["id"])
        if submitted is None:
            observations.append(
                {
                    "id": required["id"],
                    "status": "UNKNOWN",
                    "reason": "Required claim absent from the submission.",
                    "required_claim": required,
                }
            )
        elif any(submitted.get(k) != v for k, v in required.items()):
            observations.append(
                {
                    "id": required["id"],
                    "status": "FAIL",
                    "reason": "Submitted claim changes the required property, object, unit or basis.",
                    "required_claim": required,
                }
            )
    for item in ctx.claims["claims"]:
        row = {
            "id": item["id"],
            "claim": item,
            "status": "UNKNOWN",
            "reason": "Property credibility is outside v0.",
        }
        metric = item["metric"]
        value = item["value"]
        basis = item["basis"]
        expected_unit = (
            "m"
            if metric in ["min_y", "center_y", "dimensions"]
            else "kg" if metric == "mass" else "1"
        )
        expected_type = (
            isinstance(value, list)
            if metric == "dimensions"
            else (
                isinstance(value, bool)
                if metric == "contact_support"
                else isinstance(value, (int, float)) and not isinstance(value, bool)
            )
        )
        if item["unit"] != expected_unit or not expected_type:
            raise ContractError(
                "Claim metric, value and unit are inconsistent: " + item["id"]
            )
        if basis == "measured":
            source = item.get("source")
            if source and source in ctx.contract["evidence_sources"]:
                data = strict_json(ctx.bundle.record(source, missing=True))
                if not isinstance(data, dict):
                    raise ContractError("Evidence source must be a JSON object")
                if data.get("basis") == "assumed":
                    row.update(
                        status="FAIL",
                        reason="Claim says measured; cited source explicitly says assumed.",
                    )
                else:
                    row["reason"] = (
                        "Source supplied, but its measurement truth is not validated by v0."
                    )
            else:
                row["reason"] = "Measured claim has no declared measurement source."
        elif basis == "assumed":
            row["reason"] = (
                "Declared assumption retained; this is not a verified physical property."
            )
        elif metric in ["min_y", "center_y", "dimensions"]:
            require_geometry(ctx.scene)
            box = ctx.scene.geometry.get(item["path"])
            if box is None:
                row.update(
                    status="FAIL",
                    reason="Claim refers to geometry absent from the complete supported inventory.",
                )
            else:
                actual = (
                    box["min"][1]
                    if metric == "min_y"
                    else box["center"][1] if metric == "center_y" else box["dimensions"]
                )
                row.update(
                    status=(
                        "PASS"
                        if close(value, actual, ctx.contract["tolerance_m"])
                        else "FAIL"
                    ),
                    observed=actual,
                    reason="Compared with saved geometry, not a plant measurement.",
                )
        observations.append(row)
    statuses = {x["status"] for x in observations}
    status = (
        "FAIL" if "FAIL" in statuses else "UNKNOWN" if "UNKNOWN" in statuses else "PASS"
    )
    return check(
        "claims",
        status,
        "Typed claims only; free-form reports remain unchecked.",
        {"claims": observations},
    )


def freshness(ctx):
    if ctx.receipt is None:
        raise MissingEvidence("No prior receipt supplied for comparison")
    receipt = ctx.receipt
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema_version") != "1.0"
        or not isinstance(receipt.get("identity"), dict)
    ):
        raise ContractError("Receipt is not a result record")
    # A receipt establishes identity continuity only; every current check still reruns.
    same = receipt["identity"] == ctx.identity
    return check(
        "freshness",
        "PASS" if same else "FAIL",
        (
            "Receipt identity matches current inputs and checker."
            if same
            else "Receipt is stale for these inputs, dependencies or checker."
        ),
        {"receipt_identity": receipt["identity"], "current_identity": ctx.identity},
    )


def report_grounding(ctx):
    return check(
        "report_grounding",
        "UNKNOWN",
        "Free-form prose/report grounding has no provider in v0.",
    )


def mesh(ctx):
    s = ctx.scene
    if s.profile != "usd-static-geometry-v1":
        raise MissingEvidence("Mesh checks require the static geometry profile")
    violations = dict(s.mesh_issues)
    for path in ctx.contract.get("mesh_rules", {}).get("require_closed_edges", []):
        if path not in s.meshes:
            if not s.unsupported and path not in s.mesh_issues:
                violations[path] = ["Required mesh for edge closure is missing"]
        elif not s.mesh_stats[path]["closed_consistent_edges"]:
            violations[path] = [
                "Mesh does not have two oppositely directed uses per edge"
            ]
    return check(
        "mesh",
        "FAIL" if violations else "UNKNOWN" if s.unsupported else "PASS",
        "Native topology, finite points, face validity and declared edge requirements; not collision or watertightness.",
        {
            "violations": violations,
            "meshes": s.mesh_stats,
            "unsupported": s.unsupported,
            "closure_required_paths": ctx.contract.get("mesh_rules", {}).get(
                "require_closed_edges", []
            ),
        },
    )


def _corner_match(a, b, tolerance):
    # Eight cube corners: bipartite matching avoids ambiguous nearest-neighbor ties.
    matched = {}

    def assign(i, seen):
        for j in range(len(b)):
            if j in seen or not close(a[i], b[j], tolerance):
                continue
            seen.add(j)
            if j not in matched or assign(matched[j], seen):
                matched[j] = i
                return True
        return False

    return len(a) == len(b) and all(assign(i, set()) for i in range(len(a)))


def shape(ctx):
    if ctx.baseline is None:
        raise MissingEvidence("Translation-only shape check requires a saved baseline")
    require_geometry(ctx.scene)
    require_geometry(ctx.baseline)
    observations = []
    for path in ctx.contract["shape"]["paths"]:
        a = ctx.baseline.shapes.get(path)
        b = ctx.scene.shapes.get(path)
        if a is None:
            observations.append(
                {"path": path, "status": "UNKNOWN", "reason": "Baseline shape absent"}
            )
            continue
        if b is None:
            observations.append(
                {
                    "path": path,
                    "status": "FAIL",
                    "reason": "Required candidate shape absent",
                }
            )
            continue
        ca = ctx.baseline.geometry[path]["center"]
        cb = ctx.scene.geometry[path]["center"]
        pa = [[x - c for x, c in zip(p, ca)] for p in a["points"]]
        pb = [[x - c for x, c in zip(p, cb)] for p in b["points"]]
        tol = ctx.contract["tolerance_m"]
        topology_same = a["kind"] == b["kind"] and all(
            a.get(k) == b.get(k) for k in ["face_counts", "face_indices"]
        )
        same = topology_same and (
            _corner_match(pa, pb, tol) if a["kind"] == "Cube" else close(pa, pb, tol)
        )
        observations.append(
            {
                "path": path,
                "status": "PASS" if same else "FAIL",
                "reason": "Centered cube-corner set or indexed mesh points and connectivity compared; equivalent reindexing/remeshing is not supported",
                "baseline_kind": a["kind"],
                "candidate_kind": b["kind"],
                "same_connectivity_and_representation": topology_same,
                "baseline_point_count": len(pa),
                "candidate_point_count": len(pb),
                "baseline_bounds_m": {
                    k: ctx.baseline.geometry[path][k] for k in ["min", "max"]
                },
                "candidate_bounds_m": {
                    k: ctx.scene.geometry[path][k] for k in ["min", "max"]
                },
            }
        )
    statuses = {o["status"] for o in observations}
    return check(
        "shape",
        (
            "FAIL"
            if "FAIL" in statuses
            else "UNKNOWN" if "UNKNOWN" in statuses else "PASS"
        ),
        "Only world translation is allowed on the consumer-declared shapes.",
        {
            "mode": "translation_only",
            "tolerance_m": ctx.contract["tolerance_m"],
            "observations": observations,
        },
    )


REGISTRY = {
    "usd": lambda c: upstream(c.scene),
    "profile": profile,
    "metadata": metadata,
    "layout": layout,
    "target": target,
    "mesh": mesh,
    "shape": shape,
    "preserved": preserved,
    "claims": claims,
    "freshness": freshness,
    "report_grounding": report_grounding,
}
