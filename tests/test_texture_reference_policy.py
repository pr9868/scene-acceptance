"""Connected-input, visual-brief and declared pixel-policy regression controls."""

from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from PIL import Image
from pxr import Sdf, Usd, UsdGeom, UsdShade
from scene_acceptance.brief_measurements import image_pixels, read_image, brief_measurement_pack
from scene_acceptance.briefs import load_brief
from scene_acceptance.followups.packs import decode
from scene_acceptance.image_evidence import inspect_visual_reference
from scene_acceptance.model import BoundaryError, ContractError, MissingEvidence, sha
from scene_acceptance.preparation import _read_raw
from scene_acceptance.profiles import discover_artifact
from jsonschema import Draft202012Validator


ATTRIBUTE = '/World/Material/Texture.inputs:file'
PIXELS = dict(asset_attribute=ATTRIBUTE, reference_image='reference.png', max_channel_error=0)
DECODE = dict(asset_attribute=ATTRIBUTE, max_pixels=16000000, max_bytes=33554432)


def context(tmp_path, *, connected=False, fault=None, actual=None):
    stage = Usd.Stage.CreateNew(str(tmp_path/'scene.usda'))
    world = UsdGeom.Xform.Define(stage, '/World')
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(stage, 'Y')
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    material = UsdShade.Material.Define(stage, '/World/Material')
    texture = UsdShade.Shader.Define(stage, '/World/Material/Texture')
    texture.CreateIdAttr('UsdUVTexture')
    selected = texture.CreateInput('file', Sdf.ValueTypeNames.Asset)
    source = material.CreateInput('file', Sdf.ValueTypeNames.Asset)
    source.Set(Sdf.AssetPath('actual.png'))
    if connected:
        selected.ConnectToSource(source)
    else:
        selected.Set(Sdf.AssetPath('actual.png'))
    if fault == 'cycle':
        source.ConnectToSource(selected)
    elif fault == 'multiple':
        other = material.CreateInput('other', Sdf.ValueTypeNames.Asset)
        other.Set(Sdf.AssetPath('actual.png'))
        selected.GetAttr().SetConnections([source.GetAttr().GetPath(), other.GetAttr().GetPath()])
    elif fault == 'missing':
        selected.GetAttr().SetConnections(['/World/Material.inputs:missing'])
    elif fault == 'animated':
        source.Set(Sdf.AssetPath('actual.png'), 1)
    elif fault == 'computed':
        output = texture.CreateOutput('computed', Sdf.ValueTypeNames.Asset)
        output.Set(Sdf.AssetPath('actual.png'))
        selected.GetAttr().SetConnections([output.GetAttr().GetPath()])
    stage.GetRootLayer().Save()
    (actual or Image.new('RGB', (4, 4))).save(tmp_path/'actual.png')
    Image.new('RGB', (4, 4)).save(tmp_path/'reference.png')
    artifact = discover_artifact(tmp_path, 'scene.usda')
    return SimpleNamespace(artifact=artifact, bundle=artifact.bundle,
                           sources=['reference.png', 'mask.png'])


@pytest.mark.parametrize('connected', [False, True])
def test_static_direct_and_connected_asset_inputs_resolve(tmp_path, connected):
    ctx = context(tmp_path, connected=connected)
    assert decode(ctx, DECODE).status == 'PASS'
    result = image_pixels(ctx, PIXELS)
    assert result.status == 'PASS'
    chain = result.evidence['asset_resolution']['input_chain']
    assert len(chain) == (2 if connected else 1)
    assert result.evidence['actual_image_sha256'] == sha(tmp_path/'actual.png')


@pytest.mark.parametrize('fault', ['cycle', 'multiple', 'missing', 'animated', 'computed'])
def test_ambiguous_or_computed_texture_sources_stay_unknown(tmp_path, fault):
    ctx = context(tmp_path, connected=True, fault=fault)
    assert decode(ctx, DECODE).status == 'UNKNOWN'
    with pytest.raises(MissingEvidence):
        image_pixels(ctx, PIXELS)


def test_connected_input_cannot_add_an_asset_after_admission(tmp_path):
    ctx = context(tmp_path, connected=True)
    Image.new('RGB', (4, 4)).save(tmp_path/'not-admitted.png')
    ctx.artifact.stage.GetAttributeAtPath('/World/Material.inputs:file').Set(Sdf.AssetPath(str(tmp_path/'not-admitted.png')))
    assert decode(ctx, DECODE).status == 'UNKNOWN'
    with pytest.raises(MissingEvidence, match='admitted dependency closure'):
        image_pixels(ctx, PIXELS)


def test_connected_texture_bytes_are_rechecked(tmp_path):
    ctx = context(tmp_path, connected=True)
    Image.new('RGB', (4, 4), 'red').save(tmp_path/'actual.png')
    with pytest.raises(BoundaryError, match='changed'):
        image_pixels(ctx, PIXELS)


def test_explicit_regions_preserve_whole_image_diagnostics(tmp_path):
    actual = Image.new('RGB', (4, 4), (1, 1, 1))
    for y in range(4):
        actual.putpixel((0, y), (123, 123, 123))
    ctx = context(tmp_path, actual=actual)
    assert image_pixels(ctx, PIXELS | {'max_channel_error':32}).status == 'FAIL'
    params = PIXELS | dict(max_channel_error=32, max_mean_channel_error=4,
                          excluded_regions=[dict(x=0, y=0, width=1, height=4)])
    result = image_pixels(ctx, params)
    assert result.status == 'PASS'
    row = result.evidence['assessment']['items'][0]
    assert row['compared_pixels'] == 12 and row['excluded_pixels'] == 4
    assert row['maximum_channel_error'] == 1
    assert row['whole_image_maximum_channel_error'] == 123
    assert row['mean_channel_errors'] == [1, 1, 1]
    assert result.evidence['comparison_policy']['excluded_regions'] == params['excluded_regions']
    assert image_pixels(ctx, params | {'max_mean_channel_error':.5}).status == 'FAIL'


def test_binary_mask_and_region_intersection_are_hashed(tmp_path):
    actual = Image.new('RGB', (4, 4), (1, 1, 1))
    actual.putpixel((0, 0), (99, 99, 99))
    ctx = context(tmp_path, actual=actual)
    mask = Image.new('RGB', (4, 4), 'white')
    mask.putpixel((0, 0), (0, 0, 0))
    mask.save(tmp_path/'mask.png')
    params = PIXELS | dict(max_channel_error=1, mask_image='mask.png',
                          regions=[dict(x=0, y=0, width=2, height=4)])
    result = image_pixels(ctx, params)
    assert result.status == 'PASS'
    assert result.evidence['assessment']['items'][0]['compared_pixels'] == 7
    assert result.evidence['comparison_policy']['mask']['sha256'] == sha(tmp_path/'mask.png')
    assert image_pixels(ctx, params | {'max_channel_error':0}).status == 'FAIL'


@pytest.mark.parametrize('fault', ['empty', 'nonbinary', 'size', 'undeclared', 'outside'])
def test_invalid_pixel_selection_never_becomes_a_pass(tmp_path, fault):
    ctx = context(tmp_path)
    mask = Image.new('RGB', (3, 4) if fault == 'size' else (4, 4),
                     'black' if fault == 'empty' else (1, 1, 1) if fault == 'nonbinary' else 'white')
    mask.save(tmp_path/'mask.png')
    params = PIXELS | {'mask_image':'mask.png'}
    if fault == 'undeclared':
        ctx.sources = ['reference.png']
    if fault == 'outside':
        params['regions'] = [dict(x=3, y=0, width=2, height=4)]
    with pytest.raises(ContractError):
        image_pixels(ctx, params)


@pytest.mark.parametrize('mode', ['RGB', 'RGBA'])
def test_visual_brief_admits_1080p_without_changing_exact_comparison(tmp_path, mode):
    image = tmp_path/'reference.png'
    # Uncompressed RGB is >1 MiB: exercise both the old byte and pixel limits.
    Image.new(mode, (1920, 1080)).save(image, compress_level=0 if mode == 'RGB' else 6)
    before = sha(image)
    raw = dict(schema_version='1.0', id='reference', title='Reference', intended_use='Visual comparison',
               provenance='Synthetic regression fixture',
               files=[dict(path='reference.png', role='reference_image', caption='1080p visual reference')])
    (tmp_path/'raw.json').write_text(json.dumps(raw))
    _, rows, _ = _read_raw(tmp_path, 'raw.json')
    mapped = deepcopy(raw)
    mapped.update(mapping_review=dict(status='pending', reviewer='pending', note='Synthetic mapping'),
                  checks=[], requirements=[dict(id='appearance', layer='explicit',
                      statement='Compare visible appearance with supplied reference', basis='Supplied image',
                      required=True, check_ids=[], review_required=True, decision_id=None,
                      inference_authorization=None)])
    # Reuse the schema's required mapping fields rather than bypassing brief validation.
    from scene_acceptance.briefs import BRIEF_SCHEMA
    mapped['mapping_review'] = {k: ('pending' if k == 'status' else 'Synthetic test')
                               for k in BRIEF_SCHEMA['properties']['mapping_review']['required']}
    (tmp_path/'mapped.json').write_text(json.dumps(mapped))
    _, _, snapshots = load_brief(tmp_path, 'mapped.json')
    for row in (rows[0], snapshots[0]):
        assert row['width'] == 1920 and row['height'] == 1080
        assert row['mode'] == mode and row['conversion'] == 'none'
        assert row['alpha'] == ('preserved' if mode == 'RGBA' else 'absent')
    assert sha(image) == before
    with pytest.raises(MissingEvidence):
        read_image(image)


def test_visual_brief_decoder_rejects_corruption_and_excess_bytes(tmp_path):
    path = tmp_path/'bad.png'
    path.write_bytes(b'not an image')
    with pytest.raises(ContractError, match='fully decoded'):
        inspect_visual_reference(path)
    path.write_bytes(b'0' * 8388609)
    with pytest.raises(ContractError, match='8 MiB'):
        inspect_visual_reference(path)


def test_old_and_extended_pixel_parameters_are_valid_contracts():
    schema = brief_measurement_pack().checks['image_pixels'].parameters
    Draft202012Validator(schema).validate(PIXELS)
    Draft202012Validator(schema).validate(PIXELS | dict(max_mean_channel_error=4,
        regions=[dict(x=0, y=0, width=256, height=256)],
        excluded_regions=[dict(x=120, y=0, width=16, height=256)], mask_image='mask.png'))
