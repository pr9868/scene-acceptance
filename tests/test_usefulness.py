"""Regression controls from the adopter review; no model-quality claims."""

import pytest
from pxr import UsdGeom, UsdShade, Sdf
from scene_acceptance.clearance import zone
from scene_acceptance.builtin_packs import materials
from scene_acceptance.observations import summarize
from test_extensions_geometry import scene, context

ZONE = dict(
    zone_min_m=[-1, -1, -1],
    zone_max_m=[1, 1, 1],
    time_s=0,
    numeric_margin_m=1e-8,
    max_triangle_pairs=10000,
)


@pytest.mark.parametrize("reverse", [False, True])
def test_known_collision_survives_unsupported_subject(tmp_path, reverse):
    s = scene(tmp_path)
    UsdGeom.Cube.Define(s, "/World/Hit")
    UsdGeom.Cone.Define(s, "/World/Unknown")
    paths = ["/World/Hit", "/World/Unknown"]
    r = zone(
        context(s, tmp_path), dict(ZONE, obstacles=paths[::-1] if reverse else paths)
    )
    assert r.status == "FAIL"
    assert {x["path"]: x["status"] for x in r.evidence["findings"]} == dict(
        zip(paths, ["FAIL", "UNKNOWN"])
    )


def material(stage, name, asset=None):
    m = UsdShade.Material.Define(stage, "/World/Looks/" + name)
    shader = UsdShade.Shader.Define(stage, str(m.GetPath()) + "/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    m.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    if asset:
        shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(asset))
    return m


def test_missing_sign_texture_does_not_fail_unrelated_belt(tmp_path):
    s = scene(tmp_path)
    for name, asset in [("Belt", None), ("Sign", "missing.png")]:
        p = UsdGeom.Cube.Define(s, "/World/" + name)
        UsdShade.MaterialBindingAPI.Apply(p.GetPrim()).Bind(material(s, name, asset))
    ctx = context(s, tmp_path)

    def run(name):
        return materials(
            ctx,
            dict(
                bindings={"/World/" + name: "/World/Looks/" + name},
                purpose="allPurpose",
                render_context="",
                surface_shader_id="UsdPreviewSurface",
            ),
        )

    assert run("Belt").status == "PASS"
    sign = run("Sign")
    assert sign.status == "FAIL"
    assert any(
        x.get("object") == "missing.png" and x["status"] == "FAIL"
        for x in sign.evidence["findings"]
    )


def test_shared_missing_file_keeps_both_material_owners(tmp_path):
    s = scene(tmp_path)
    bindings = {}
    for name in ("SignA", "SignB"):
        p = UsdGeom.Cube.Define(s, "/World/" + name)
        m = material(s, name, "shared-missing.png")
        UsdShade.MaterialBindingAPI.Apply(p.GetPrim()).Bind(m)
        bindings[str(p.GetPath())] = str(m.GetPath())
    r = materials(
        context(s, tmp_path),
        dict(
            bindings=bindings,
            purpose="allPurpose",
            render_context="",
            surface_shader_id="UsdPreviewSurface",
        ),
    )
    missing = [
        x
        for x in r.evidence["findings"]
        if x.get("property") == "external_asset_exists"
    ]
    assert r.status == "FAIL"
    assert len(missing) == 1
    assert missing[0]["materials"] == ["/World/Looks/SignA", "/World/Looks/SignB"]


def test_invalid_cylinder_axis_is_unresolved(tmp_path):
    s = scene(tmp_path)
    shape = UsdGeom.Cylinder.Define(s, "/World/UnknownAxis")
    shape.CreateAxisAttr("unexpected")
    r = zone(context(s, tmp_path), dict(ZONE, obstacles=[str(shape.GetPath())]))
    assert r.status == "UNKNOWN"
    assert "Invalid cylinder axis" in r.evidence["findings"][0]["reason"]


def test_report_keeps_failed_observations_and_reports_omissions():
    rows = [dict(status="PASS", expected=1, observed=1) for _ in range(100)]
    rows.append(dict(status="FAIL", expected="bidirectional", observed="bidir"))
    r = summarize(dict(findings=rows))
    assert r["findings"][0]["observed"] == "bidir"
    assert r["observation_count"] == 101 and r["omitted_observation_count"] == 37


def test_surface_policy_does_not_require_sealing_a_sign(tmp_path):
    s = scene(tmp_path)
    m = UsdGeom.Mesh.Define(s, "/World/Sign")
    m.CreatePointsAttr([(-0.5, 0, -0.5), (0.5, 0, -0.5), (0.5, 0, 0.5), (-0.5, 0, 0.5)])
    m.CreateFaceVertexCountsAttr([4])
    m.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    m.CreateSubdivisionSchemeAttr("none")
    ctx = context(s, tmp_path)
    before = ctx.artifact.memory_digest()
    assert zone(ctx, dict(ZONE, obstacles=["/World/Sign"])).status == "UNKNOWN"
    r = zone(ctx, dict(ZONE, obstacles=["/World/Sign"], representation="surfaces"))
    assert r.status == "FAIL"
    assert ctx.artifact.memory_digest() == before and ctx.artifact.unchanged()


@pytest.mark.parametrize("policy,status", [("allow", "PASS"), ("forbid", "FAIL")])
def test_flush_contact_obeys_explicit_policy(tmp_path, policy, status):
    s = scene(tmp_path)
    p = UsdGeom.Cube.Define(s, "/World/Part")
    p.CreateSizeAttr(2)
    p.AddTranslateOp().Set((2, 0, 0))
    r = zone(
        context(s, tmp_path),
        dict(ZONE, obstacles=["/World/Part"], contact_policy=policy),
    )
    assert r.status == status, r


def test_broad_selection_includes_new_unlisted_obstacle(tmp_path):
    s = scene(tmp_path)
    UsdGeom.Cube.Define(s, "/World/NewPart")
    r = zone(context(s, tmp_path), dict(ZONE, selector={"root": "/World"}))
    assert r.status == "FAIL" and r.evidence["selection"]["paths"] == ["/World/NewPart"]


@pytest.mark.parametrize("kind", [UsdGeom.Cylinder, UsdGeom.Sphere])
def test_implicit_shape_collision_and_analytic_bounds(tmp_path, kind):
    from scene_acceptance.brief_measurements import bounds

    s = scene(tmp_path)
    shape = kind.Define(s, "/World/Part")
    shape.CreateRadiusAttr(0.2)
    if kind == UsdGeom.Cylinder:
        shape.CreateHeightAttr(0.5)
    ctx = context(s, tmp_path)
    assert zone(ctx, dict(ZONE, obstacles=["/World/Part"])).status == "FAIL"
    assert (
        bounds(
            ctx,
            dict(
                path="/World/Part",
                time_code=0,
                size_m=[0.4, 0.4, None],
                tolerance_m=1e-6,
            ),
        ).status
        == "PASS"
    )


def test_concave_polygon_preserves_missing_corner():
    from scene_acceptance.geometry_access import triangulate

    points = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (1, 1, 0), (1, 2, 0), (0, 2, 0)]
    triangles = triangulate(points, list(range(6)))

    def area(t):
        a, b, c = [points[i] for i in t]
        return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2

    assert len(triangles) == 4 and sum(map(area, triangles)) == 3


def test_preflight_and_capture_budget(tmp_path):
    from scene_acceptance.preflight import checks, capture_budget

    s = scene(tmp_path)
    UsdGeom.Xform.Define(s, "/World/Assembly")
    ctx = context(s, tmp_path)
    r = checks(
        ctx.artifact,
        [
            dict(
                id="zone",
                pack="geometry.clearance",
                check="clear_zone",
                parameters=dict(ZONE, obstacles=["/World/Assembly"]),
            )
        ],
    )
    assert (
        r["status"] == "unresolved"
        and r["checks"][0]["gaps"][0]["subject"] == "/World/Assembly"
    )
    captures = [
        dict(id=str(i), times_seconds=[0], feasibility_gaps=[]) for i in range(11)
    ]
    report = capture_budget(captures, 8)
    assert report["additional_slots_needed"] == 3 and all(
        c["feasibility_gaps"] for c in captures
    )


def test_relative_motion_does_not_need_rest_position(tmp_path):
    from scene_acceptance.requirement_values import relative_motion

    s = scene(tmp_path)
    x = UsdGeom.Xform.Define(s, "/World/Part")
    op = x.AddTranslateOp()
    op.Set((50, 20, 8), 0)
    op.Set((50, 20, 8.04), 10)
    r = relative_motion(
        context(s, tmp_path),
        dict(
            path="/World/Part",
            start_s=0,
            end_s=10,
            delta_m=[None, None, 0.04],
            tolerance_m=1e-5,
        ),
    )
    assert r.status == "PASS"


def test_subject_capacity_keeps_known_failure(tmp_path):
    s = scene(tmp_path)
    for i in range(3):
        UsdGeom.Cube.Define(s, f"/World/Part{i}")
    r = zone(
        context(s, tmp_path), dict(ZONE, selector={"root": "/World", "max_subjects": 1})
    )
    assert r.status == "FAIL"
    assert any(x["cause"] == "capacity_limit" for x in r.evidence["findings"])
    assert r.evidence["selection"]["capacity_exhausted"]


def test_collection_and_exclusion_selection(tmp_path):
    from pxr import Usd
    from scene_acceptance.subjects import resolve

    s = scene(tmp_path)
    for name in ("A", "B"):
        UsdGeom.Cube.Define(s, "/World/" + name)
    c = Usd.CollectionAPI.Apply(s.GetDefaultPrim(), "obstacles")
    c.CreateIncludesRel().SetTargets(["/World/A", "/World/B"])
    found = resolve(
        s, dict(collection="/World.collection:obstacles", exclude=["/World/B"])
    )
    assert found["paths"] == ["/World/A"] and found["excluded"] == ["/World/B"]


def test_nonplanar_polygon_is_unresolved(tmp_path):
    from scene_acceptance.geometry_access import triangulate
    from scene_acceptance.model import MissingEvidence

    with pytest.raises(MissingEvidence):
        triangulate([(0, 0, 0), (1, 0, 0), (1, 1, 0.01), (0, 1, 0)], [0, 1, 2, 3])


def test_sliding_and_engagement_controls(tmp_path):
    from scene_acceptance.mechanical import sliding, engagement

    s = scene(tmp_path)
    for n, x in [("A", 0), ("B", 1.815)]:
        cube = UsdGeom.Cube.Define(s, "/World/" + n)
        cube.CreateSizeAttr(1)
        op = cube.AddTranslateOp()
        op.Set((x, 0, 0), 0)
        op.Set((x + 0.1, 0, 0), 10)
    ctx = context(s, tmp_path)
    params = dict(
        a={"path": "/World/A", "local_point": [0, 0, 0]},
        b={"path": "/World/B", "local_point": [0, 0, 0]},
        axis_world=[1, 0, 0],
        interval_s=[0, 10],
        numeric_margin_m=1e-8,
        max_lateral_m=0.01,
        minimum_travel_m=1,
        maximum_travel_m=2,
    )
    assert sliding(ctx, params).status == "PASS"
    params["axis_world"] = [0, 1, 0]
    assert sliding(ctx, params).status == "FAIL"
    q = dict(
        a="/World/A",
        b="/World/B",
        axis_world=[1, 0, 0],
        interval_s=[0, 10],
        numeric_margin_m=1e-8,
        minimum_overlap_m=0.01,
    )
    r = engagement(ctx, q)
    assert r.status == "FAIL" and r.evidence["findings"][0][
        "overlap_m"
    ] == pytest.approx(-0.815)


def test_rotation_rate_preserves_full_turns(tmp_path):
    from scene_acceptance.requirement_values import rotation_rate

    s = scene(tmp_path)
    p = UsdGeom.Xform.Define(s, "/World/Rotor")
    op = p.AddRotateZOp()
    op.Set(0, 0)
    op.Set(3600, 10)
    ctx = context(s, tmp_path)
    q = dict(
        attribute="/World/Rotor.xformOp:rotateZ",
        interval_s=[0, 10],
        expected_rpm=60,
        tolerance_rpm=0.01,
    )
    assert rotation_rate(ctx, q).status == "PASS"
    q["expected_rpm"] = 45
    assert rotation_rate(ctx, q).status == "FAIL"


def test_prim_capacity_is_unknown_and_caller_can_raise_it(tmp_path):
    from scene_acceptance.profiles import evaluate_baseline

    s = scene(tmp_path)
    for i in range(10):
        UsdGeom.Cube.Define(s, f"/World/P{i}")
    s.GetRootLayer().Save()
    r = evaluate_baseline(tmp_path, "scene.usda", max_prims=5)
    assert r["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert r["checks"][0]["evidence"]["observed_at_least"] == 6
    r = evaluate_baseline(tmp_path, "scene.usda", max_prims=20)
    assert not any(c["id"] == "core.discovery" for c in r["checks"])


def test_model_protocol_supplies_schema_and_declares_omissions():
    from scene_acceptance.model_protocol import prepare_request

    request = dict(
        scene=dict(prim_paths=[str(i) for i in range(100)], inventory={}),
        requirements=[{"id": "must-retain"}],
    )
    old = prepare_request(request, "interpreter", {"type": "object"}, 16)
    assert (
        len(old["scene"]["prim_paths"]) == 100
        and len(request["scene"]["prim_paths"]) == 16
    )
    assert request["model_protocol"]["context_omissions"][0]["omitted_items"] == 84
    assert request["requirements"] == [{"id": "must-retain"}]
    assert request["model_protocol"]["response_schema"] == {"type": "object"}


def test_contact_allowance_is_explicit_and_does_not_hide_deeper_intrusion(tmp_path):
    s = scene(tmp_path)
    cube = UsdGeom.Cube.Define(s, "/World/Part")
    cube.CreateSizeAttr(2)
    op = cube.AddTranslateOp()
    op.Set((1.9999999, 0, 0))
    ctx = context(s, tmp_path)
    args = dict(
        ZONE, obstacles=["/World/Part"], contact_policy="allow", numeric_margin_m=0.0005
    )
    assert zone(ctx, args).status == "UNKNOWN"
    assert zone(ctx, dict(args, contact_tolerance_m=0.001)).status == "PASS"
    s = ctx.artifact.stage
    UsdGeom.Xformable(s.GetPrimAtPath("/World/Part")).GetOrderedXformOps()[0].Set(
        (1.99, 0, 0)
    )
    assert zone(ctx, dict(args, contact_tolerance_m=0.001)).status == "FAIL"


def test_missing_relative_motion_subject_cannot_pass(tmp_path):
    from scene_acceptance.requirement_values import relative_motion
    from scene_acceptance.model import MissingEvidence

    ctx = context(scene(tmp_path), tmp_path)
    with pytest.raises(MissingEvidence):
        relative_motion(
            ctx,
            dict(
                path="/World/Absent",
                start_s=0,
                end_s=1,
                delta_m=[0, 0, 0],
                tolerance_m=0.1,
            ),
        )


@pytest.mark.parametrize("kind", [UsdGeom.Sphere, UsdGeom.Cylinder])
@pytest.mark.parametrize("scale", [(1, 1, 1), (-2, 0.5, 3)])
def test_implicit_distance_bound_contains_analytic_plane_gap(tmp_path, kind, scale):
    from scene_acceptance.geometry_access import read_geometry
    from scene_acceptance.clearance import point_triangle
    from pxr import Gf

    s = scene(tmp_path)
    shape = kind.Define(s, "/World/Part")
    shape.CreateRadiusAttr(0.2)
    if kind == UsdGeom.Cylinder:
        shape.CreateHeightAttr(0.5)
    shape.AddScaleOp().Set(scale)
    shape.AddTranslateOp().Set((0, 0, 0))
    context(s, tmp_path)
    geometry = read_geometry(s, "/World/Part", 0, False, approximation_m=0.002)
    # All shape points remain on the negative side of x=2. The exact support
    # value is |x scale| * radius, independently of the tessellation.
    measured = 2 - max(p[0] for t in geometry.triangles for p in t)
    exact = 2 - abs(scale[0]) * 0.2
    assert abs(measured - exact) <= geometry.error_m + 1e-12
    assert geometry.error_m <= 0.002


def test_transform_does_not_change_local_attachment_requirement(tmp_path):
    from scene_acceptance.continuous_motion import connection

    s = scene(tmp_path)
    parent = UsdGeom.Xform.Define(s, "/World/Assembly")
    parent.AddRotateZOp().Set(65)
    parent.AddScaleOp().Set((2, 0.5, 3))
    for name in ["A", "B"]:
        child = UsdGeom.Xform.Define(s, "/World/Assembly/" + name)
        op = child.AddTranslateOp()
        op.Set((1, 2, 3), 0)
        op.Set((2, 2, 3), 10)
    q = dict(
        a=dict(path="/World/Assembly/A", local_point=[0, 0, 0]),
        b=dict(path="/World/Assembly/B", local_point=[0, 0, 0]),
        interval_s=[0, 10],
        max_gap_m=0.001,
        numeric_margin_m=1e-8,
    )
    assert connection(context(s, tmp_path), q).status == "PASS"


def test_open_surface_crossing_and_closed_containment_differ(tmp_path):
    s = scene(tmp_path)
    cube = UsdGeom.Cube.Define(s, "/World/Container")
    cube.CreateSizeAttr(4)
    ctx = context(s, tmp_path)
    q = dict(ZONE, obstacles=["/World/Container"])
    assert zone(ctx, q).status == "FAIL"
    assert zone(ctx, dict(q, representation="surfaces")).status == "PASS"


def test_model_projection_deduplicates_views_without_losing_targets():
    from scene_acceptance.model_protocol import prepare_request

    targets = [f"/World/P{i}" for i in range(100)]
    r = dict(
        evidence=[
            dict(id=str(i), role="scene_view", covered_prims=list(targets))
            for i in range(4)
        ]
    )
    prepare_request(r, "judge", {"type": "object"}, 16)
    assert len(r["declared_subject_sets"]) == 1
    for v in r["evidence"]:
        assert r["declared_subject_sets"][v["covered_prims_ref"]] == targets


def test_model_semantic_identity_survives_file_relocation_but_not_content_change():
    from scene_acceptance.model_protocol import prepare_request

    def identity(path, digest, role="judge"):
        r = {"evidence": [{"id": "image", "path": path}], "subject": "/World/Part"}
        prepare_request(r, role, {"type": "object"}, input_hashes={path: digest})
        return r["model_protocol"]["semantic_input_sha256"]

    assert identity("/a/view.png", "1" * 64) == identity("/b/view.png", "1" * 64)
    assert identity("/a/view.png", "1" * 64) != identity("/a/view.png", "2" * 64)
    assert identity("/a/view.png", "1" * 64) != identity(
        "/a/view.png", "1" * 64, "audit"
    )


def test_mechanical_coverage_counts_relationships_not_knots():
    from scene_acceptance.coverage import summarize_observations

    record = {
        "status": "FAIL",
        "evidence": {
            "observations": {
                "knots": [{}, {}, {}],
                "interval_s": [0, 10],
                "coverage": "Declared pair only",
            }
        },
    }
    a = summarize_observations(
        {"pack": "mechanical.relationships", "check": "attachment"}, record
    )
    assert a["unit"] == "declared relationships" and a["candidate_count"] == 1
    assert a["fail_count"] == 1 and a["knot_count"] == 3


def test_material_network_gap_does_not_hide_known_missing_file(tmp_path):
    s = scene(tmp_path)
    cube = UsdGeom.Cube.Define(s, "/World/Sign")
    m = material(s, "Sign", "missing.png")
    UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(m)
    shader = s.GetPrimAtPath("/World/Looks/Sign/Shader")
    a = shader.CreateAttribute("inputs:broken", Sdf.ValueTypeNames.Color3f)
    a.SetConnections(["/World/Absent.outputs:color"])
    ctx = context(s, tmp_path)
    r = materials(
        ctx,
        dict(
            bindings={"/World/Sign": "/World/Looks/Sign"},
            purpose="allPurpose",
            render_context="",
            surface_shader_id="UsdPreviewSurface",
        ),
    )
    assert r.status == "FAIL"
    assert any(x["status"] == "UNKNOWN" for x in r.evidence["findings"])
    assert any(
        x.get("object") == "missing.png" and x["status"] == "FAIL"
        for x in r.evidence["findings"]
    )


def test_unused_angle_attribute_is_not_a_rotation_rate(tmp_path):
    from scene_acceptance.requirement_values import rotation_rate
    from scene_acceptance.model import MissingEvidence

    s = scene(tmp_path)
    p = UsdGeom.Xform.Define(s, "/World/Rotor")
    p.GetPrim().CreateAttribute("xformOp:rotateZ", Sdf.ValueTypeNames.Double).Set(0)
    with pytest.raises(MissingEvidence):
        rotation_rate(
            context(s, tmp_path),
            dict(
                attribute="/World/Rotor.xformOp:rotateZ",
                interval_s=[0, 10],
                expected_rpm=0,
                tolerance_rpm=0,
            ),
        )
