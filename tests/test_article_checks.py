"""Development controls: expected decisions, analytical checks and execution fault injection."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest
from scene_acceptance.engine import evaluate
from scene_acceptance.contract_upgrade import copy_replay_bundle
from tempfile import TemporaryDirectory
from scene_acceptance.model import sha
from scene_acceptance.followups import simulation
from scene_acceptance.followups.worker import simulate

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'evaluation/article-checks-v1'
FIX=EVIDENCE/'fixtures'
APPROVED=()


def run(name, contract='contract.json', approved=APPROVED):
    with TemporaryDirectory() as temporary:
        d=copy_replay_bundle(FIX/name, Path(temporary)/'bundle')
        return evaluate(d/contract,d/'scene.usda',bundle_root=d,approved_packs=approved)


@pytest.mark.parametrize('name,spec',list(json.loads((EVIDENCE/'cases.json').read_text()).items()))
def test_frozen_expected_decisions(name,spec):
    report=run(name)
    assert report['verdict']==spec['expected'],report


def test_bundled_article_packs_are_available():
    assert run('texture-valid_png')['verdict']=='ACCEPT_FOR_USE'


def test_wrong_color_passes_decode_but_differs_from_white_reference():
    from PIL import Image
    assert run('texture-wrong_color')['verdict']=='ACCEPT_FOR_USE'
    assert Image.open(FIX/'texture-wrong_color/pixel.png').getpixel((0,0))==(255,0,0)
    assert Image.open(FIX/'texture-valid_png/pixel.png').getpixel((0,0))==(255,255,255)


def test_header_identification_does_not_establish_readable_pixels():
    from PIL import Image
    with Image.open(FIX/'texture-damaged_png/pixel.png') as image:
        assert image.size==(16,16)
        with pytest.raises((OSError,SyntaxError)):
            image.verify()
    assert run('texture-damaged_png','baseline.json')['verdict']=='ACCEPT_FOR_USE'
    assert run('texture-damaged_png')['verdict']=='REJECT'


@pytest.mark.parametrize('name,baseline', [('wrapped','endpoints'),('brief_excursion','uniform'),('two_turns','contract')])
def test_finite_sampling_counterexamples(name,baseline):
    assert run('motion-'+name,baseline+'.json')['verdict']=='ACCEPT_FOR_USE'
    assert run('motion-'+name,'dense.json')['verdict']=='REJECT'


def test_origins_do_not_measure_the_pin():
    assert run('motion-wrapped','origins.json')['verdict']=='ACCEPT_FOR_USE'
    assert run('motion-wrapped')['verdict']=='REJECT'


@pytest.fixture(scope='module')
def real_result():
    path=FIX/'physics-high/scene.usda'
    identity = simulation.expected_code_identity()
    job={'input_sha256':sha(path),'dt_s':.001,'duration_s':1,**identity}
    result={**simulate(path,.001,1),'input_sha256':sha(path),'job_sha256':'correct-job','status':'complete',**identity}
    return result,job


@pytest.mark.parametrize('fault', ['wrong_input','wrong_job','clock','missing_rows','nan','wrong_scalar','wrong_position','warning','no_status','wrong_runtime'])
def test_unusable_simulation_evidence_is_rejected_by_protocol(real_result,fault):
    original,job=real_result; r=deepcopy(original)
    if fault=='wrong_input': r['input_sha256']='0'*64
    if fault=='wrong_job': r['job_sha256']='old-job'
    if fault=='clock': r['trace'][10][0]=.9
    if fault=='missing_rows': r['trace'].pop()
    if fault=='nan': r['trace'][10][1]=float('nan')
    if fault=='wrong_scalar': r['maximum_displacement_m']=0.5
    if fault=='wrong_position': r['trace'][10][1]+=1
    if fault=='warning': r['warnings']=1
    if fault=='no_status': r.pop('status')
    if fault=='wrong_runtime': r['versions']['mujoco']='different'
    with pytest.raises(ValueError): simulation.validate_result(r,job,'correct-job')


@pytest.mark.parametrize('script', ["import sys; sys.exit(7)","print('not json')","print('x'*5000000)"])
def test_actual_failed_subprocess_does_not_become_content_rejection(monkeypatch,script):
    real_popen=subprocess.Popen
    def replace_command(args,**kwargs):
        return real_popen([sys.executable,'-c',script],**kwargs)
    monkeypatch.setattr(simulation.subprocess,'Popen',replace_command)
    assert run('physics-high')['verdict']=='EVALUATION_ERROR'


@pytest.mark.parametrize('fault',['wrong_job','wrong_input','wrong_scalar','wrong_runtime'])
def test_bad_worker_result_becomes_evaluation_error(monkeypatch,real_result,fault):
    original,_=real_result
    def faulty_result(input_path,job_path,directory,timeout):
        r=deepcopy(original); r['input_sha256']=sha(input_path); r['job_sha256']=sha(job_path)
        if fault=='wrong_job': r['job_sha256']='stale'
        if fault=='wrong_input': r['input_sha256']='0'*64
        if fault=='wrong_scalar': r['maximum_displacement_m']=123
        if fault=='wrong_runtime': r['versions']['mujoco']='different'
        return r
    monkeypatch.setattr(simulation,'run_worker',faulty_result)
    assert run('physics-high')['verdict']=='EVALUATION_ERROR'


def test_frozen_inputs_still_match():
    for relative,digest in json.loads((EVIDENCE/'frozen-inputs.json').read_text()).items():
        assert sha(EVIDENCE/relative)==digest
