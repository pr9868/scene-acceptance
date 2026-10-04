"""MDL identity and resolver gaps must not disguise missing delivered files."""
from pathlib import Path

import pytest
from pxr import Sdf, Usd, UsdGeom, UsdShade

from scene_acceptance.artifact import EvidenceBundle, UsdArtifact
from scene_acceptance.builtin_packs import materials, native
from scene_acceptance.pack_engine import Context
from scene_acceptance.profiles import discover_artifact, evaluate_baseline
from scene_acceptance.scene_audit import files


def mdl_scene(root, *, bundled=False, texture=False, same_file_as_texture=False):
    stage = Usd.Stage.CreateNew(str(root / 'scene.usda'))
    world = UsdGeom.Xform.Define(stage, '/World')
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    cube = UsdGeom.Cube.Define(stage, '/World/Cube')
    material = UsdShade.Material.Define(stage, '/World/Material')
    shader = UsdShade.Shader.Define(stage, '/World/Material/Shader')
    shader.SetSourceAsset(Sdf.AssetPath('OmniPBR.mdl'), 'mdl')
    shader.SetSourceAssetSubIdentifier('OmniPBR', 'mdl')
    material.CreateSurfaceOutput('mdl').ConnectToSource(shader.ConnectableAPI(), 'out')
    UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(material)
    if texture:
        shader.CreateInput('diffuse_texture', Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath('OmniPBR.mdl' if same_file_as_texture else 'missing.png'))
    stage.GetRootLayer().Save()
    if bundled:
        # Only local file existence and shader identity are under test here.
        # This is deliberately not evidence of valid MDL compilation.
        (root / 'OmniPBR.mdl').write_text('// local dependency placeholder\n')
    allowed = ['OmniPBR.mdl'] + (['missing.png'] if texture and not same_file_as_texture else [])
    bundle = EvidenceBundle(root, allowed)
    return Context(bundle, UsdArtifact(bundle, 'scene.usda'), None, ())


def dependency_check(ctx):
    return native(ctx, {'validators': ['usdUtilsValidators:MissingReferenceValidator'],
                        'warnings_as_failures': False})


def surface_check(ctx, expected='OmniPBR'):
    return materials(ctx, {'bindings': {'/World/Cube': '/World/Material'},
                           'purpose': 'allPurpose', 'render_context': 'mdl',
                           'surface_shader_id': expected})


def test_missing_runtime_library_remains_unknown_with_upstream_issue(tmp_path):
    ctx = mdl_scene(tmp_path)
    result = dependency_check(ctx)
    assert result.status == 'UNKNOWN'
    issue = result.evidence['issues'][0]
    assert issue['severity'] == 'Error'
    assert issue['assessment'] == 'UNKNOWN'
    assert files(ctx, {}).status == 'UNKNOWN'
    assert surface_check(ctx).status == 'UNKNOWN'
    identity = surface_check(ctx).evidence['findings'][1]
    assert identity['status'] == 'PASS'
    assert identity['observed'] == 'OmniPBR'
    assert identity['source_asset'] == 'OmniPBR.mdl'


def test_bundled_library_checks_declared_subidentifier(tmp_path):
    ctx = mdl_scene(tmp_path, bundled=True)
    assert surface_check(ctx).status == 'PASS'
    assert surface_check(ctx, 'OtherShader').status == 'FAIL'
    assert dependency_check(ctx).status == 'PASS'
    assert files(ctx, {}).status == 'PASS'


def test_missing_texture_still_rejects_alongside_runtime_library(tmp_path):
    ctx = mdl_scene(tmp_path, texture=True)
    assert files(ctx, {}).status == 'FAIL'
    assert dependency_check(ctx).status == 'FAIL'
    assert surface_check(ctx).status == 'FAIL'
    assert {i.get('assessment', 'FAIL') for i in dependency_check(ctx).evidence['issues']} == {'UNKNOWN', 'FAIL'}


def test_shared_asset_cannot_hide_ordinary_missing_file(tmp_path):
    ctx = mdl_scene(tmp_path, texture=True, same_file_as_texture=True)
    assert not ctx.artifact.runtime_assets
    assert files(ctx, {}).status == 'FAIL'
    assert dependency_check(ctx).status == 'FAIL'


def test_explicit_local_library_delivery_requirement_can_fail(tmp_path):
    ctx = mdl_scene(tmp_path)
    assert files(ctx, {'runtime_libraries': 'require_local'}).status == 'FAIL'


def test_appearing_runtime_dependency_invalidates_snapshot(tmp_path):
    ctx = mdl_scene(tmp_path)
    assert ctx.bundle.unchanged()
    (tmp_path / 'OmniPBR.mdl').write_text('// appeared after admission')
    assert not ctx.bundle.unchanged()


def test_default_report_separates_mdl_support_gap_from_invalid_delivery(tmp_path):
    pytest.importorskip('usd_validation_nvidia')
    mdl_scene(tmp_path)
    report = evaluate_baseline(tmp_path, 'scene.usda')
    assert report['verdict'] == 'INSUFFICIENT_EVIDENCE', report
    checks = {c['id']: c['status'] for c in report['checks']}
    assert checks['usd.12'] == checks['audit.files'] == 'UNKNOWN'
    assert 'FAIL' not in checks.values()


def discovered(root):
    artifact = discover_artifact(root, 'scene.usda')
    return Context(artifact.bundle, artifact, None, ())


def test_layered_over_uses_composed_shader_metadata(tmp_path):
    base = tmp_path/'base'
    base.mkdir()
    mdl_scene(base)
    stage = Usd.Stage.CreateNew(str(tmp_path/'scene.usda'))
    stage.GetRootLayer().subLayerPaths = ['base/scene.usda']
    shader = stage.OverridePrim('/World/Material/Shader')
    # Neither Shader type nor implementationSource is authored in this layer.
    shader.CreateAttribute('info:mdl:sourceAsset', Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath('Override.mdl'))
    stage.GetRootLayer().Save()
    assert stage.GetRootLayer().GetPrimAtPath('/World/Material/Shader').typeName == ''
    ctx = discovered(tmp_path)
    assert {p.name for p in ctx.artifact.runtime_assets} == {'OmniPBR.mdl', 'Override.mdl'}
    assert files(ctx, {}).status == dependency_check(ctx).status == 'UNKNOWN'


def test_sublayer_relative_mdl_path_matches_computed_upstream_identifier(tmp_path):
    child = tmp_path/'sub'
    child.mkdir()
    original = mdl_scene(child)
    shader = UsdShade.Shader(original.artifact.stage.GetPrimAtPath('/World/Material/Shader'))
    shader.SetSourceAsset(Sdf.AssetPath('../Library.mdl'), 'mdl')
    original.artifact.stage.GetRootLayer().Save()
    stage = Usd.Stage.CreateNew(str(tmp_path/'scene.usda'))
    stage.GetRootLayer().subLayerPaths = ['sub/scene.usda']
    stage.GetRootLayer().Save()
    ctx = discovered(tmp_path)
    result = dependency_check(ctx)
    assert files(ctx, {}).status == result.status == 'UNKNOWN'
    assert str(tmp_path/'Library.mdl') in result.evidence['issues'][0]['message']
    assert result.evidence['issues'][0]['severity'] == 'Error'


def test_reference_remapping_preserves_authored_shader_identity(tmp_path):
    base = tmp_path/'base'
    base.mkdir()
    mdl_scene(base)
    stage = Usd.Stage.CreateNew(str(tmp_path/'scene.usda'))
    root = UsdGeom.Xform.Define(stage, '/Remapped')
    root.GetPrim().GetReferences().AddReference('base/scene.usda')
    stage.GetRootLayer().Save()
    ctx = discovered(tmp_path)
    assert ctx.artifact.stage.GetPrimAtPath('/Remapped/Material/Shader')
    assert files(ctx, {}).status == dependency_check(ctx).status == 'UNKNOWN'


@pytest.mark.parametrize('ordinary_in_root', [False, True])
def test_cross_layer_shared_target_never_defers_ordinary_missing_file(tmp_path, ordinary_in_root):
    sub = tmp_path/'sub'
    sub.mkdir()
    stage = Usd.Stage.CreateNew(str(tmp_path/'scene.usda'))
    child = Usd.Stage.CreateNew(str(sub/'child.usda'))
    library_stage, texture_stage = (child, stage) if ordinary_in_root else (stage, child)
    shader = UsdShade.Shader.Define(library_stage, '/World/Library')
    shader.SetSourceAsset(Sdf.AssetPath('../shared.mdl' if ordinary_in_root else 'shared.mdl'), 'mdl')
    shader.SetSourceAssetSubIdentifier('OmniPBR', 'mdl')
    texture = UsdShade.Shader.Define(texture_stage, '/World/Texture')
    texture.CreateIdAttr('UsdUVTexture')
    texture.CreateInput('file', Sdf.ValueTypeNames.Asset).Set(
        Sdf.AssetPath('shared.mdl' if ordinary_in_root else '../shared.mdl'))
    child.GetRootLayer().Save()
    stage.GetRootLayer().subLayerPaths = ['sub/child.usda']
    stage.GetRootLayer().Save()
    ctx = discovered(tmp_path)
    assert not ctx.artifact.runtime_assets
    assert files(ctx, {}).status == dependency_check(ctx).status == 'FAIL'


def test_same_identifier_in_different_layers_cannot_disguise_missing_texture(tmp_path):
    sub = tmp_path/'sub'
    sub.mkdir()
    mdl_scene(tmp_path)
    child = Usd.Stage.CreateNew(str(sub/'child.usda'))
    texture = UsdShade.Shader.Define(child, '/World/Texture')
    texture.CreateIdAttr('UsdUVTexture')
    texture.CreateInput('file', Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath('OmniPBR.mdl'))
    child.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(tmp_path/'scene.usda'))
    stage.GetRootLayer().subLayerPaths = ['sub/child.usda']
    stage.GetRootLayer().Save()
    ctx = discovered(tmp_path)
    assert len(ctx.artifact.runtime_assets) == 1
    assert files(ctx, {}).status == dependency_check(ctx).status == 'FAIL'


def test_mdl_named_attribute_on_nonshader_is_an_ordinary_dependency(tmp_path):
    stage = Usd.Stage.CreateNew(str(tmp_path/'scene.usda'))
    prim = UsdGeom.Xform.Define(stage, '/World').GetPrim()
    prim.CreateAttribute('info:implementationSource', Sdf.ValueTypeNames.Token).Set('sourceAsset')
    prim.CreateAttribute('info:mdl:sourceAsset', Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath('OmniPBR.mdl'))
    stage.GetRootLayer().Save()
    ctx = discovered(tmp_path)
    assert not ctx.artifact.runtime_assets
    assert files(ctx, {}).status == dependency_check(ctx).status == 'FAIL'
