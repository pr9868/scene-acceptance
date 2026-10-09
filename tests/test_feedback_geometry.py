"""Regression controls from the receipt, motion and clearance review.

Synthetic controls establish checker behavior, not model quality or real-scene
failure rates. Analytic distances and evaluated skinning provide independent
expected results.
"""

import pytest
from pxr import Gf, Ts, Usd, UsdGeom, UsdSkel

from scene_acceptance.clearance import distance, static
from scene_acceptance.continuous_motion import connection
from scene_acceptance.model import MissingEvidence
from test_extensions_geometry import PARAMS, context, cubes, scene
from test_semantic_packs import bundle

CONNECTION = dict(
    a=dict(path="/World/A", local_point=[0, 0, 0]),
    b=dict(path="/World/B", local_point=[0, 0, 0]),
    interval_s=[0, 10],
    max_gap_m=0.01,
    numeric_margin_m=1e-8,
)


def spline(attribute):
    value = Ts.Spline()
    for time, x in [(0, 0), (5, 3), (10, 0)]:
        knot = Ts.Knot()
        knot.SetTime(time)
        knot.SetValue(x)
        knot.SetNextInterpolation(Ts.InterpLinear)
        value.SetKnot(knot)
    attribute.SetSpline(value)
    assert attribute.GetTimeSamples() == []
    assert attribute.Get(5) == 3


@pytest.mark.parametrize("parent", [False, True])
def test_spline_cannot_hide_between_connection_endpoints(tmp_path, parent):
    def build(stage):
        a, _, _ = cubes(stage, 0)
        owner = UsdGeom.Xformable(stage.GetPrimAtPath("/World")) if parent else a
        spline(owner.AddTranslateXOp().GetAttr())

    report, row = bundle(tmp_path, "motion.continuous", "connection", CONNECTION, build)
    assert row["status"] == "UNKNOWN", report
    assert "spline" in row["reason"]
    assert report["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_spline_sweep_is_unknown_but_named_static_time_is_evaluated(tmp_path):
    stage = scene(tmp_path)
    a, _, _ = cubes(stage, 3)
    spline(a.AddTranslateXOp().GetAttr())
    ctx = context(stage, tmp_path)
    # The instantaneous transform is evaluated correctly at the collision.
    assert static(ctx, dict(PARAMS, time_s=5)).status == "FAIL"
    from scene_acceptance.clearance import sweep

    params = {k: v for k, v in PARAMS.items() if k != "time_s"}
    with pytest.raises(MissingEvidence, match="spline"):
        sweep(
            ctx,
            dict(
                params, interval_s=[0, 10], max_evaluations=16, minimum_interval_s=0.01
            ),
        )


def test_spline_cube_size_is_not_static_geometry(tmp_path):
    stage = scene(tmp_path)
    a, _, _ = cubes(stage, 3)
    spline(a.GetSizeAttr())
    with pytest.raises(MissingEvidence, match="static positive cube size"):
        static(context(stage, tmp_path), PARAMS)


def test_reset_transform_stack_excludes_unrelated_ancestor_spline(tmp_path):
    stage = scene(tmp_path)
    a, b, _ = cubes(stage, 0)
    spline(UsdGeom.Xformable(stage.GetPrimAtPath("/World")).AddTranslateXOp().GetAttr())
    a.SetResetXformStack(True)
    b.SetResetXformStack(True)
    assert connection(context(stage, tmp_path), CONNECTION).status == "PASS"


def triangle(stage, path, offset):
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr([(offset, 0, 0), (offset + 1, 0, 0), (offset, 1, 0)])
    mesh.CreateFaceVertexCountsAttr([3])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2])
    mesh.CreateSubdivisionSchemeAttr("none")
    return mesh


def skin_collision(stage, inherited=False):
    root = UsdSkel.Root.Define(stage, "/World")
    a = triangle(stage, "/World/A", 0)
    b = triangle(stage, "/World/B", 3)
    sk = UsdSkel.Skeleton.Define(stage, "/World/Skeleton")
    sk.CreateJointsAttr(["joint"])
    sk.CreateBindTransformsAttr([Gf.Matrix4d(1)])
    sk.CreateRestTransformsAttr([Gf.Matrix4d(1)])
    animation = UsdSkel.Animation.Define(stage, "/World/Animation")
    animation.CreateJointsAttr(["joint"])
    animation.CreateTranslationsAttr([Gf.Vec3f(3, 0, 0)])
    animation.CreateRotationsAttr([Gf.Quatf(1)])
    animation.CreateScalesAttr([Gf.Vec3h(1)])
    UsdSkel.BindingAPI.Apply(sk.GetPrim()).CreateAnimationSourceRel().SetTargets(
        [animation.GetPath()]
    )
    binding = UsdSkel.BindingAPI.Apply(a.GetPrim())
    owner = UsdSkel.BindingAPI.Apply(root.GetPrim()) if inherited else binding
    owner.CreateSkeletonRel().SetTargets([sk.GetPath()])
    binding.CreateGeomBindTransformAttr(Gf.Matrix4d(1))
    binding.CreateJointIndicesPrimvar(True, 1).Set([0])
    binding.CreateJointWeightsPrimvar(True, 1).Set([1.0])
    cache = UsdSkel.Cache()
    cache.Populate(root, Usd.PrimDefaultPredicate)
    query = cache.GetSkelQuery(sk)
    skinning = cache.GetSkinningQuery(a.GetPrim())
    points = a.GetPointsAttr().Get()
    assert skinning.ComputeSkinnedPoints(
        query.ComputeSkinningTransforms(Usd.TimeCode(0)), points, Usd.TimeCode(0)
    )
    assert points == b.GetPointsAttr().Get()  # Evaluated surfaces coincide.


@pytest.mark.parametrize("inherited", [False, True])
def test_skinned_collision_cannot_pass_from_rest_points(tmp_path, inherited):
    report, row = bundle(
        tmp_path,
        "geometry.clearance",
        "distance",
        dict(PARAMS, representation="surfaces"),
        lambda stage: skin_collision(stage, inherited),
    )
    assert row["status"] == "UNKNOWN", report
    assert "skinning" in row["reason"]
    assert report["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_blend_shape_is_not_rest_geometry(tmp_path):
    stage = scene(tmp_path)
    a = triangle(stage, "/World/A", 0)
    triangle(stage, "/World/B", 3)
    shape = UsdSkel.BlendShape.Define(stage, "/World/Shape")
    shape.CreateOffsetsAttr([(3, 0, 0)] * 3)
    binding = UsdSkel.BindingAPI.Apply(a.GetPrim())
    binding.CreateBlendShapesAttr(["move"])
    binding.CreateBlendShapeTargetsRel().SetTargets([shape.GetPath()])
    with pytest.raises(MissingEvidence, match="blend-shape"):
        static(context(stage, tmp_path), dict(PARAMS, representation="surfaces"))


@pytest.mark.parametrize("angle", [0, 10, 20, 30, 45, 60, 90])
@pytest.mark.parametrize(
    "offset,expected", [(3, "PASS"), (1.5, "FAIL"), (0.25, "FAIL")]
)
def test_global_rotation_preserves_analytic_clearance(
    tmp_path, angle, offset, expected
):
    stage = scene(tmp_path)
    cubes(stage, offset)
    UsdGeom.Xformable(stage.GetPrimAtPath("/World")).AddRotateXYZOp().Set(
        (angle, angle / 2, angle / 3)
    )
    result = static(context(stage, tmp_path), PARAMS)
    assert result.status == expected
    assert result.evidence["distance_m"] == pytest.approx(max(0, offset - 1), abs=1e-9)


@pytest.mark.parametrize("scale", [1e-6, 1, 1e6])
def test_near_parallel_crossing_is_not_discarded(scale):
    a = [tuple(Gf.Vec3d(*p) * scale for p in [(0, 0, 0), (1, 0, 0), (0, 1, 0)])]
    b = [
        tuple(
            Gf.Vec3d(*p) * scale
            for p in [(0.1, 0.1, -1e-16), (0.8, 0.1, 1e-16), (0.1, 0.8, 1e-16)]
        )
    ]
    assert distance(a, b, False, 10) == 0
