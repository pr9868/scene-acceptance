"""Own the job, bound execution, validate returned evidence, then apply the requirement."""
from pathlib import Path
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from importlib.metadata import version
from scene_acceptance.builtin_packs import obj
from scene_acceptance.model import sha, strict_json, ContractError
from scene_acceptance.packs import Pack, CheckSpec, Outcome

MAX_OUTPUT = 4 * 1024 * 1024
CODE_FILES = {
    'worker_sha256': 'worker.py',
    'adapter_sha256': 'incline_adapter.py',
    'profile_sha256': 'incline-profile.usda',
}


def expected_code_identity():
    root = Path(__file__).parent
    return {name: sha(root / filename) for name, filename in CODE_FILES.items()}


def run_worker(input_path, job_path, directory, timeout):
    """Only installed trusted worker code; candidate cannot select command or environment."""
    output, errors = directory/'result.json', directory/'stderr.txt'
    started = time.monotonic()
    with output.open('wb') as out, errors.open('wb') as err:
        with subprocess.Popen([sys.executable, '-I', '-m', 'scene_acceptance.followups.worker',
                               str(input_path), str(job_path)],
                              stdout=out, stderr=err, cwd=directory, shell=False,
                              env={k:v for k,v in os.environ.items() if not k.startswith('PYTHON')}) as process:
            while process.poll() is None:
                if time.monotonic()-started > timeout:
                    process.kill(); process.wait()
                    raise TimeoutError('Simulation worker exceeded its wall-clock deadline')
                if output.stat().st_size + errors.stat().st_size > MAX_OUTPUT:
                    process.kill(); process.wait()
                    raise RuntimeError('Worker output exceeded the 4 MiB limit')
                time.sleep(0.01)
            if process.returncode != 0:
                raise RuntimeError('Worker exited unsuccessfully: '+str(process.returncode))
    if output.stat().st_size + errors.stat().st_size > MAX_OUTPUT:
        raise RuntimeError('Worker output exceeded the 4 MiB limit')
    return strict_json(output)


def validate_result(result, job, expected_job_hash):
    current_code = expected_code_identity()
    for name, actual in current_code.items():
        if job.get(name) != actual or result.get(name) != actual:
            raise ValueError('Worker code identity is missing, stale or changed: ' + name)
    if result.get('job_sha256') != expected_job_hash or result.get('input_sha256') != job['input_sha256']:
        raise ValueError('Result does not belong to this job and input')
    if result.get('status') == 'unsupported':
        return None
    if result.get('status') != 'complete':
        raise ValueError('Worker result has no complete measurement')
    if result.get('versions') != {n:version(n) for n in ('mujoco','numpy','usd-core')}:
        raise ValueError('Worker runtime differs from the caller runtime')
    if result['dt_s'] != job['dt_s'] or result['duration_s'] != job['duration_s']:
        raise ValueError('Worker used a different simulation interval')
    trace = result['trace']
    steps = round(job['duration_s']/job['dt_s'])
    if len(trace) != steps+1 or any(len(r) != 5 for r in trace):
        raise ValueError('Incomplete trajectory')
    theta = math.radians(20)
    observed = []
    for i,row in enumerate(trace):
        if any(isinstance(v, bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in row):
            raise ValueError('Trajectory contains non-finite or non-numeric values')
        if abs(row[0]-i*job['dt_s']) > 1e-9:
            raise ValueError('Trajectory clock mismatch')
        delta = (row[1]-trace[0][1])*math.cos(theta)-(row[3]-trace[0][3])*math.sin(theta)
        if abs(delta-row[4]) > 1e-12:
            raise ValueError('Reported displacement disagrees with saved positions')
        observed.append(abs(delta))
    maximum = max(observed)
    if not math.isfinite(result['maximum_displacement_m']) or abs(maximum-result['maximum_displacement_m']) > 1e-12:
        raise ValueError('Reported maximum disagrees with the trajectory')
    if result['warnings'] != 0:
        raise ValueError('Simulator reported warnings')
    return maximum


def behavior(ctx, params):
    steps = params['duration_s']/params['dt_s']
    if steps > 10000 or not math.isclose(steps, round(steps), abs_tol=1e-9):
        raise ContractError('Duration must contain 1 to 10,000 complete simulation steps')
    if len(ctx.artifact.layers) != 1 or ctx.artifact.assets:
        return Outcome('UNKNOWN', 'The worker admits only a standalone two-box stage.')
    root = ctx.bundle.record(ctx.artifact.root)
    job = {'input_sha256': sha(root), 'dt_s': params['dt_s'], 'duration_s': params['duration_s'],
           **expected_code_identity()}
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='incline-job-') as temporary:
            directory = Path(temporary)
            copied = directory/'scene.usda'
            copied.write_bytes(root.read_bytes())
            copied.chmod(0o444)
            job_path = directory/'job.json'
            job_path.write_text(json.dumps(job, sort_keys=True, allow_nan=False))
            job_path.chmod(0o444)
            job_hash = sha(job_path)
            result = run_worker(copied, job_path, directory, params['timeout_s'])
            if sha(copied) != job['input_sha256'] or sha(job_path) != job_hash:
                raise ValueError('Copied input or job changed during execution')
            maximum = validate_result(result, job, job_hash)
    except Exception as exc:
        return Outcome('ERROR', 'No usable simulation result: '+type(exc).__name__+': '+str(exc),
                       {'job': job, 'elapsed_wall_s': time.monotonic()-started})
    evidence = {'job': job, 'job_sha256': job_hash, 'worker': result,
                'elapsed_wall_s': time.monotonic()-started,
                'coverage': 'Fixed two-box CPU model; assumed friction; no measured physical validation.'}
    if maximum is None:
        return Outcome('UNKNOWN', 'Scene is outside the bounded incline adapter.', evidence)
    if params['require_measured_parameters']:
        return Outcome('UNKNOWN', 'No measured friction evidence is supplied by this experiment.', evidence)
    evidence['maximum_recomputed_displacement_m'] = maximum
    return Outcome('PASS' if maximum <= params['maximum_displacement_m'] else 'FAIL',
                   'Trajectory belongs to this job; displacement compared with the requirement.', evidence)


def simulation_pack():
    root = Path(__file__).parent
    return Pack('physics.incline-worker', '0.2.0', 'Bounded CPU incline experiment with job identity', {
        'displacement': CheckSpec(behavior, obj({
            'dt_s': {'type':'number','minimum':0.0001,'maximum':0.01},
            'duration_s': {'type':'number','minimum':0.01,'maximum':2},
            'timeout_s': {'type':'number','minimum':0.001,'maximum':60},
            'maximum_displacement_m': {'type':'number','minimum':0},
            'require_measured_parameters': {'type':'boolean'},
        }), 'Run the fixed incline model and compare displacement', 'A one-body CPU experiment and its execution record',
        ('Fixed fixture profile; no general USD physics importer or hostile-code sandbox',
         'Assumed friction does not establish real-world task validity'))
    }, tuple(str(root/n) for n in ('simulation.py','worker.py','incline_adapter.py','incline-profile.usda')),
       ('mujoco','numpy','usd-core'))
