"""Independent analytic controls for composed geometry and continuous motion."""

from types import SimpleNamespace
import math

import pytest
from pxr import Usd, UsdGeom, Sdf

from scene_acceptance.profiles import discover_artifact
from scene_acceptance.model import BoundaryError, MissingEvidence
from scene_acceptance.usd_composition import prims
from scene_acceptance.continuous_motion import connection
from scene_acceptance.clearance import static, sweep, zone
from scene_acceptance.layer_policy import metadata, dependencies


def scene(tmp_path):
    stage = Usd.Stage.CreateNew(str(tmp_path / "scene.usda"))
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(stage, "Z")
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(10)
    stage.SetTimeCodesPerSecond(1)
    return stage


def context(stage, tmp_path):
    stage.GetRootLayer().Save()
    artifact = discover_artifact(tmp_path, "scene.usda")
    return SimpleNamespace(artifact=artifact, bundle=artifact.bundle, sources=[])


@pytest.mark.parametrize(
    "kind", ["variant", "payload", "instance", "inherit", "specialize"]
)
def test_composed_geometry_is_visible(tmp_path, kind):
    stage = scene(tmp_path)
    if kind == "payload":
        child = Usd.Stage.CreateNew(str(tmp_path / "child.usda"))
        p = UsdGeom.Xform.Define(child, "/Assembly")
        child.SetDefaultPrim(p.GetPrim())
        UsdGeom.Cube.Define(child, "/Assembly/Part")
        child.GetRootLayer().Save()
        stage.GetPrimAtPath("/World").GetPayloads().AddPayload("child.usda")
        expected = "/World/Part"
    elif kind == "variant":
        variants = (
            stage.GetPrimAtPath("/World").GetVariantSets().AddVariantSet("design")
        )
        variants.AddVariant("A")
        variants.SetVariantSelection("A")
        with variants.GetVariantEditContext():
            UsdGeom.Cube.Define(stage, "/World/Part")
        expected = "/World/Part"
    else:
        cls = stage.DefinePrim("/Source", "Xform")
        UsdGeom.Cube.Define(stage, "/Source/Part")
        target = stage.DefinePrim("/World/Copy", "Xform")
        if kind == "instance":
            target.GetReferences().AddInternalReference("/Source")
            target.SetInstanceable(True)
        elif kind == "inherit":
            target.GetInherits().AddInherit("/Source")
        else:
            target.GetSpecializes().AddSpecialize("/Source")
        expected = "/World/Copy/Part"
    ctx = context(stage, tmp_path)
    assert expected in {str(p.GetPath()) for p in prims(ctx.artifact.stage)}
    assert dependencies(ctx, {}).status == "PASS"


def test_unselected_variant_cannot_hide_escape(tmp_path):
    stage = scene(tmp_path)
    v = stage.GetPrimAtPath("/World").GetVariantSets().AddVariantSet("design")
    for name in ("good", "bad"):
        v.AddVariant(name)
    v.SetVariantSelection("bad")
    with v.GetVariantEditContext():
        stage.GetPrimAtPath("/World").CreateAttribute(
            "asset", Sdf.ValueTypeNames.Asset
        ).Set(Sdf.AssetPath("../escape.png"))
    v.SetVariantSelection("good")
    with pytest.raises(BoundaryError):
        context(stage, tmp_path)


def test_udim_tiles_have_identity_and_expansion_budget(tmp_path):
    from PIL import Image

    stage = scene(tmp_path)
    stage.GetPrimAtPath("/World").CreateAttribute(
        "texture", Sdf.ValueTypeNames.Asset
    ).Set(Sdf.AssetPath("albedo.<UDIM>.png"))
    for tile in (1001, 1002):
        Image.new("RGB", (1, 1)).save(tmp_path / f"albedo.{tile}.png")
    ctx = context(stage, tmp_path)
    assert set(ctx.artifact.identity["files"]) == {
        "scene.usda",
        "albedo.1001.png",
        "albedo.1002.png",
    }
    assert dependencies(ctx, {}).status == "PASS"
    Image.new("RGB", (1, 1)).save(tmp_path / "albedo.1003.png")
    assert not ctx.artifact.unchanged()


def test_layer_policy_finds_unconverted_reference(tmp_path):
    stage = scene(tmp_path)
    child = Usd.Stage.CreateNew(str(tmp_path / "child.usda"))
    child.DefinePrim("/Part", "Cube")
    child.SetDefaultPrim(child.GetPrimAtPath("/Part"))
    UsdGeom.SetStageMetersPerUnit(child, 0.001)
    UsdGeom.SetStageUpAxis(child, "Y")
    child.GetRootLayer().Save()
    stage.GetPrimAtPath("/World").GetReferences().AddReference("child.usda")
    row = metadata(
        context(stage, tmp_path),
        dict(meters_per_unit=1, up_axis="Z", require_authored_on_every_layer=True),
    )
    assert row.status == "FAIL"
    assert len([r for r in row.evidence["findings"] if r["status"] == "FAIL"]) == 2


def cubes(stage, distance=3):
    a = UsdGeom.Cube.Define(stage, "/World/A")
    a.CreateSizeAttr(1)
    b = UsdGeom.Cube.Define(stage, "/World/B")
    b.CreateSizeAttr(1)
    return a, b, b.AddTranslateOp().Set((distance, 0, 0))


PARAMS = dict(
    a="/World/A",
    b="/World/B",
    representation="closed-solids",
    minimum_m=1.0,
    numeric_margin_m=1e-8,
    max_triangle_pairs=1000,
    time_s=0.0,
)


@pytest.mark.parametrize("offset,expected", [(3, "PASS"), (1.5, "FAIL"), (0, "FAIL")])
def test_clearance_analytic_cubes(tmp_path, offset, expected):
    stage = scene(tmp_path)
    cubes(stage, offset)
    result = static(context(stage, tmp_path), PARAMS)
    assert result.status == expected
    assert result.evidence["distance_m"] == pytest.approx(max(0, offset - 1))


def test_containment_is_not_positive_clearance(tmp_path):
    stage = scene(tmp_path)
    a, b, _ = cubes(stage, 0)
    a.CreateSizeAttr(4)
    assert static(context(stage, tmp_path), PARAMS).evidence["distance_m"] == 0


def test_distance_uses_triangles_not_overlapping_boxes(tmp_path):
    stage = scene(tmp_path)
    for path, points in [
        ("/World/A", [(0, 0, 0), (1, 0, 0), (0, 1, 0)]),
        ("/World/B", [(1, 1, 0), (0.6, 1, 0), (1, 0.6, 0)]),
    ]:
        mesh = UsdGeom.Mesh.Define(stage, path)
        mesh.CreatePointsAttr(points)
        mesh.CreateFaceVertexCountsAttr([3])
        mesh.CreateFaceVertexIndicesAttr([0, 1, 2])
        mesh.CreateSubdivisionSchemeAttr("none")
    ctx = context(stage, tmp_path)
    result = static(ctx, dict(PARAMS, representation="surfaces", minimum_m=0.4))
    assert result.status == "PASS"
    assert result.evidence["distance_m"] == pytest.approx(0.6 / math.sqrt(2), abs=1e-6)
    with pytest.raises(MissingEvidence, match="two-manifold"):
        static(ctx, PARAMS)


def test_swept_clearance_catches_between_poses_and_refuses_budget_pass(tmp_path):
    stage = scene(tmp_path)
    a, b, _ = cubes(stage, 3)
    op = a.AddTranslateOp()
    op.Set((0, 0, 0), 0)
    op.Set((6, 0, 0), 10)
    ctx = context(stage, tmp_path)
    params = {k: v for k, v in PARAMS.items() if k != "time_s"}
    params.update(interval_s=[0, 10], max_evaluations=128, minimum_interval_s=0.001)
    result = sweep(ctx, params)
    assert result.status == "FAIL"
    assert result.evidence["intervals"][0]["observed_distance_m"] == 0
    params.update(b="/World/A", max_evaluations=1)
    assert sweep(ctx, params).status == "FAIL"


def test_continuous_connection_includes_unscheduled_key(tmp_path):
    stage = scene(tmp_path)
    a, b, _ = cubes(stage, 0)
    op = a.AddTranslateOp()
    for t, x in [(0, 0), (4.123, 1), (4.124, 0), (10, 0)]:
        op.Set((x, 0, 0), t)
    ctx = context(stage, tmp_path)
    params = dict(
        a=dict(path="/World/A", local_point=[0, 0, 0]),
        b=dict(path="/World/B", local_point=[0, 0, 0]),
        interval_s=[0, 10],
        max_gap_m=0.01,
        numeric_margin_m=1e-8,
    )
    row = connection(ctx, params)
    assert row.status == "FAIL" and row.evidence["upper_bound_m"] > 1
    a.AddRotateZOp().Set(90, 5)
    stage.GetRootLayer().Save()
    with pytest.raises(MissingEvidence, match="translations only"):
        connection(context(stage, tmp_path), params)


def test_clear_height_zone(tmp_path):
    stage = scene(tmp_path)
    cubes(stage, 3)
    params = dict(
        zone_min_m=[2, -1, -1],
        zone_max_m=[4, 1, 1],
        obstacles=["/World/B"],
        time_s=0,
        numeric_margin_m=1e-8,
        max_triangle_pairs=1000,
    )
    assert zone(context(stage, tmp_path), params).status == "FAIL"


def test_sweep_can_prove_clearance_and_reports_exhausted_budget(tmp_path):
    stage = scene(tmp_path)
    a, b, _ = cubes(stage, 3)
    for geom, offset in ((a, 0), (b, 3)):
        geom.ClearXformOpOrder()
        op = geom.AddTranslateOp()
        op.Set((offset, 0, 0), 0)
        op.Set((offset + 10, 0, 0), 10)
    ctx = context(stage, tmp_path)
    params = {k: v for k, v in PARAMS.items() if k != "time_s"}
    params.update(interval_s=[0, 10], max_evaluations=1, minimum_interval_s=0.001)
    bounded = sweep(ctx, params)
    assert bounded.status == "UNKNOWN" and bounded.evidence["unfinished_intervals"] > 0
    # Analytically the rigid pair keeps a two-metre gap throughout.
    complete = sweep(ctx, dict(params, max_evaluations=128))
    assert complete.status == "PASS" and complete.evidence["unfinished_intervals"] == 0
    row = connection(
        ctx,
        dict(
            a=dict(path="/World/A", local_point=[0, 0, 0]),
            b=dict(path="/World/B", local_point=[-3, 0, 0]),
            interval_s=[0, 10],
            max_gap_m=0.01,
            numeric_margin_m=1e-8,
        ),
    )
    assert row.status == "PASS"


@pytest.mark.parametrize("offset,expected", [(3, "PASS"), (1.5, "FAIL")])
def test_clearance_pack_reports_through_public_evaluate(tmp_path, offset, expected):
    from test_semantic_packs import bundle

    report, row = bundle(
        tmp_path,
        "geometry.clearance",
        "distance",
        PARAMS,
        lambda stage: cubes(stage, offset),
    )
    assert row["status"] == expected, report
    assert report["verdict"] == ("ACCEPT_FOR_USE" if expected == "PASS" else "REJECT")


def test_continuous_pack_keeps_unsupported_rotation_unknown(tmp_path):
    from test_semantic_packs import bundle

    def build(stage):
        a, b, _ = cubes(stage, 0)
        a.AddRotateZOp().Set(90, 5)

    parameters = dict(
        a=dict(path="/World/A", local_point=[0, 0, 0]),
        b=dict(path="/World/B", local_point=[0, 0, 0]),
        interval_s=[0, 10],
        max_gap_m=0.01,
        numeric_margin_m=1e-8,
    )
    report, row = bundle(tmp_path, "motion.continuous", "connection", parameters, build)
    assert row["status"] == "UNKNOWN", report
    assert report["verdict"] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.parametrize("scale", [1e-6, 1.0, 1e6])
def test_crossing_triangles_do_not_gain_clearance_at_small_scale(scale):
    from pxr import Gf
    from scene_acceptance.clearance import distance

    s = scale
    a = [tuple(Gf.Vec3d(*p) for p in [(-s, -s, 0), (s, -s, 0), (0, s, 0)])]
    b = [tuple(Gf.Vec3d(*p) for p in [(0, 0, -s), (0, 0, s), (0, s / 2, s)])]
    assert distance(a, b, False, 10) == 0
