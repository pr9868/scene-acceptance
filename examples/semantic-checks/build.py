"""Generate synthetic state/connection acceptance examples with current pack pins."""
import argparse
import json
from pathlib import Path
from pxr import Usd, UsdGeom, Sdf
from scene_acceptance.packs import default_registry


def build(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for name in ('state-correct', 'state-gap', 'state-owner-correct', 'state-owner-wrong', 'connections-correct', 'connections-missing'):
        folder = root / name; folder.mkdir()
        stage = Usd.Stage.CreateNew(str(folder / 'scene.usda'))
        stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, '/World').GetPrim())
        UsdGeom.SetStageUpAxis(stage, 'Z'); UsdGeom.SetStageMetersPerUnit(stage, 1)
        stage.SetStartTimeCode(0); stage.SetEndTimeCode(10); stage.SetFramesPerSecond(1)
        if name.startswith('state'):
            pack, check = 'behavior.state', 'agreement'
            prim = stage.DefinePrim('/World/Junction', 'Xform')
            for key in ('indicator', 'route'):
                attr = prim.CreateAttribute(key, Sdf.ValueTypeNames.Token)
                for time, value in ((0, 'A'), (4, 'B'), (8, 'A')): attr.Set(value, time)
            prim.CreateAttribute('occupied', Sdf.ValueTypeNames.Bool).Set(True)
            if name == 'state-gap':
                prim.GetAttribute('indicator').Set('A', 5.001)
                prim.GetAttribute('indicator').Set('B', 5.002)
            parameters = dict(observed_attribute='/World/Junction.indicator', expected_attribute='/World/Junction.route',
                              active_attribute='/World/Junction.occupied', start_s=0, end_s=10)
            if name.startswith('state-owner'):
                check = 'timeline'
                parameters = dict(observed_attribute='/World/Junction.indicator', start_s=0, end_s=10,
                    expected_timeline=[dict(time_s=t, value=v) for t, v in [(0, 'A'), (4, 'B'), (8, 'A')]])
                if name.endswith('wrong'):
                    for key in ('indicator', 'route'):
                        prim.GetAttribute(key).Clear()
                        prim.GetAttribute(key).Set('WRONG')
        else:
            pack, check = 'process.connections', 'match'
            for path, tag, port, port_name, direction in (
                ('/World/Tank', 'T-101', 'Outlet', 'outlet', 'out'),
                ('/World/Pump', 'P-101', 'Inlet', 'inlet', 'in'),
            ):
                prim = stage.DefinePrim(path, 'Xform')
                prim.CreateAttribute('process:tag', Sdf.ValueTypeNames.String).Set(tag)
                prim = stage.DefinePrim(path + '/' + port, 'Xform')
                prim.CreateAttribute('process:port', Sdf.ValueTypeNames.Token).Set(port_name)
                prim.CreateAttribute('process:direction', Sdf.ValueTypeNames.Token).Set(direction)
            if name == 'connections-correct':
                stage.GetPrimAtPath('/World/Tank/Outlet').CreateRelationship('process:connectsTo').SetTargets(['/World/Pump/Inlet'])
            parameters = dict(
                assets=[dict(path='/World/Tank', tag='T-101', ports=[dict(path='/World/Tank/Outlet', name='outlet', direction='out')]),
                        dict(path='/World/Pump', tag='P-101', ports=[dict(path='/World/Pump/Inlet', name='inlet', direction='in')])],
                connections=[{'from': '/World/Tank/Outlet', 'to': '/World/Pump/Inlet'}],
                tag_attribute='process:tag', port_name_attribute='process:port', direction_attribute='process:direction',
                connection_relationship='process:connectsTo', allow_extra_connections=False)
        stage.GetRootLayer().Save()
        pin = default_registry().get(pack).describe()
        contract = dict(schema_version='2.0', id=name, intended_use='Constructed software demonstration only',
                        profile=dict(id='semantic-controls', version='1.0.0'), artifact_format='usd-local-v1',
                        allowed_dependencies=[], evidence_sources=[],
                        packs={pack: dict(version=pin['version'], sha256=pin['implementation_sha256'])},
                        checks=[dict(id='agreement', pack=pack, check=check, parameters=parameters, required=True)])
        (folder / 'contract.json').write_text(json.dumps(contract, indent=2) + '\n')
        (folder / 'README.txt').write_text('Synthetic control. Expected: ' + ('ACCEPT_FOR_USE' if name.endswith('correct') else 'REJECT') + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    build(parser.parse_args().out)
