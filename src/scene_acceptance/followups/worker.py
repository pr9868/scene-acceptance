"""Trusted fixed CPU worker. This is process separation, not a hostile-code sandbox."""
from pathlib import Path
import hashlib
import json
import math
import sys
from importlib.metadata import version
import mujoco
import numpy as np
from pxr import Usd
from .incline_adapter import read_fixture, model_xml
from . import incline_adapter


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_identity():
    """Identify the installed files this process actually uses."""
    return {
        'worker_sha256': digest(Path(__file__)),
        'adapter_sha256': digest(Path(incline_adapter.__file__)),
        'profile_sha256': digest(Path(__file__).with_name('incline-profile.usda')),
    }


def verify_code_identity(job):
    actual = code_identity()
    if any(job.get(name) != digest_value for name, digest_value in actual.items()):
        raise RuntimeError('Installed worker, adapter or profile identity differs from the job')
    return actual


def read_bounded(path):
    stage = Usd.Stage.Open(str(path))
    template = Usd.Stage.Open(str(Path(__file__).with_name('incline-profile.usda')))
    if not stage or len(stage.GetUsedLayers()) != 2:  # root plus anonymous session layer
        raise ValueError('Only a standalone two-box stage is admitted')
    if set(str(p.GetPath()) for p in stage.Traverse()) != set(str(p.GetPath()) for p in template.Traverse()):
        raise ValueError('Only the fixed two-box profile is admitted')
    variable = {'/World/Block.physics:mass', '/World/Contact.physics:staticFriction',
                '/World/Contact.physics:dynamicFriction'}
    for p in stage.Traverse():
        ref = template.GetPrimAtPath(p.GetPath())
        if p.GetTypeName() != ref.GetTypeName() or p.GetAppliedSchemas() != ref.GetAppliedSchemas():
            raise ValueError('Unsupported type or applied schema')
        if p.GetAuthoredPropertyNames() != ref.GetAuthoredPropertyNames():
            raise ValueError('Unsupported or missing authored property')
        for a in p.GetAttributes():
            if a.GetNumTimeSamples() or a.GetConnections():
                raise ValueError('Animated or connected attributes are outside the adapter')
            if str(a.GetPath()) not in variable and a.Get() != ref.GetAttribute(a.GetName()).Get():
                raise ValueError('Changed fixture property outside the adapter profile: '+str(a.GetPath()))
        for rel in p.GetRelationships():
            if rel.GetTargets() != ref.GetRelationship(rel.GetName()).GetTargets():
                raise ValueError('Unsupported relationship')
    f = read_fixture(path)
    if not (math.isfinite(f['mass']) and 0 < f['mass'] <= 100 and
            math.isfinite(f['mu']) and 0 <= f['mu'] <= 2):
        raise ValueError('Mass or equal friction values are outside the admitted range')
    return f


def simulate(path, dt, duration):
    f = read_bounded(path)
    xml = model_xml(f, dt)
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    origin = d.qpos[:3].copy()
    theta = math.radians(f['ramp']['angle_deg'])
    axis = np.array([math.cos(theta), 0, -math.sin(theta)])
    steps = round(duration/dt)
    if not (1 <= steps <= 10000) or not math.isclose(steps*dt, duration, abs_tol=1e-12):
        raise ValueError('Duration must be an exact bounded number of steps')
    trace = []
    for i in range(steps+1):
        trace.append([float(d.time), *map(float, d.qpos[:3]), float(np.dot(d.qpos[:3]-origin, axis))])
        if i < steps:
            mujoco.mj_step(m, d)
            mujoco.mj_forward(m, d)
    if not np.isfinite(np.array(trace)).all():
        raise RuntimeError('Simulation generated non-finite observations')
    return {'fixture': f, 'dt_s': dt, 'duration_s': duration, 'trace': trace,
            'maximum_displacement_m': max(abs(row[4]) for row in trace),
            'warnings': sum(int(w.number) for w in d.warning),
            'model_xml': xml, 'versions': {n: version(n) for n in ('mujoco','numpy','usd-core')}}


def main():
    path, job_path = map(Path, sys.argv[1:])
    job = json.loads(job_path.read_text())
    identities = verify_code_identity(job)
    if digest(path) != job['input_sha256']:
        raise RuntimeError('Worker input identity mismatch')
    try:
        result = {'status': 'complete', **simulate(path, job['dt_s'], job['duration_s'])}
    except (ValueError, AssertionError) as exc:
        result = {'status': 'unsupported', 'reason': str(exc)}
    if verify_code_identity(job) != identities:
        raise RuntimeError('Installed worker code changed during execution')
    result.update(input_sha256=digest(path), job_sha256=digest(job_path), **identities)
    print(json.dumps(result, allow_nan=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
