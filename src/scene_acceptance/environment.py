"""Installed provider identity and resource disclosure, with no model invocation."""
from importlib import metadata
import os
import platform
import shutil
from .model import digest_json

LIMITS=dict(max_dependency_files_default=64,max_dependency_files_maximum=1024,
    source_file_bytes=33554432,scene_prims=10000,images_including_brief=12,
    view_bytes=8388608,view_pixels=16000000,total_view_bytes=33554432,review_items=256,
    reference_image_bytes=8388608,reference_image_pixels=16000000,
    total_reference_image_bytes=33554432,exact_pixel_image_bytes=1048576,
    exact_pixel_image_pixels=262144)


def environment_identity():
    dependencies={}
    for name in ('usd-core','jsonschema','usd-validation-nvidia','Pillow','numpy','mujoco'):
        try:
            dist=metadata.distribution(name)
            dependencies[name]=dict(version=dist.version,record_sha256=digest_json(dist.read_text('RECORD')))
        except metadata.PackageNotFoundError:dependencies[name]=None
    return dict(python=platform.python_version(),platform=platform.system(),dependencies=dependencies)


def doctor(*,bundle_root=None,candidate=None,max_dependency_files=64,judge_config=None):
    from .packs import default_registry
    from .preparation import allowed_catalog
    env=environment_identity();missing=[n for n in ('usd-core','jsonschema','usd-validation-nvidia','Pillow') if env['dependencies'][n] is None]
    model=None
    if judge_config:
        from .judge import load_config
        config=load_config(judge_config);exe=shutil.which(config['executable'])
        model=dict(executable_found=bool(exe),driver=config['driver'],model=config['model'],
            declared_modalities=config.get('modalities'),modality_verification='Caller declaration; no provider probe or model call',
            timeout_seconds=config['timeout_seconds'],max_model_calls=config.get('max_model_calls',1),
            max_request_bytes=config.get('max_request_bytes',8388608),max_output_bytes=config.get('max_output_bytes',8388608),
            token_budget='Hard token/spend limits belong to the configured provider; usage is recorded when supplied.')
    scene=None;errors=[]
    if bool(bundle_root)!=bool(candidate):errors.append('bundle_root and candidate must be supplied together')
    elif candidate:
        try:
            from .profiles import discover_artifact
            a=discover_artifact(bundle_root,candidate,max_dependency_files=max_dependency_files)
            scene=dict(admitted=True,identity=a.identity,sha256=a.artifact_set_sha256)
        except Exception as e:scene=dict(admitted=False,error=str(e));errors.append(str(e))
    return dict(schema_version='1.0',environment=env,limits=LIMITS,
        formats=['.usd','.usda','.usdc'],unsupported_composition=['payloads','variants','inherits','specializes','value clips','instanceable content','USD packages','resolver URLs'],
        input_adapter='bounded-local-usd-v1',process_group_cleanup_supported=os.name=='posix',
        baseline_ready=not any(n in missing for n in ('usd-core','jsonschema','usd-validation-nvidia')),
        image_evidence_ready='Pillow' not in missing,missing_dependencies=missing,
        packs=default_registry().catalog(),automatic_mapping_types=[c['id'] for c in allowed_catalog()],
        model=model,scene=scene,errors=errors)
