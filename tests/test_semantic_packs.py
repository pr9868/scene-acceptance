"""Real saved USD controls for explicit state and directed process topology."""
import json
from copy import deepcopy

import pytest
from pxr import Usd, UsdGeom, Sdf

from scene_acceptance import evaluate
from scene_acceptance.packs import default_registry


def bundle(tmp_path, pack, check, parameters, build):
    root = tmp_path / 'bundle'; root.mkdir()
    stage = Usd.Stage.CreateNew(str(root / 'scene.usda'))
    world = UsdGeom.Xform.Define(stage, '/World')
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(stage, 'Z'); UsdGeom.SetStageMetersPerUnit(stage, 1)
    stage.SetStartTimeCode(0); stage.SetEndTimeCode(10); stage.SetFramesPerSecond(1)
    build(stage)
    stage.GetRootLayer().Save()
    pin = default_registry().get(pack).describe()
    contract = dict(schema_version='2.0', id='semantic-control', intended_use='Synthetic acceptance controls',
                    profile=dict(id='semantic-control', version='1.0.0'), artifact_format='usd-local-v1',
                    allowed_dependencies=[], evidence_sources=[],
                    packs={pack: dict(version=pin['version'], sha256=pin['implementation_sha256'])},
                    checks=[dict(id='semantic', pack=pack, check=check, parameters=parameters, required=True)])
    (root / 'contract.json').write_text(json.dumps(contract))
    report = evaluate('contract.json', 'scene.usda', bundle_root=root)
    return report, next((x for x in report['checks'] if x['id'] == 'semantic'), None)


def states(stage, fault):
    prim = stage.DefinePrim('/World/Junction', 'Xform')
    for name in ('indicator', 'route'):
        attr = prim.CreateAttribute(name, Sdf.ValueTypeNames.Token)
        for t, value in [(0, 'A'), (4, 'B'), (8, 'A')]: attr.Set(value, t)
    active = prim.CreateAttribute('occupied', Sdf.ValueTypeNames.Bool)
    active.Set(fault != 'inactive', 0)
    attr = prim.GetAttribute('indicator')
    if fault == 'between': attr.Set('A', 5.001); attr.Set('B', 5.002)
    if fault == 'endpoint': attr.Set('B', 10)
    if fault == 'inactive-difference':
        active.Set(False, 0); active.Set(True, 4); attr.Set('B', 0)
    if fault == 'missing': prim.RemoveProperty('indicator')
    if fault == 'numeric':
        prim.RemoveProperty('indicator'); prim.CreateAttribute('indicator', Sdf.ValueTypeNames.Float).Set(1)


@pytest.mark.parametrize('fault,status', [('correct','PASS'), ('between','FAIL'), ('endpoint','FAIL'),
    ('inactive-difference','PASS'), ('inactive','UNKNOWN'), ('missing','UNKNOWN'), ('numeric','UNKNOWN')])
def test_state_intervals(tmp_path, fault, status):
    params = dict(observed_attribute='/World/Junction.indicator', expected_attribute='/World/Junction.route',
                  active_attribute='/World/Junction.occupied', start_s=0, end_s=10)
    report, row = bundle(tmp_path, 'behavior.state', 'agreement', params, lambda s: states(s, fault))
    assert row['status'] == status, report
    if fault == 'between':
        failures = [f for f in row['evidence']['observations']['findings'] if f['status'] == 'FAIL']
        assert len(failures) == 1
        assert failures[0]['start_s'] == 5.001 and failures[0]['end_s'] == 5.002
    if fault == 'correct':
        assert row['evidence']['observations']['checked_intervals_and_endpoints'] == 4


def process_reference():
    return dict(assets=[dict(path='/World/Tank', tag='T-101', ports=[dict(path='/World/Tank/Outlet', name='outlet', direction='out')]),
                        dict(path='/World/Pump', tag='P-101', ports=[dict(path='/World/Pump/Inlet', name='inlet', direction='in')])],
                connections=[{'from': '/World/Tank/Outlet', 'to': '/World/Pump/Inlet'}],
                tag_attribute='process:tag', port_name_attribute='process:port', direction_attribute='process:direction',
                connection_relationship='process:connectsTo', allow_extra_connections=False)


def plant(stage, fault):
    # The scene is authored independently from the contract reference below.
    for path, tag, port, name, direction in [('/World/Tank','T-101','Outlet','outlet','out'), ('/World/Pump','P-101','Inlet','inlet','in')]:
        equipment = stage.DefinePrim(path, 'Xform')
        equipment.CreateAttribute('process:tag', Sdf.ValueTypeNames.String).Set(tag)
        p = stage.DefinePrim(path + '/' + port, 'Xform')
        p.CreateAttribute('process:port', Sdf.ValueTypeNames.Token).Set(name)
        p.CreateAttribute('process:direction', Sdf.ValueTypeNames.Token).Set(direction)
    out = stage.GetPrimAtPath('/World/Tank/Outlet')
    if fault != 'missing-edge':
        out.CreateRelationship('process:connectsTo').SetTargets(['/World/Pump/Inlet'])
    if fault == 'extra':
        stage.GetPrimAtPath('/World/Pump/Inlet').CreateRelationship('process:connectsTo').SetTargets(['/World/Tank/Outlet'])
    if fault == 'wrong-direction': out.GetAttribute('process:direction').Set('in')
    if fault == 'missing-tag': stage.GetPrimAtPath('/World/Tank').RemoveProperty('process:tag')
    if fault == 'missing-equipment': stage.RemovePrim('/World/Pump')


@pytest.mark.parametrize('fault,status', [('correct','PASS'), ('missing-edge','FAIL'), ('extra','FAIL'),
    ('wrong-direction','FAIL'), ('missing-tag','UNKNOWN'), ('missing-equipment','FAIL')])
def test_process_topology(tmp_path, fault, status):
    report, row = bundle(tmp_path, 'process.connections', 'match', process_reference(), lambda s: plant(s, fault))
    assert row['status'] == status, report
    if fault == 'correct':
        observations = row['evidence']['observations']
        assert observations['equipment_count'] == 2 and observations['port_count'] == 2
        assert observations['expected_connection_count'] == observations['observed_connection_count'] == 1


def test_extra_connections_follow_explicit_policy(tmp_path):
    params = process_reference(); params['allow_extra_connections'] = True
    report, row = bundle(tmp_path, 'process.connections', 'match', params, lambda s: plant(s, 'extra'))
    assert row['status'] == 'PASS', report
    assert row['evidence']['observations']['observed_connection_count'] == 2


@pytest.mark.parametrize('fault', ['duplicate-tag', 'duplicate-port', 'bad-direction', 'relative-path'])
def test_invalid_reference_is_error_not_scene_rejection(tmp_path, fault):
    params = process_reference()
    if fault == 'duplicate-tag': params['assets'][1]['tag'] = 'T-101'
    if fault == 'duplicate-port': params['assets'][0]['ports'].append(deepcopy(params['assets'][0]['ports'][0]))
    if fault == 'bad-direction': params['assets'][0]['ports'][0]['direction'] = 'in'
    if fault == 'relative-path': params['assets'][0]['path'] = 'World/Tank'
    report, row = bundle(tmp_path, 'process.connections', 'match', params, lambda s: plant(s, 'correct'))
    assert report['verdict'] == 'EVALUATION_ERROR', report
    assert row is not None and row['status'] == 'ERROR', report



def test_known_connection_failure_survives_unrelated_missing_metadata(tmp_path):
    def build(stage):
        plant(stage, 'missing-edge')
        stage.GetPrimAtPath('/World/Tank').RemoveProperty('process:tag')
    report, row = bundle(tmp_path, 'process.connections', 'match', process_reference(), build)
    assert report['verdict'] == 'REJECT' and row['status'] == 'FAIL'
    findings = row['evidence']['observations']['findings']
    assert any(f['status'] == 'UNKNOWN' and f.get('property') == 'process:tag' for f in findings)
    assert any(f['status'] == 'FAIL' and f.get('target') == '/World/Pump/Inlet' for f in findings)
