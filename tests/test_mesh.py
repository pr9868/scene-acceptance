"""Consumer acceptance cases, representation gaps and integrity regressions."""

from pathlib import Path
import json, shutil
import pytest
from pxr import Usd, UsdGeom
from scene_acceptance import evaluate
from scene_acceptance.model import sha

ROOT = Path(__file__).resolve().parents[1] / "evaluation/mesh-v1"
FIXTURES = ROOT / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())


def run(d):
    return evaluate(
        "contract.json",
        "scene.usda",
        bundle_root=d,
        baseline_path="baseline.usda" if (d / "baseline.usda").exists() else None,
        claims_path="claims.json" if (d / "claims.json").exists() else None,
    )


@pytest.mark.parametrize("case", MANIFEST["cases"], ids=lambda c: c["id"])
def test_frozen_mesh_acceptance(case):
    d = FIXTURES / case["id"]
    r = run(d)
    assert r["verdict"] == case["expected"], r
    for name, digest in MANIFEST["files"].items():
        if name.startswith(case["id"] + "/"):
            assert sha(FIXTURES / name) == digest


@pytest.mark.parametrize(
    "name", ["interior_shape_changed_same_bounds", "rotated_shape_same_bounds"]
)
def test_equal_bounds_do_not_hide_shape_changes(name):
    r = run(FIXTURES / name)
    by = {c["id"]: c for c in r["checks"]}
    assert by["layout"]["status"] == "PASS"
    assert by["target"]["status"] == "PASS"
    assert by["mesh"]["status"] == "PASS"
    o = by["shape"]["evidence"]["observations"][0]
    assert all(
        abs(a - b) < 1e-5
        for k in ["min", "max"]
        for a, b in zip(o["baseline_bounds_m"][k], o["candidate_bounds_m"][k])
    )
    assert by["shape"]["status"] == "FAIL"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_mesh_check",
        "advisory_mesh_check",
        "unchecked_shape",
        "invalid_shape_path",
        "legacy_closure_rule",
    ],
)
def test_contract_requirements_cannot_be_skipped(tmp_path, mutation):
    d = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "translated_mesh", d)
    c = json.loads((d / "contract.json").read_text())
    if mutation in ["missing_mesh_check", "advisory_mesh_check"]:
        c["checks"]["required"].remove("mesh")
        if mutation == "advisory_mesh_check":
            c["checks"]["advisory"].append("mesh")
    elif mutation == "unchecked_shape":
        c["checks"]["required"].remove("shape")
    elif mutation == "invalid_shape_path":
        c["shape"]["paths"] = ["/World.attr"]
    else:
        c.update(
            profile="usd-static-cubes-v1",
            mesh_rules={"require_closed_edges": ["/World/Equipment/Part"]},
        )
    (d / "contract.json").write_text(json.dumps(c))
    assert run(d)["verdict"] == "EVALUATION_ERROR"


def test_mesh_native_topology_is_not_enough_for_a_task():
    r = run(FIXTURES / "wrong_destination")
    by = {c["id"]: c for c in r["checks"]}
    assert (
        by["mesh"]["evidence"]["meshes"]["/World/Equipment/Part"]["native_topology"][
            "valid"
        ]
        is True
    )
    assert by["target"]["status"] == "FAIL"


@pytest.mark.parametrize(
    "attr,value",
    [("faceVertexCounts", [-1]), ("faceVertexCounts", []), ("faceVertexIndices", [])],
)
def test_bad_mesh_arrays_do_not_pass(tmp_path, attr, value):
    d = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "quad_layout", d)
    s = Usd.Stage.Open(str(d / "scene.usda"))
    s.GetPrimAtPath("/World/Equipment/Part").GetAttribute(attr).Set(value)
    s.GetRootLayer().Save()
    assert run(d)["verdict"] == "REJECT"


def test_default_subdivision_is_not_treated_as_polygon(tmp_path):
    d = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "quad_layout", d)
    s = Usd.Stage.Open(str(d / "scene.usda"))
    UsdGeom.Mesh(
        s.GetPrimAtPath("/World/Equipment/Part")
    ).GetSubdivisionSchemeAttr().Clear()
    s.GetRootLayer().Save()
    assert run(d)["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_old_unrequested_shape_gap_remains_explicit(tmp_path):
    d = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "previous_shrunk_derivative", d)
    c = json.loads((d / "contract.json").read_text())
    del c["shape"]
    c["checks"]["required"].remove("shape")
    (d / "contract.json").write_text(json.dumps(c))
    assert run(d)["verdict"] == "ACCEPT_FOR_USE"


def test_rotated_centimetre_mesh_extrema_have_analytic_oracle():
    import math

    r = run(FIXTURES / "centimetre_rotated_parent")
    box = next(c for c in r["checks"] if c["id"] == "layout")["evidence"]["bounds"][
        "/World/Equipment/Part"
    ]
    angle = math.radians(37)
    x = 3 * math.cos(angle) - 2 * math.sin(angle)
    y = 3 * math.sin(angle) + 2 * math.cos(angle)
    hx = math.cos(angle) + 0.5 * math.sin(angle)
    hy = math.sin(angle) + 0.5 * math.cos(angle)
    assert box["min"] == pytest.approx([x - hx, y - hy, 0.1], abs=1e-6)
    assert box["max"] == pytest.approx([x + hx, y + hy, 0.3], abs=1e-6)


@pytest.mark.parametrize(
    "limits", [(7, 250000, 1000000), (250000, 5, 1000000), (250000, 250000, 23)]
)
def test_mesh_resource_limits_are_evaluation_errors(monkeypatch, limits):
    import scene_acceptance.mesh as module

    monkeypatch.setattr(module, "LIMITS", limits)
    r = run(FIXTURES / "quad_layout")
    assert r["verdict"] == "EVALUATION_ERROR"
    assert "resource limit" in r["checks"][0]["reason"]


def test_edge_closure_does_not_claim_physical_evidence(tmp_path):
    from scene_acceptance.usd_reader import Scene, Bundle

    d = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "quad_layout", d)
    c = json.loads((d / "contract.json").read_text())
    c["checks"]["required"].append("claims")
    c["mesh_rules"] = {"require_closed_edges": ["/World/Equipment/Part"]}
    (d / "contract.json").write_text(json.dumps(c))
    claims = {
        "schema_version": "1.0",
        "artifact_set_sha256": Scene(
            Bundle(d, []), "scene.usda", c["profile"]
        ).artifact_set_sha256,
        "claims": [
            {
                "id": "friction",
                "path": "/World/Equipment/Part",
                "metric": "friction",
                "value": 0.5,
                "unit": "1",
                "basis": "assumed",
            }
        ],
    }
    (d / "claims.json").write_text(json.dumps(claims))
    r = run(d)
    assert r["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert next(c for c in r["checks"] if c["id"] == "mesh")["status"] == "PASS"


def test_equivalent_reindex_is_explicitly_outside_shape_equivalence(tmp_path):
    d = tmp_path / "bundle"
    shutil.copytree(FIXTURES / "translated_mesh", d)
    s = Usd.Stage.Open(str(d / "scene.usda"))
    m = UsdGeom.Mesh(s.GetPrimAtPath("/World/Equipment/Part"))
    points = list(m.GetPointsAttr().Get())
    m.GetPointsAttr().Set(points[::-1])
    m.GetFaceVertexIndicesAttr().Set(
        [len(points) - 1 - i for i in m.GetFaceVertexIndicesAttr().Get()]
    )
    s.GetRootLayer().Save()
    r = run(d)
    by = {c["id"]: c["status"] for c in r["checks"]}
    assert by["layout"] == "PASS" and by["mesh"] == "PASS" and by["shape"] == "FAIL"
