"""Real core evaluations and adversarial review controls; no producer submission used."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import pytest
from scene_acceptance.model import sha
from scene_acceptance.contract_upgrade import upgrade_copied_contracts
from scene_acceptance.packs import Pack, CheckSpec, Outcome, default_registry
from scene_acceptance.review import assess
from scene_acceptance.review.__main__ import render, write_report
from scene_acceptance.review.schemas import LAYERS

ROOT = Path(__file__).resolve().parents[1]


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def item(name, layer, checks=(), *, review=False, required=True):
    return {"id": name, "layer": layer, "statement": name, "basis": "Constructed development control",
            "required": required, "check_ids": list(checks), "review_required": review,
            "decision_id": "triangulation" if layer == "decisions" else None,
            "inference_authorization": {"status": "approved", "by": "Control policy author", "reason": "Selected rule for this control"} if layer == "inferred" else None}


def prepare(root, fixture="material_correct"):
    root.mkdir(parents=True, exist_ok=True)
    bundle, owner = root / "delivery", root / "review"
    shutil.copytree(ROOT / "evaluation/packs-v1/fixtures" / fixture, bundle)
    upgrade_copied_contracts(bundle)
    owner.mkdir()
    plan = {"schema_version": "1.0", "id": "material-scope-control",
            "intended_use": "Constructed visual-delivery review; no real engineering approval",
            "contract": "contract.json", "contract_sha256": sha(bundle / "contract.json"),
            "candidate": "scene.usda", "baseline": None,
            "mapping_review": {"status": "reviewed", "reviewer": "Constructed control policy", "reason": "Known mapping for the test; not a human assessment"},
            "layers": {layer: {"scope": "excluded", "reason": "Not required in this narrow control"} for layer in LAYERS},
            "items": [item("material-binding", "explicit", ["appearance.delivery"])]}
    plan["layers"]["explicit"] = {"scope": "included", "reason": "Named material must be bound"}
    save(owner / "plan.json", plan)
    return bundle, owner, plan


def run(bundle, owner, plan, **kwargs):
    save(owner / "plan.json", plan)
    return assess("plan.json", review_root=owner, bundle_root=bundle,
                  expected_plan_sha256=sha(owner / "plan.json"), **kwargs)


def add_decision(bundle, plan):
    plan["layers"]["decisions"]["scope"] = "included"
    plan["items"].append(item("meshing-choice", "decisions", review=True))
    data = {"schema_version": "1.0", "decisions": [{"id": "triangulation", "choice": "One triangle",
            "reason": "Sufficient for this deliberately minimal fixture", "alternatives": ["Quad"],
            "assumptions": ["No manufacturing use"], "affected_paths": ["/World/Panel"], "evidence": ["scene.usda"]}]}
    save(bundle / "decisions.json", data)
    return data


def approve(owner, initial, statuses=None):
    (owner / "control-review.txt").write_text("Synthetic reviewer record for software controls only. No human or engineering approval.\n")
    statuses = statuses or {"meshing-choice": "approved"}
    data = {"schema_version": "1.0", "snapshot_sha256": initial["snapshot_sha256"],
            "reviews": [{"item_id": key, "status": status,
                         "reviewer": "Synthetic control reviewer, not a human approval",
                         "reason": "Constructed test of recorded judgment semantics",
                         "evidence": [{"path": "control-review.txt", "sha256": sha(owner / "control-review.txt")}]} for key, status in statuses.items()]}
    save(owner / "reviews.json", data)
    return data


@pytest.fixture
def case(tmp_path):
    return prepare(tmp_path)


def test_narrow_scope_does_not_pretend_excluded_layers_pass(case):
    b, o, p = case
    r = run(b, o, p)
    assert r["core_verdict"] == "ACCEPT_FOR_USE"
    assert r["assessment_verdict"] == "ACCEPT_FOR_DECLARED_SCOPE"
    assert r["layers"]["decisions"]["coverage"] == "EXCLUDED"


@pytest.mark.parametrize("layer", LAYERS)
def test_included_but_empty_layer_blocks_acceptance(case, layer):
    b, o, p = case
    if layer == "explicit":
        p["items"][0]["layer"] = "delivery"
        p["layers"]["delivery"]["scope"] = "included"
    p["layers"][layer]["scope"] = "included"
    r = run(b, o, p)
    assert r["core_verdict"] == "ACCEPT_FOR_USE"
    assert r["assessment_verdict"] == "NEEDS_REVIEW"
    assert r["layers"][layer]["coverage"] == "NOT_ASSESSED"


def test_actual_omitted_check_is_exposed_without_inventing_failure(tmp_path):
    b, o, p = prepare(tmp_path, "omitted_material_requirement")
    p["items"][0]["check_ids"] = []
    r = run(b, o, p)
    assert r["core_verdict"] == "ACCEPT_FOR_USE"
    assert r["assessment_verdict"] == "NEEDS_REVIEW"
    assert r["items"][0]["status"] == "UNKNOWN"


def test_invalid_mapping_is_configuration_error(case):
    b, o, p = case
    p["items"][0]["check_ids"] = ["made.up.check"]
    assert run(b, o, p)["assessment_verdict"] == "EVALUATION_ERROR"


def test_wrong_but_valid_mapping_is_not_automatically_discovered(tmp_path):
    b, o, p = prepare(tmp_path, "omitted_material_requirement")
    p["items"][0]["check_ids"] = ["format"]
    r = run(b, o, p)
    assert r["assessment_verdict"] == "ACCEPT_FOR_DECLARED_SCOPE"
    assert "Mapping relevance" in " ".join(r["limitations"])


def test_unreviewed_mapping_blocks(case):
    b, o, p = case
    p["mapping_review"]["status"] = "pending"
    assert run(b, o, p)["assessment_verdict"] == "NEEDS_REVIEW"


@pytest.mark.parametrize("required,expected", [(True, "NEEDS_REVIEW"), (False, "ACCEPT_FOR_DECLARED_SCOPE")])
def test_unapproved_inference_is_not_an_established_requirement(case, required, expected):
    b, o, p = case
    p["layers"]["inferred"]["scope"] = "included"
    inferred = item("format-convention", "inferred", ["format"], required=required)
    inferred["inference_authorization"]["status"] = "proposed"
    p["items"].append(inferred)
    r = run(b, o, p)
    assert r["assessment_verdict"] == expected
    assert r["items"][1]["status"] == "UNKNOWN"


@pytest.mark.parametrize("status,expected", [("approved", "ACCEPT_FOR_DECLARED_SCOPE"), ("rejected", "REJECT"), ("needs_review", "NEEDS_REVIEW")])
def test_separate_decision_judgment(case, status, expected):
    b, o, p = case
    add_decision(b, p)
    initial = run(b, o, p, decision_record="decisions.json")
    assert initial["assessment_verdict"] == "NEEDS_REVIEW"
    approve(o, initial, {"meshing-choice": status})
    reviewed = run(b, o, p, decision_record="decisions.json", review_record="reviews.json")
    assert reviewed["assessment_verdict"] == expected, reviewed
    assert reviewed["snapshot_sha256"] == initial["snapshot_sha256"]


def test_missing_decision_does_not_pass_on_reviewer_approval(case):
    b, o, p = case
    add_decision(b, p)
    initial = run(b, o, p)
    approve(o, initial)
    assert run(b, o, p, review_record="reviews.json")["assessment_verdict"] == "NEEDS_REVIEW"


def test_producer_cannot_self_approve(case):
    b, o, p = case
    data = add_decision(b, p)
    data["decisions"][0]["approved"] = True
    save(b / "decisions.json", data)
    r = run(b, o, p, decision_record="decisions.json")
    assert r["assessment_verdict"] == "EVALUATION_ERROR"


@pytest.mark.parametrize("change", ["scene", "texture", "decision", "plan", "review-evidence", "missing-evidence"])
def test_stale_inputs_invalidate_review(case, change):
    b, o, p = case
    add_decision(b, p)
    initial = run(b, o, p, decision_record="decisions.json")
    approve(o, initial)
    if change == "scene":
        with (b / "scene.usda").open("a") as f:
            f.write("\n# changed scene\n")
    elif change == "texture":
        with (b / "pixel.png").open("ab") as f:
            f.write(b"changed")
    elif change == "decision":
        data = json.loads((b / "decisions.json").read_text())
        data["decisions"][0]["reason"] = "Different rationale"
        save(b / "decisions.json", data)
    elif change == "plan":
        p["items"][1]["basis"] = "Changed policy basis"
    elif change == "review-evidence":
        (o / "control-review.txt").write_text("different observation")
    else:
        (o / "control-review.txt").unlink()
    r = run(b, o, p, decision_record="decisions.json", review_record="reviews.json")
    assert r["assessment_verdict"] == "NEEDS_REVIEW", r


def test_reviewer_approval_cannot_override_known_failure(case):
    b, o, p = case
    scene = b / "scene.usda"
    scene.write_text(scene.read_text().replace("rel material:binding = </World/Looks/Coating>", "rel material:binding = </World/Looks/Other>"))
    p["items"][0]["review_required"] = True
    initial = run(b, o, p)
    approve(o, initial, {"material-binding": "approved"})
    r = run(b, o, p, review_record="reviews.json")
    assert r["core_verdict"] == "REJECT"
    assert r["assessment_verdict"] == "REJECT"
    assert r["items"][0]["status"] == "FAIL"


def test_unmapped_producer_choice_requires_scope_review(case):
    b, o, p = case
    add_decision(b, deepcopy(p))
    r = run(b, o, p, decision_record="decisions.json")
    assert r["assessment_verdict"] == "NEEDS_REVIEW"
    assert r["unmapped_decisions"] == ["triangulation"]


@pytest.mark.parametrize("kind", ["plan-hash", "contract-hash", "duplicate-item", "nested-roots", "path-escape", "symlink-escape"])
def test_bad_policy_and_boundaries(case, kind, tmp_path):
    b, o, p = case
    if kind == "plan-hash":
        r = assess("plan.json", review_root=o, bundle_root=b, expected_plan_sha256="0" * 64)
    elif kind == "nested-roots":
        r = assess("review/plan.json", review_root=tmp_path, bundle_root=b, expected_plan_sha256=sha(o / "plan.json"))
    else:
        if kind == "contract-hash":
            p["contract_sha256"] = "0" * 64
        elif kind == "duplicate-item":
            p["items"].append(deepcopy(p["items"][0]))
        elif kind == "path-escape":
            p["candidate"] = "../review/plan.json"
        else:
            (b / "escape.usda").symlink_to(o / "plan.json")
            p["candidate"] = "escape.usda"
        r = run(b, o, p)
    assert r["assessment_verdict"] == "EVALUATION_ERROR"


def test_changed_review_input_during_core_run_is_error(case):
    b, o, p = case
    def mutate(*_):
        (o / "plan.json").write_text("{}")
        return Outcome("PASS", "Mutation control")
    registry = default_registry()
    registry.add(Pack("test.mutation", "1.0.0", "Review mutation control",
                      {"mutate": CheckSpec(mutate, {"type": "object"}, "Mutation control", "Test only")},
                      (str(Path(__file__)),)))
    contract = json.loads((b / "contract.json").read_text())
    contract["packs"]["test.mutation"] = {"version": "1.0.0"}
    contract["checks"].append({"id": "mutate", "pack": "test.mutation", "check": "mutate", "parameters": {}, "required": True})
    save(b / "contract.json", contract)
    p["contract_sha256"] = sha(b / "contract.json")
    r = run(b, o, p, pack_registry=registry)
    assert r["assessment_verdict"] == "EVALUATION_ERROR"
    assert "changed" in " ".join(r["errors"]).lower()


def test_report_escapes_producer_text_and_preserves_core(case, tmp_path):
    b, o, p = case
    data = add_decision(b, p)
    data["decisions"][0]["choice"] = "<script>alert(1)</script>"
    save(b / "decisions.json", data)
    r = run(b, o, p, decision_record="decisions.json")
    assert "<script>" not in render(r)
    assert "&lt;script&gt;" in render(r)
    out = tmp_path / "report"
    write_report(r, out)
    assert json.loads((out / "core-result.json").read_text()) == r["core_report"]
    with pytest.raises(FileExistsError):
        write_report(r, out)


@pytest.mark.parametrize("required,expected", [(True, "REJECT"), (False, "ACCEPT_FOR_DECLARED_SCOPE")])
def test_obligation_can_require_a_core_advisory_check(case, required, expected):
    b, o, p = case
    contract = json.loads((b / "contract.json").read_text())
    contract["checks"][1]["required"] = False
    save(b / "contract.json", contract)
    p["contract_sha256"] = sha(b / "contract.json")
    p["items"][0]["required"] = required
    p["items"].append(item("metadata", "explicit", ["format"]))
    scene = b / "scene.usda"
    scene.write_text(scene.read_text().replace("rel material:binding = </World/Looks/Coating>", "rel material:binding = </World/Looks/Other>"))
    r = run(b, o, p)
    assert r["core_verdict"] == "ACCEPT_FOR_USE"
    assert r["assessment_verdict"] == expected
    assert r["items"][0]["status"] == "FAIL"


def test_all_five_layers_with_manual_use_evidence(case):
    b, o, p = case
    add_decision(b, p)
    for layer in LAYERS:
        p["layers"][layer]["scope"] = "included"
    p["items"] += [item("metadata-convention", "inferred", ["format"]),
                   item("dependency-closure", "delivery", ["appearance.delivery"]),
                   item("visual-use-limits", "use_evidence", review=True)]
    initial = run(b, o, p, decision_record="decisions.json")
    assert initial["assessment_verdict"] == "NEEDS_REVIEW"
    approve(o, initial, {"meshing-choice": "approved", "visual-use-limits": "approved"})
    r = run(b, o, p, decision_record="decisions.json", review_record="reviews.json")
    assert r["assessment_verdict"] == "ACCEPT_FOR_DECLARED_SCOPE"
    assert all(x["coverage"] == "ASSESSED" for x in r["layers"].values())


def test_proposed_inference_with_failed_advisory_measurement_is_unknown(case):
    b, o, p = case
    contract = json.loads((b / "contract.json").read_text())
    contract["checks"][1]["required"] = False
    save(b / "contract.json", contract)
    p["contract_sha256"] = sha(b / "contract.json")
    scene = b / "scene.usda"
    scene.write_text(scene.read_text().replace("rel material:binding = </World/Looks/Coating>", "rel material:binding = </World/Looks/Other>"))
    p["items"][0] = item("metadata", "explicit", ["format"])
    p["layers"]["inferred"]["scope"] = "included"
    inferred = item("inferred-binding", "inferred", ["appearance.delivery"])
    inferred["inference_authorization"]["status"] = "proposed"
    p["items"].append(inferred)
    r = run(b, o, p)
    assert r["core_verdict"] == "ACCEPT_FOR_USE"
    assert r["assessment_verdict"] == "NEEDS_REVIEW"
    assert r["items"][1]["status"] == "UNKNOWN"
    assert any("FAIL" in x["reason"] for x in r["items"][1]["observations"])


def test_missing_producer_evidence_is_not_cured_by_reviewer(case):
    b, o, p = case
    data = add_decision(b, p)
    data["decisions"][0]["evidence"].append("absent.txt")
    save(b / "decisions.json", data)
    initial = run(b, o, p, decision_record="decisions.json")
    approve(o, initial)
    assert run(b, o, p, decision_record="decisions.json", review_record="reviews.json")["assessment_verdict"] == "NEEDS_REVIEW"


def test_duplicate_json_key_is_not_silently_accepted(case):
    b, o, p = case
    add_decision(b, p)
    (b / "decisions.json").write_text('{"schema_version":"1.0","decisions":[],"decisions":[]}')
    assert run(b, o, p, decision_record="decisions.json")["assessment_verdict"] == "EVALUATION_ERROR"


def test_worker_wall_time_does_not_stale_a_review_but_measurements_do():
    from scene_acceptance.review.assessment import semantic_report
    a={'runtime':{'elapsed_ms':20},'checks':[{'id':'behavior','duration_ms':10,
       'evidence':{'pack':'physics.incline-worker','check':'displacement',
                   'observations':{'elapsed_wall_s':.2,'worker':{'trace':[[0,0,0,0,0],[.001,1,0,0,1]]}}}}]}
    b=deepcopy(a);b['checks'][0]['evidence']['observations']['elapsed_wall_s']=.4
    assert semantic_report(a)==semantic_report(b)
    assert a['checks'][0]['evidence']['observations']['elapsed_wall_s']==.2
    b['checks'][0]['evidence']['observations']['worker']['trace'][1][1]=2
    assert semantic_report(a)!=semantic_report(b)
    for r in (a,b): r['checks'][0]['evidence']['pack']='another.pack'
    b['checks'][0]['evidence']['observations']['worker']=deepcopy(a['checks'][0]['evidence']['observations']['worker'])
    assert semantic_report(a)!=semantic_report(b)


def test_real_worker_rerun_keeps_review_current(tmp_path):
    pytest.importorskip('mujoco')
    b,o,p=prepare(tmp_path)
    shutil.copy2(ROOT/'evaluation/article-checks-v1/fixtures/physics-high/scene.usda',b/'scene.usda')
    shutil.copy2(ROOT/'evaluation/article-checks-v1/fixtures/physics-high/contract.json',b/'contract.json')
    upgrade_copied_contracts(b)
    p['contract_sha256']=sha(b/'contract.json')
    p['items']=[item('behavior','explicit',['physics.incline-worker.displacement']),
                item('use-limits','use_evidence',review=True)]
    p['layers']['use_evidence']['scope']='included'
    initial=run(b,o,p,approved_packs=['physics.incline-worker'])
    assert initial['assessment_verdict']=='NEEDS_REVIEW'
    approve(o,initial,{'use-limits':'approved'})
    reviewed=run(b,o,p,approved_packs=['physics.incline-worker'],review_record='reviews.json')
    assert reviewed['assessment_verdict']=='ACCEPT_FOR_DECLARED_SCOPE',reviewed
    assert reviewed['snapshot_sha256']==initial['snapshot_sha256']


def test_nested_geometry_rerun_keeps_review_current(tmp_path):
    b,o,p=prepare(tmp_path)
    source=ROOT/'evaluation/mesh-v1/fixtures/quad_layout'
    shutil.copy2(source/'scene.usda',b/'scene.usda')
    shutil.copy2(source/'contract.json',b/'geometry.json')
    contract=json.loads((b/'contract.json').read_text())
    contract['packs']={'geometry':{'version':'1.0.0'}}
    contract['checks']=[{'id':'geometry','pack':'geometry','check':'contract','required':True,'parameters':{'contract_file':'geometry.json'}}]
    contract['allowed_dependencies']=[];contract['evidence_sources']=['geometry.json']
    save(b/'contract.json',contract);p['contract_sha256']=sha(b/'contract.json')
    p['items']=[item('geometry','explicit',['geometry']),item('use-limits','use_evidence',review=True)]
    p['layers']['use_evidence']['scope']='included'
    initial=run(b,o,p)
    assert initial['core_verdict']=='ACCEPT_FOR_USE',initial
    approve(o,initial,{'use-limits':'approved'})
    reviewed=run(b,o,p,review_record='reviews.json')
    assert reviewed['assessment_verdict']=='ACCEPT_FOR_DECLARED_SCOPE',reviewed
    assert reviewed['snapshot_sha256']==initial['snapshot_sha256']
