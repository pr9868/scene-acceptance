"""Checks of selected saved evidence, deliberately narrower than visual correctness."""
from pathlib import Path
import math
import warnings
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade
from scene_acceptance.builtin_packs import obj, TEXT, VEC3
from scene_acceptance.model import ContractError, MissingEvidence, sha
from scene_acceptance.motion_timing import read_clock
from scene_acceptance.packs import Pack, CheckSpec, Outcome
from scene_acceptance.image_evidence import resolve_asset_input


def decode(ctx, params):
    from PIL import Image, UnidentifiedImageError
    attribute = ctx.artifact.stage.GetAttributeAtPath(params['asset_attribute'])
    if not attribute or attribute.GetTypeName() != Sdf.ValueTypeNames.Asset:
        return Outcome('FAIL', 'Required asset-valued attribute is absent.')
    shader = UsdShade.Shader(attribute.GetPrim())
    if not shader or shader.GetIdAttr().Get() != 'UsdUVTexture':
        return Outcome('UNKNOWN', 'This decoder only admits a selected UsdUVTexture attribute.')
    try:
        path, resolution = resolve_asset_input(ctx, attribute)
    except MissingEvidence as exc:
        return Outcome('UNKNOWN', str(exc))
    if path is None:
        return Outcome('FAIL', 'The selected texture reference is empty.')
    evidence = {'file': str(path.relative_to(ctx.bundle.root)), 'sha256': sha(path),
                'bytes': path.stat().st_size, 'asset_attribute': params['asset_attribute'],
                'asset_resolution': resolution}
    if evidence['bytes'] > params['max_bytes']:
        return Outcome('UNKNOWN', 'File exceeds the configured decoding byte budget.', evidence)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as img:
                evidence.update(format=img.format, width=img.width, height=img.height,
                                frames=getattr(img, 'n_frames', 1))
                if img.format not in ('PNG', 'JPEG') or evidence['frames'] != 1:
                    return Outcome('UNKNOWN', 'Only single-frame PNG and JPEG are admitted.', evidence)
                if img.width * img.height > params['max_pixels']:
                    return Outcome('UNKNOWN', 'Image exceeds the configured pixel budget.', evidence)
                img.verify()
            with Image.open(path) as img:
                img.load()
                evidence['mode'] = img.mode
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        return Outcome('UNKNOWN', 'Decoder safety limit exceeded.', evidence)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        evidence['decoder_error'] = type(exc).__name__ + ': ' + str(exc)
        return Outcome('FAIL', 'Required image could not be verified and fully decoded.', evidence)
    return Outcome('PASS', 'Selected image verified and fully decoded within the stated limits.', evidence)


def texture_pack():
    return Pack('textures.decode', '0.2.0', 'Decode a selected static PNG or JPEG dependency', {
        'image': CheckSpec(decode, obj({
            'asset_attribute': TEXT,
            'max_pixels': {'type': 'integer', 'minimum': 1, 'maximum': 16000000},
            'max_bytes': {'type': 'integer', 'minimum': 1, 'maximum': 33554432},
        }), 'Verify and load one required image', 'Selected static image bytes',
        ('No UV, color-management, rendered appearance or hostile-input isolation claim',))
    }, (str(Path(__file__)), str(Path(__file__).parent.parent/'image_evidence.py')), ('Pillow', 'usd-core'))


def connection(ctx, params):
    from scene_acceptance.motion_timing import elapsed_time_code
    stage = ctx.artifact.stage
    clock = read_clock(stage)
    if not stage.HasAuthoredMetadata('metersPerUnit'):
        raise MissingEvidence('An authored metres-per-unit value is required')
    units = UsdGeom.GetStageMetersPerUnit(stage)
    if not math.isfinite(units) or units <= 0:
        raise MissingEvidence('Stage units must be finite and positive')
    start, end = params['interval_s']
    if start >= end:
        raise ContractError('The connection interval must be increasing')
    elapsed_time_code(clock, start)
    elapsed_time_code(clock, end)
    prims = [stage.GetPrimAtPath(params[k]['path']) for k in ('a', 'b')]
    if not all(p and p.IsA(UsdGeom.Xformable) for p in prims):
        return Outcome('FAIL', 'A required transformable connection endpoint is absent.')
    n = params['segments']
    times = {start + (end-start)*i/n for i in range(n+1)}
    if params['schedule'] == 'keys-and-midpoints':
        for p in prims:
            while p and not p.IsPseudoRoot():
                if p.IsA(UsdGeom.Xformable):
                    xf = UsdGeom.Xformable(p)
                    for op in xf.GetOrderedXformOps():
                        for tc in op.GetAttr().GetTimeSamples():
                            t = (tc-clock['start_time_code'])/clock['time_codes_per_second']
                            if start <= t <= end:
                                times.add(t)
                    if xf.GetResetXformStack():
                        break
                p = p.GetParent()
        ordered = sorted(times)
        times.update((a+b)/2 for a,b in zip(ordered, ordered[1:]))
    if len(times) > 4097:
        raise MissingEvidence('Schedule exceeds the 4,097-sample budget')
    rows = []
    for elapsed in sorted(times):
        tc = elapsed_time_code(clock, elapsed)
        cache = UsdGeom.XformCache(Usd.TimeCode(tc))
        points = [cache.GetLocalToWorldTransform(p).Transform(Gf.Vec3d(*params[k]['local_point'])) * units
                  for p,k in zip(prims, ('a','b'))]
        if not all(math.isfinite(v) for point in points for v in point):
            raise MissingEvidence('Non-finite transformed point')
        gap = (points[0]-points[1]).GetLength()
        rows.append({'elapsed_s': elapsed, 'time_code': tc, 'a_m': list(points[0]),
                     'b_m': list(points[1]), 'gap_m': gap})
    worst = max(rows, key=lambda row: row['gap_m'])
    return Outcome('PASS' if worst['gap_m'] <= params['max_gap_m'] else 'FAIL',
        'Euclidean connection distance in metres compared at the recorded sample times only.',
        {'clock': clock, 'units_m': units, 'schedule': params['schedule'], 'samples': rows,
         'maximum_sampled_gap_m': worst['gap_m'], 'worst_elapsed_s': worst['elapsed_s'],
         'max_gap_m': params['max_gap_m'], 'tolerance_metric': 'euclidean_distance_metres',
         'coverage': 'Finite samples; no continuous bound, collisions or physics proof.'})


def connection_pack():
    return Pack('motion.connection', '0.1.0', 'Sample a connection between two transformed local points', {
        'distance': CheckSpec(connection, obj({
            'a': obj({'path': TEXT, 'local_point': VEC3}),
            'b': obj({'path': TEXT, 'local_point': VEC3}),
            'interval_s': {'type': 'array', 'minItems': 2, 'maxItems': 2,
                           'items': {'type': 'number', 'minimum': 0}},
            'segments': {'type': 'integer', 'minimum': 1, 'maximum': 2048},
            'schedule': {'enum': ['uniform', 'keys-and-midpoints']},
            'max_gap_m': {'type': 'number', 'minimum': 0},
        }), 'Compare the gap between two task-named points', 'World-space distances at explicit times',
        ('Points are caller-defined, not inferred joints; finite sampling can miss motion defects',))
    }, (str(Path(__file__)),), ('usd-core',))
