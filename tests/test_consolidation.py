"""Preserved adversarial artifacts and integration controls for the consolidated package."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import shutil

import pytest
from scene_acceptance import evaluate
from scene_acceptance.contract_upgrade import propose_upgrade
from scene_acceptance.cli import main
from scene_acceptance.model import sha
from scene_acceptance.supplemental import four_job_pack
from scene_acceptance.review import assess
from scene_acceptance.review.schemas import LAYERS
from scene_acceptance.review.__main__ import write_report

ROOT = Path(__file__).resolve().parents[1] / 'evaluation/consolidation-v1'
CASES = json.loads((ROOT / 'cases.json').read_text())


def save(p, obj): p.write_text(json.dumps(obj, indent=2) + '\n')


def prepare(tmp_path, name):
    bundle = tmp_path / 'bundle'
    shutil.copytree(ROOT / 'fixtures' / name, bundle)
    c = json.loads((bundle / 'contract.json').read_text())
    del c['packs']['fresh.brief']
    p = four_job_pack()
    c['packs'][p.id] = {'version': p.version, 'sha256': p.describe()['implementation_sha256']}
    for check in c['checks']:
        if check['pack'] == 'fresh.brief': check['pack'] = p.id
    c, upgrades = propose_upgrade(c)
    save(bundle / 'contract-upgrades.json', upgrades)
    save(bundle / 'contract.json', c)
    return bundle, c


def run(bundle, job):
    return evaluate('contract.json', 'scene.usda', bundle_root=bundle,
                    baseline_path='baseline.usda' if job == 'tray-translated' else None,
                    expected_contract_sha256=sha(bundle / 'contract.json'))


def statuses(report): return {c['id']: c['status'] for c in report['checks']}


def test_frozen_inputs():
    assert {str(p.relative_to(ROOT)): sha(p) for p in (ROOT/'fixtures').rglob('*') if p.is_file()} == json.loads((ROOT/'frozen-inputs.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_preserved_supplemental_controls(tmp_path, case):
    pytest.importorskip('PIL'); pytest.importorskip('numpy')
    if case['job'].startswith('physics'):
        pytest.importorskip('mujoco'); pytest.importorskip('usd_validation_nvidia')
    bundle, _ = prepare(tmp_path, case['id'])
    result = run(bundle, case['job'])
    if case['expected'] == 'NOT_ACCEPTED': assert result['verdict'] != 'ACCEPT_FOR_USE', result
    else: assert result['verdict'] == case['expected'], result
    if case['id'] == 'panel-wrong-readable-texture':
        assert statuses(result)['texture.decode'] == 'PASS'
        assert statuses(result)['brief.panel.pixels'] == 'FAIL'
    if case['id'] == 'motion-valid-variable-speed':
        assert statuses(result)['brief.motion.cycle'] == 'PASS'
        assert statuses(result)['brief.motion.trajectory'] == 'FAIL'
    for row in result['coverage']['audit']['rows']:
        if row['pack'] == 'brief.four-job' and row['contract_status'] != 'ERROR':
            counts = row['counts']
            assert counts is not None, row
            assert counts['candidate_count'] == sum(counts[x+'_count'] for x in ('pass','fail','warning','unknown','error','skipped'))


@pytest.mark.parametrize('missing', ['textures/label.png', 'reference.usda'])
def test_unavailable_evidence_does_not_suppress_independent_checks(tmp_path, missing):
    b, _ = prepare(tmp_path, 'original-panel-png')
    (b / missing).unlink()
    r = run(b, 'panel-png'); s = statuses(r)
    assert s['brief.panel.dimensions'] == s['brief.panel.uv'] == s['brief.panel.shader'] == 'PASS'
    assert s['brief.panel.pixels' if missing.endswith('png') else 'brief.panel.equivalence'] == 'UNKNOWN'


def test_wrong_preset_is_configuration_error(tmp_path):
    b, c = prepare(tmp_path, 'original-panel-png')
    c['checks'][-1]['parameters']['job'] = 'motion'
    save(b / 'contract.json', c)
    assert run(b, 'panel-png')['verdict'] == 'EVALUATION_ERROR'


def test_pixel_budget_precedes_decode(tmp_path, monkeypatch):
    from PIL import Image
    b, c = prepare(tmp_path, 'original-panel-png')
    c['checks'] = [x for x in c['checks'] if x['id'] == 'brief.panel.pixels']
    c['packs'] = {'brief.four-job': c['packs']['brief.four-job']}
    save(b / 'contract.json', c)
    Image.new('RGB', (257, 256)).save(b / 'textures/label.png')
    loaded = []
    def forbidden(*args, **kwargs):
        loaded.append(True)
        raise AssertionError('Oversized image must not decode')
    monkeypatch.setattr(Image.Image, 'load', forbidden)
    r = run(b, 'panel-png')
    assert statuses(r)['brief.panel.pixels'] == 'UNKNOWN', r
    assert not loaded


def review_plan(tmp_path, b, c):
    owner = tmp_path/'owner'; owner.mkdir()
    p = {'schema_version':'1.0', 'id':'integration-control', 'intended_use':'Finite sampled motion; continuous correctness unresolved',
         'contract':'contract.json', 'contract_sha256':sha(b/'contract.json'), 'candidate':'scene.usda', 'baseline':None,
         'mapping_review':{'status':'reviewed','reviewer':'Synthetic test author','reason':'Software control only'},
         'layers':{n:{'scope':'included' if n=='explicit' else 'excluded','reason':'Narrow test scope'} for n in LAYERS},
         'items':[{'id':'continuous-motion','layer':'explicit','statement':'Correct attachments at every intended time',
                   'basis':'Declared broad use','required':True,'check_ids':['brief.motion.connections'],
                   'review_required':True,'decision_id':None,'inference_authorization':None}]}
    save(owner/'plan.json',p)
    return owner, p


def test_combined_cli_and_traceable_report(tmp_path):
    b, c = prepare(tmp_path, 'original-motion'); owner, p = review_plan(tmp_path,b,c)
    out = tmp_path/'report'
    code = main(['--review-plan','plan.json','--review-root',str(owner),'--plan-sha256',sha(owner/'plan.json'),
                 '--bundle-root',str(b),'--out',str(out)])
    assert code == 3
    r = json.loads((out/'assessment.json').read_text())
    assert r['core_verdict'] == 'ACCEPT_FOR_USE' and r['assessment_verdict'] == 'NEEDS_REVIEW'
    assert r['coverage_summary']['required'] == {'UNKNOWN':1}
    assert r['layers']['explicit']['coverage'] == 'ASSESSED_WITH_GAPS'
    assert json.loads((out/'artifact/result.json').read_text()) == r['core_report']
    html = (out/'report.html').read_text()
    assert 'What the harness checked' in html and 'Correct attachments at every intended time' in html
    assert 'href="artifact/subjects.csv"' in html
    for name, digest in json.loads((out/'manifest.json').read_text())['files'].items():
        assert sha(out/name) == digest
    rows = list(csv.DictReader((out/'obligations.csv').open()))
    assert rows[0]['evidence_pointer'] == '/items/0'


@pytest.mark.parametrize('kind', ['missing-hash','override','nested-output','orphan-review-arg'])
def test_cli_rejects_ambiguous_or_unsafe_inputs(tmp_path, kind):
    b,c=prepare(tmp_path,'original-motion');owner,p=review_plan(tmp_path,b,c)
    args=['--review-plan','plan.json','--review-root',str(owner),'--plan-sha256',sha(owner/'plan.json'),
          '--bundle-root',str(b),'--out',str(tmp_path/'report')]
    if kind=='missing-hash': del args[4:6]
    elif kind=='override': args += ['--candidate','scene.usda']
    elif kind=='nested-output': args[-1]=str(owner/'report')
    else: args=['--contract','contract.json','--candidate','scene.usda','--bundle-root',str(b),'--reviews','review.json','--out',str(tmp_path/'report')]
    with pytest.raises(SystemExit) as e: main(args)
    assert e.value.code == 4
