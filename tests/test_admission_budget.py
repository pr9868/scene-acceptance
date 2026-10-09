"""Caller budgets admit larger deliveries without weakening coverage or path rules."""
import json
import shutil
from pathlib import Path

import pytest
from pxr import Sdf, Usd, UsdGeom

from scene_acceptance import evaluate
from scene_acceptance.cli import main

ROOT = Path(__file__).resolve().parents[1]


def contract():
    return {
        'schema_version': '2.0', 'id': 'budget-test', 'intended_use': 'Structural test',
        'profile': {'id': 'budget-test', 'version': '1.0.0'},
        'artifact_format': 'usd-local-v1', 'allowed_dependencies': [], 'evidence_sources': [],
        'packs': {'openusd': {'version': '1.1.0'}},
        'checks': [{'id': 'composition', 'pack': 'openusd', 'check': 'validators',
                    'required': True, 'parameters': {
                        'validators': ['usdValidation:CompositionErrorTest'],
                        'warnings_as_failures': False}}],
    }


def make_bundle(tmp_path, layers=0, assets=0):
    d = tmp_path / 'bundle'
    d.mkdir()
    s = Usd.Stage.CreateNew(str(d / 'scene.usda'))
    p = s.DefinePrim('/World', 'Xform')
    s.SetDefaultPrim(p)
    UsdGeom.SetStageMetersPerUnit(s, 1)
    UsdGeom.SetStageUpAxis(s, UsdGeom.Tokens.y)
    names = []
    for i in range(layers):
        name = f'layer-{i}.usda'
        (d / name).write_text('#usda 1.0\n')
        names.append(name)
    s.GetRootLayer().subLayerPaths = names
    asset_names = []
    for i in range(assets):
        name = f'asset-{i}.bin'
        (d / name).write_bytes(b'local test asset')
        asset_names.append(name)
    if asset_names:
        p.CreateAttribute('test:files', Sdf.ValueTypeNames.AssetArray).Set(
            [Sdf.AssetPath(n) for n in asset_names])
    s.GetRootLayer().Save()
    c = contract()
    c['allowed_dependencies'] = names + asset_names
    (d / 'contract.json').write_text(json.dumps(c))
    return d


def run(d, **kwargs):
    return evaluate('contract.json', 'scene.usda', bundle_root=d, **kwargs)


@pytest.mark.parametrize('layers,assets', [(63, 0), (0, 63), (31, 32)])
def test_exact_default_budget_accepts_root_and_63_dependencies(tmp_path, layers, assets):
    d = make_bundle(tmp_path, layers, assets)
    r = run(d)
    assert r['verdict'] == 'ACCEPT_FOR_USE', r
    assert len(r['identity']['candidate']['files']) == 64
    assert r['runtime']['admission_limits']['max_dependency_files'] == 64


@pytest.mark.parametrize('layers,assets', [(64, 0), (0, 64), (32, 32)])
def test_limit_is_unknown_before_composition_then_explicit_budget_admits(
    tmp_path, monkeypatch, layers, assets
):
    d = make_bundle(tmp_path, layers, assets)
    original_open = Usd.Stage.Open
    def forbidden(*args, **kwargs):
        pytest.fail('Over-budget stage must not compose')
    monkeypatch.setattr(Usd.Stage, 'Open', forbidden)
    r = run(d)
    assert r['verdict'] == 'INSUFFICIENT_EVIDENCE' and not r['complete']
    gap = r['checks'][0]
    assert gap['id'] == 'core.coverage' and gap['status'] == 'UNKNOWN'
    assert gap['evidence']['limit'] == 64
    assert gap['evidence']['observed_at_least'] == 65
    assert r['checks'][1]['status'] == 'UNKNOWN'
    monkeypatch.setattr(Usd.Stage, 'Open', original_open)
    larger = run(d, max_dependency_files=128)
    assert larger['verdict'] == 'ACCEPT_FOR_USE', larger
    assert len(larger['identity']['candidate']['files']) == 65
    assert larger['runtime']['admission_limits']['max_dependency_files'] == 128


@pytest.mark.parametrize('value', [0, -1, 1025, True, 64.0, '128', None])
def test_invalid_caller_budget_cannot_accept(tmp_path, value):
    r = run(make_bundle(tmp_path), max_dependency_files=value)
    assert r['verdict'] == 'EVALUATION_ERROR'


def test_shared_dependency_counts_once(tmp_path):
    d = make_bundle(tmp_path, layers=2)
    (d / 'shared.usda').write_text('#usda 1.0\n')
    for n in ['layer-0.usda', 'layer-1.usda']:
        layer = Sdf.Layer.FindOrOpen(str(d / n))
        layer.subLayerPaths = ['shared.usda']
        layer.Save()
    c = json.loads((d / 'contract.json').read_text())
    c['allowed_dependencies'].append('shared.usda')
    (d / 'contract.json').write_text(json.dumps(c))
    r = run(d, max_dependency_files=4)
    assert r['verdict'] == 'ACCEPT_FOR_USE', r
    assert len(r['identity']['candidate']['files']) == 4


@pytest.mark.parametrize('asset', ['../outside.bin', 'https://example.invalid/a.bin', 'tile.<UVTILE>.png'])
def test_larger_budget_does_not_relax_paths(tmp_path, asset):
    d = make_bundle(tmp_path)
    s = Usd.Stage.Open(str(d / 'scene.usda'))
    s.GetPrimAtPath('/World').CreateAttribute('test:file', Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(asset))
    s.GetRootLayer().Save()
    r = run(d, max_dependency_files=256)
    assert r['verdict'] == 'EVALUATION_ERROR', r


def test_larger_budget_does_not_accept_undeclared_dependency(tmp_path):
    d = make_bundle(tmp_path, assets=1)
    c = json.loads((d / 'contract.json').read_text())
    c['allowed_dependencies'] = []
    (d / 'contract.json').write_text(json.dumps(c))
    r = run(d, max_dependency_files=256)
    assert r['verdict'] == 'INSUFFICIENT_EVIDENCE', r
    assert 'Undeclared dependency' in r['checks'][0]['reason']


def test_contract_cannot_raise_caller_budget(tmp_path):
    d = make_bundle(tmp_path, layers=64)
    c = json.loads((d / 'contract.json').read_text())
    c['max_dependency_files'] = 256
    (d / 'contract.json').write_text(json.dumps(c))
    assert run(d)['verdict'] == 'EVALUATION_ERROR'


def test_v1_budget_and_geometry_adapter_propagation(tmp_path):
    d = tmp_path / 'legacy'
    shutil.copytree(ROOT / 'evaluation/mesh-v1/fixtures/translated_mesh', d)
    c = json.loads((d / 'contract.json').read_text())
    names = [f'empty-{i}.usda' for i in range(64)]
    for n in names:
        (d / n).write_text('#usda 1.0\n')
    layer = Sdf.Layer.FindOrOpen(str(d / 'scene.usda'))
    layer.subLayerPaths = names
    layer.Save()
    c['allowed_dependencies'].extend(names)
    (d / 'contract.json').write_text(json.dumps(c))
    args = {'baseline_path': 'baseline.usda'}
    assert run(d, **args)['verdict'] == 'INSUFFICIENT_EVIDENCE'
    assert run(d, max_dependency_files=128, **args)['verdict'] == 'ACCEPT_FOR_USE'
    (d / 'geometry-contract.json').write_text(json.dumps(c))
    outer = contract()
    outer['allowed_dependencies'] = names
    outer['evidence_sources'] = ['geometry-contract.json']
    outer['packs'] = {'geometry': {'version': '1.0.0'}}
    outer['checks'] = [{'id': 'geometry', 'pack': 'geometry', 'check': 'contract',
                        'required': True, 'parameters': {'contract_file': 'geometry-contract.json'}}]
    (d / 'contract.json').write_text(json.dumps(outer))
    assert run(d, max_dependency_files=128, **args)['verdict'] == 'ACCEPT_FOR_USE'


def test_cli_reports_chosen_limit_and_coverage_exit(tmp_path):
    d = make_bundle(tmp_path, layers=64)
    args = ['--contract', 'contract.json', '--candidate', 'scene.usda', '--bundle-root', str(d)]
    assert main(args + ['--out', str(tmp_path / 'default')]) == 3
    assert main(args + ['--max-dependency-files', '256', '--out', str(tmp_path / 'larger')]) == 0
    r = json.loads((tmp_path / 'larger/result.json').read_text())
    assert r['runtime']['admission_limits']['max_dependency_files'] == 256
    with pytest.raises(SystemExit) as exc:
        main(args + ['--max-dependency-files', '0', '--out', str(tmp_path / 'invalid')])
    assert exc.value.code == 4
    assert not (tmp_path / 'invalid').exists()
