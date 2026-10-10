"""Regression controls for projected references and bounded preparation revision."""

from copy import deepcopy
import json
import sys
import pytest
from pxr import UsdGeom
from scene_acceptance.model import ContractError, digest_json
from scene_acceptance.model_protocol import prepare_request, validation_context
from scene_acceptance.judge import run_request
from scene_acceptance.assumption_audit import RESPONSE_SCHEMA, validate_response
from scene_acceptance.review_context import save
from scene_acceptance.application import invoke
from scene_acceptance.preparation import prepare_scene
from scene_acceptance.plan_revision import validate_revision
from test_preparation import bundle, setup
from test_extensions_geometry import scene


def adapter(tmp_path, body):
    p = tmp_path / "adapter.py"
    p.write_text("import json,sys\nr=json.load(sys.stdin)\n" + body)
    return dict(
        driver="json-cli",
        executable=sys.executable,
        args=[str(p)],
        model="protocol-control",
        effort="none",
        timeout_seconds=10,
    )


@pytest.mark.parametrize(
    "target,ok", [("/World/P512", True), ("/World/Missing", False)]
)
def test_audit_validates_full_admitted_inventory(tmp_path, target, ok):
    request = dict(
        scene=dict(prim_paths=[f"/World/P{i}" for i in range(513)], inventory={}),
        evidence=[dict(id="declared", prim_paths=["/World/P512"])],
    )
    response = dict(
        schema_version="1.0",
        questions=[
            dict(
                id="question-17",
                question="Inspect the declared part?",
                possible_consequence="Unreviewed interface",
                evidence_ids=["declared"],
                prim_paths=[target],
                needed_evidence=[],
            )
        ],
        limitations=["Software control"],
    )
    cfg = adapter(
        tmp_path,
        "v="
        + repr(response)
        + '\nv["request_sha256"]=r["request_sha256"]\nprint(json.dumps(v))\n',
    )
    result = run_request(
        request,
        {},
        [],
        cfg,
        tmp_path / "model",
        role="audit",
        response_schema=RESPONSE_SCHEMA,
        response_validator=validate_response,
    )
    assert (result["status"] == "AUDIT_COMPLETE") == ok, result
    assert len(request["scene"]["prim_paths"]) == 512
    if not ok:
        assert "question-17" in result["error"] and "/World/Missing" in result["error"]
        assert "evidence IDs=[]" in result["error"]


def test_unknown_evidence_is_named():
    req = dict(request_sha256="0" * 64, scene=dict(prim_paths=[]), evidence=[])
    response = dict(
        schema_version="1.0",
        request_sha256="0" * 64,
        questions=[
            dict(
                id="q2",
                question="Check?",
                possible_consequence="Gap",
                evidence_ids=["bad-id"],
                prim_paths=[],
                needed_evidence=[],
            )
        ],
        limitations=["Control"],
    )
    with pytest.raises(ContractError, match="q2.*bad-id"):
        validate_response(response, req)


def test_full_references_do_not_restore_omitted_measurements():
    request = dict(
        scene=dict(prim_paths=[f"/P{i}" for i in range(20)], inventory={}),
        evidence=[
            dict(id="measure", role="script_measurement", observations=list(range(20)))
        ],
        evidence_coverage={
            "q": dict(
                evidence_kind="measurements",
                available=True,
                suitable_evidence_ids=["measure"],
            )
        },
    )
    full = prepare_request(request, "judge", {}, 16)
    checked = validation_context(request, full)
    assert len(checked["scene"]["prim_paths"]) == 20
    assert len(checked["evidence"][0]["observations"]) == 16
    assert not checked["evidence_coverage"]["q"]["available"]
    assert checked["request_sha256"] == request["request_sha256"]


def test_projection_identity_accounts_for_actual_context():
    def make(path, limit):
        r = dict(
            scene=dict(prim_paths=[f"/P{i}" for i in range(30)], inventory={}),
            evidence=[dict(path=path)],
        )
        r["request_sha256"] = digest_json(r)
        prepare_request(r, "audit", {}, limit, {path: "1" * 64})
        return r["model_protocol"]

    a, b, c = make("/a/view.png", 16), make("/b/view.png", 16), make("/a/view.png", 24)
    assert (
        a["semantic_input_sha256"]
        == b["semantic_input_sha256"]
        == c["semantic_input_sha256"]
    )
    assert a["projected_context_sha256"] == b["projected_context_sha256"]
    assert a["projected_context_sha256"] != c["projected_context_sha256"]


def test_preparation_blocks_capture_but_keeps_diagnostics_and_scope_review(
    bundle, tmp_path
):
    from scene_acceptance.scope import approve_scope
    from scene_acceptance.prepared_run import evaluate_prepared

    kw = setup(tmp_path, bundle)
    caps = json.loads(kw["capture_capabilities"].read_text())
    caps["max_images"] = 0
    save(kw["capture_capabilities"], caps)
    envelope = invoke("prepare", **kw)
    assert envelope["status"] == "completed" and envelope["exit_code"] == 3, envelope
    plan = envelope["data"]
    assert plan["next_action"] == "revise_preparation"
    assert not plan["readiness"]["ready_for_capture"]
    assert plan["readiness"]["blockers"][0]["kind"] == "capture_feasibility"
    approve_scope(
        preparation=kw["out"],
        out=tmp_path / "approval.json",
        expected_scope_sha256=plan["scope_sha256"],
        reviewer="test owner",
        reason="Scope accepted; evidence remains outstanding",
    )
    result = evaluate_prepared(preparation=kw["out"], out=tmp_path / "checks")
    assert result["script_verdict"] == "REJECT" and result["exit_code"] == 2


def revision_fixture(tmp_path, behavior="repair"):
    root = tmp_path / "scene"
    root.mkdir()
    stage = scene(root)
    UsdGeom.Xform.Define(stage, "/World/Group")
    UsdGeom.Cube.Define(stage, "/World/Group/Part").AddTranslateOp().Set((5, 0, 0))
    stage.GetRootLayer().Save()
    (root / "brief.txt").write_text(
        "All parts in Group must remain outside the zone [-1,-1,-1] to [1,1,1] metres at 0 seconds. Treat them as closed solids, prohibit contact, use a numeric margin of 0.000001 metres and at most 10000 triangle pairs."
    )
    save(
        root / "brief.json",
        dict(
            schema_version="1.0",
            id="control",
            title="Control",
            intended_use="Layout test",
            provenance="Constructed software test",
            files=[dict(path="brief.txt", role="text", caption="Test requirement")],
        ),
    )
    body = """
s=r['sources'][0]
p=dict(obstacles=['/World/Group'],zone_min_m=[-1,-1,-1],zone_max_m=[1,1,1],time_s=0,numeric_margin_m=0.000001,max_triangle_pairs=10000,representation='closed-solids',contact_policy='forbid')
items=[dict(id='clear',statement=s['text'],source_ids=[s['id']],quotes=[dict(source_id=s['id'],quote=s['text'])],route='script',reason='Declared zone',area='geometry',checks=[dict(id='spec.clear',type_id='geometry.clearance.clear_zone',parameters_json=json.dumps(p))],visual=None)]
if 'plan_revision' in r:
 items=r['plan_revision']['previous_interpretation']['requirements']
 p=json.loads(items[0]['checks'][0]['parameters_json'])
 if BEHAVIOR=='repair':p.pop('obstacles');p['selector']={'root':'/World/Group'}
 if BEHAVIOR=='weaken':p['contact_policy']='allow';p['contact_tolerance_m']=0.001
 items[0]['checks'][0]['parameters_json']=json.dumps(p)
print(json.dumps(dict(request_sha256=r['request_sha256'],requirements=items,limitations=['Synthetic adapter; not a model-quality test'])))
""".replace("BEHAVIOR", repr(behavior))
    config = tmp_path / "config.json"
    save(config, adapter(tmp_path, body))
    from scene_acceptance.review_context import GENERAL_RUBRIC

    rubric = deepcopy(GENERAL_RUBRIC)
    rubric["criteria"] = []
    rp = tmp_path / "rubric.json"
    save(rp, rubric)
    return dict(
        bundle_root=root,
        candidate="scene.usda",
        raw_brief="brief.json",
        interpreter_config=config,
        rubric=rp,
        out=tmp_path / "prepared",
    )


@pytest.mark.parametrize(
    "behavior,attempts,ready,count",
    [
        ("repair", 0, False, 0),
        ("repair", 1, True, 1),
        ("weaken", 2, False, 1),
        ("unchanged", 2, False, 2),
    ],
)
def test_bounded_revision_keeps_policy_and_attempts(
    tmp_path, behavior, attempts, ready, count
):
    kw = revision_fixture(tmp_path, behavior)
    plan = prepare_scene(**kw, plan_revision_attempts=attempts)
    assert plan["readiness"]["ready_for_capture"] == ready, plan["readiness"]
    records = json.loads((kw["out"] / "revision-attempts.json").read_text())
    assert len(records["attempts"]) == count
    brief = json.loads((kw["out"] / plan["bundle"] / plan["brief"]).read_text())
    p = brief["checks"][0]["parameters"]
    assert p["contact_policy"] == "forbid" and "contact_tolerance_m" not in p
    assert p["representation"] == "closed-solids"
    assert plan["mapping_review"] == "pending"
    if behavior == "weaken":
        assert "changed check policy" in records["attempts"][0]["error"]


@pytest.mark.parametrize(
    "change",
    [
        "drop-requirement",
        "drop-check",
        "route",
        "tolerance",
        "exclude",
        "timestamp",
        "target",
        "fidelity",
    ],
)
def test_revision_rejects_weakening(bundle, tmp_path, change):
    kw = setup(tmp_path, bundle)
    prepare_scene(**kw)
    old = json.loads((kw["out"] / "interpretation.json").read_text())
    new = deepcopy(old)
    if change == "drop-requirement":
        new["requirements"].pop()
    elif change == "drop-check":
        new["requirements"][0]["checks"] = []
    elif change == "route":
        new["requirements"][0]["route"] = "unresolved"
    elif change in ("tolerance", "exclude"):
        c = new["requirements"][0]["checks"][0]
        p = json.loads(c["parameters_json"])
        p["tolerance_m"] = 1
        c["parameters_json"] = json.dumps(p)
    else:
        c = new["requirements"][1]["visual"]["captures"][0]
        c[
            {
                "timestamp": "times_seconds",
                "target": "targets",
                "fidelity": "capabilities",
            }[change]
        ] = []
    with pytest.raises(ContractError):
        validate_revision(old, new)


def test_interpreter_can_bind_a_capture_beyond_projection_limit(bundle, tmp_path):
    from scene_acceptance.preparation import (
        INTERPRETATION_SCHEMA,
        validate_interpretation,
    )

    kw = setup(tmp_path, bundle)
    prepare_scene(**kw)
    request = json.loads((kw["out"] / "interpreter/full-context.json").read_text())
    response = json.loads((kw["out"] / "interpretation.json").read_text())
    request["scene"]["prim_paths"] = [f"/World/Early{i}" for i in range(512)] + [
        "/World/Panel"
    ]
    cfg = adapter(
        tmp_path,
        "v="
        + repr(response)
        + '\nv["request_sha256"]=r["request_sha256"]\nprint(json.dumps(v))\n',
    )
    result = run_request(
        request,
        {},
        [],
        cfg,
        tmp_path / "projected-interpreter",
        role="interpreter",
        response_schema=INTERPRETATION_SCHEMA,
        response_validator=validate_interpretation,
    )
    assert result["status"] == "INTERPRETATION_COMPLETE", result
    assert "/World/Panel" not in request["scene"]["prim_paths"]


@pytest.mark.parametrize("wrong_scene", [False, True])
def test_declaration_diagnostics_and_scene_identity(tmp_path, wrong_scene):
    from scene_acceptance.assumption_audit import run_audit
    from scene_acceptance.profiles import discover_artifact

    root = tmp_path / "source"
    root.mkdir()
    s = scene(root)
    s.GetRootLayer().Save()
    identity = discover_artifact(root, "scene.usda").artifact_set_sha256
    declarations = tmp_path / "decisions.json"
    save(
        declarations,
        dict(
            schema_version="1.0",
            scene_sha256="0" * 64 if wrong_scene else identity,
            decisions=[
                dict(
                    id="transfer-choice",
                    statement="Declared part",
                    reason="Control",
                    prim_paths=["/World/Absent"],
                )
            ],
        ),
    )
    cfg = tmp_path / "model.json"
    save(cfg, adapter(tmp_path, 'raise RuntimeError("must not run")\n'))
    match = (
        "another scene revision" if wrong_scene else "transfer-choice.*?/World/Absent"
    )
    with pytest.raises(ContractError, match=match):
        run_audit(
            bundle_root=root,
            candidate="scene.usda",
            out=tmp_path / "audit",
            audit_config=cfg,
            producer_decisions=declarations,
        )


def test_exact_subtree_revision_cannot_add_exclusions(tmp_path):
    kw = revision_fixture(tmp_path)
    prepare_scene(**kw)
    old = json.loads((kw["out"] / "interpretation.json").read_text())
    new = deepcopy(old)
    c = new["requirements"][0]["checks"][0]
    p = json.loads(c["parameters_json"])
    p.pop("obstacles")
    p["selector"] = dict(root="/World/Group", exclude=["/World/Group/Part"])
    c["parameters_json"] = json.dumps(p)
    with pytest.raises(ContractError, match="changed check policy"):
        validate_revision(old, new)


def test_revision_retains_capture_scope_while_proposing_sharing(bundle, tmp_path):
    kw = setup(tmp_path, bundle)
    prepare_scene(**kw)
    old = json.loads((kw["out"] / "interpretation.json").read_text())
    new = deepcopy(old)
    capture = new["requirements"][1]["visual"]["captures"][0]
    capture.update(
        sharing_group="front", camera_id="front"
    )
    assert validate_revision(old, new) == new
    assert new["requirements"][1]["visual"]["captures"][0]["sharing_group"] == "front"


@pytest.mark.parametrize(
    "key,value",
    [
        ("camera_id", "different-camera"),
        ("projection", "perspective"),
        ("camera_guidance", "Rear view instead"),
    ],
)
def test_revision_cannot_replace_declared_camera_or_framing(
    bundle, tmp_path, key, value
):
    kw = setup(tmp_path, bundle)
    prepare_scene(**kw)
    old = json.loads((kw["out"] / "interpretation.json").read_text())
    old["requirements"][1]["visual"]["captures"][0].update(
        camera_id="front", projection="orthographic"
    )
    proposed = deepcopy(old)
    proposed["requirements"][1]["visual"]["captures"][0][key] = value
    with pytest.raises(ContractError):
        validate_revision(old, proposed)
