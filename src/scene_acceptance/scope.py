"""Separate desired requirements, caller approval and a candidate's scene binding."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from importlib.resources import files
import json
import shutil
from jsonschema import Draft202012Validator
from .model import ContractError,digest_json,sha,strict_json
from .review.schemas import obj,array,TEXT,HASH
from .review_context import save,context_for,judge_coverage_drift
from .environment import environment_identity

APPROVAL_SCHEMA=obj({'schema_version':{'const':'1.0'},'scope_sha256':HASH,
    'status':{'enum':['approved','rejected','needs_review']},'reviewer':TEXT,'reason':TEXT,'created_at_utc':TEXT})
APPLICABILITY_SCHEMA = obj({'motion': {'type': 'boolean'}, 'materials': {'type': 'boolean'}})
JUDGE_COVERAGE_DRIFT_SCHEMA = obj({
    'status': {'enum': ['needs_review', 'unchanged']},
    'basis': {'const': 'original_preparation_inventory'},
    'prepared_applicability': APPLICABILITY_SCHEMA,
    'current_applicability': APPLICABILITY_SCHEMA,
    'newly_applicable_areas': {**array({'enum': ['motion', 'materials']}), 'uniqueItems': True},
    'missing_requirement_ids': {**array({'enum': ['review.motion', 'review.material-use']}), 'uniqueItems': True},
    'reason': TEXT,
})
SCOPE_SCHEMA=obj({'schema_version':{'const':'1.0'},'brief':{'type':['object','null']},
    'rubric':{'type':'object'},'capture_requirements':array({'type':'object'}),
    'source_files':{'type':'object','additionalProperties':HASH},
    'evaluation_policy':obj({'baseline':{'type':'object'},'packs':{'type':'object',
        'additionalProperties':obj({'version':TEXT,'implementation_sha256':HASH})}}),
    'scope_sha256':HASH})
SCOPE_SCHEMA['properties']['evaluation_policy']['properties']['runtime_dependencies'] = obj({
    'policy': {'const': 'caller-attested'}, 'environment_sha256': HASH})


def evaluation_policy(brief=None, *, runtime_dependency_policy='local-only', runtime_environment_sha256=None):
    """Freeze general requirements and the implementations selected for this scope."""
    from .packs import default_registry

    from .runtime_dependencies import validate_runtime_policy
    validate_runtime_policy(runtime_dependency_policy, runtime_environment_sha256)
    baseline = json.loads(files('scene_acceptance').joinpath(
        'profiles/usd-delivery-baseline.json').read_text())
    names = set(baseline['packs'])
    names.update(check['pack'] for check in (brief or {}).get('checks', []))
    registry = default_registry()
    identities = {}
    for name in sorted(names):
        description = registry.get(name).describe()
        identities[name] = {
            'version': description['version'],
            'implementation_sha256': description['implementation_sha256'],
        }
    result = {'baseline': baseline, 'packs': identities}
    if runtime_dependency_policy == 'caller-attested':
        result['runtime_dependencies'] = {
            'policy': runtime_dependency_policy, 'environment_sha256': runtime_environment_sha256}
    return result


def current_evaluation_policy(scope):
    """Refresh check identities without changing approved dependency expectations."""
    policy = evaluation_policy(scope['brief'])
    if 'runtime_dependencies' in scope['evaluation_policy']:
        dependencies = scope['evaluation_policy']['runtime_dependencies']
        from .runtime_dependencies import validate_runtime_policy
        validate_runtime_policy(dependencies['policy'], dependencies['environment_sha256'])
        policy['runtime_dependencies'] = deepcopy(dependencies)
    return policy


def policy_changes(previous, current):
    """A readable audit of policy migration; this does not grant scope approval."""
    def changes(before, after):
        return {
            'added': sorted(after.keys() - before.keys()),
            'removed': sorted(before.keys() - after.keys()),
            'changed': sorted(key for key in before.keys() & after.keys()
                              if before[key] != after[key]),
        }

    return {
        'previous_sha256': digest_json(previous),
        'current_sha256': digest_json(current),
        'general_checks': changes(
            {c['id']: c for c in previous['baseline']['checks']},
            {c['id']: c for c in current['baseline']['checks']}),
        'packs': changes(previous['packs'], current['packs']),
        'baseline_metadata_changed': (
            {k: v for k, v in previous['baseline'].items() if k != 'checks'} !=
            {k: v for k, v in current['baseline'].items() if k != 'checks'}),
        'runtime_dependencies_changed': previous.get('runtime_dependencies') != current.get('runtime_dependencies'),
    }


def create_scope(bundle,brief_name,rubric,captures,*,policy=None,
                 runtime_dependency_policy='local-only',runtime_environment_sha256=None):
    brief=strict_json(Path(bundle)/brief_name) if brief_name else None
    if brief:brief.pop('mapping_review',None)
    if policy is None:
        policy = (evaluation_policy(brief) if runtime_dependency_policy == 'local-only' and runtime_environment_sha256 is None
                  else evaluation_policy(brief, runtime_dependency_policy=runtime_dependency_policy,
                                         runtime_environment_sha256=runtime_environment_sha256))
    value=dict(schema_version='1.0',brief=brief,rubric=deepcopy(rubric),
        capture_requirements=[{k:v for k,v in c.items() if k!='feasibility_gaps'} for c in captures],
        source_files={f['path']:sha(Path(bundle)/f['path']) for f in (brief or {}).get('files',[])},
        evaluation_policy=deepcopy(policy))
    value['scope_sha256']=digest_json(value)
    return value


def load_scope(folder,plan):
    from .application_schemas import SCOPE_SCHEMA as schema
    scope = strict_json(Path(folder) / 'scope.json')
    if 'evaluation_policy' not in scope:
        raise ContractError('Legacy scope does not pin its evaluation policy; prepare and approve a new scope')
    Draft202012Validator(schema).validate(scope)
    value={k:v for k,v in scope.items() if k!='scope_sha256'}
    if digest_json(value)!=scope['scope_sha256'] or scope['scope_sha256']!=plan['scope_sha256']:raise ContractError('Scope identity mismatch')
    return scope


def approve_scope(*,preparation,out,expected_scope_sha256,reviewer,reason,status='approved'):
    from .preparation import load_preparation
    folder,plan=load_preparation(preparation);scope=load_scope(folder,plan)
    if scope['scope_sha256']!=expected_scope_sha256:raise ContractError('Approval scope does not match caller pin')
    approval=dict(schema_version='1.0',scope_sha256=expected_scope_sha256,status=status,reviewer=reviewer,reason=reason,
        created_at_utc=datetime.now(timezone.utc).isoformat())
    Draft202012Validator(APPROVAL_SCHEMA).validate(approval)
    out=Path(out).resolve()
    if out.exists() or out.is_relative_to(folder):raise ContractError('Approval must be a new caller-owned file outside preparation')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:
        import json
        f.write(json.dumps(approval,indent=2)+'\n')
    return approval


def read_approval(path,scope_sha256):
    p=Path(path)
    if p.stat().st_size>262144:raise ContractError('Approval record exceeds 256 KiB')
    data=strict_json(p);Draft202012Validator(APPROVAL_SCHEMA).validate(data)
    if data['scope_sha256']!=scope_sha256:raise ContractError('Approval belongs to another scope')
    return data


def bind_preparation(*,preparation,bundle_root,candidate,out,expected_scope_sha256,
                     capture_capabilities=None,max_dependency_files=None,migrate_runtime=False,reviewer=None,reason=None):
    from .preparation import load_preparation,CAPABILITIES_SCHEMA,_write_handoff
    from .engine import implementation_digest
    from .environment import environment_identity
    from .execution import checkpoint
    checkpoint('binding.started')
    old,previous=load_preparation(preparation,allow_runtime_migration=migrate_runtime)
    scope=load_scope(old,previous)
    if scope['scope_sha256']!=expected_scope_sha256:raise ContractError('Binding must pin the unchanged desired scope')
    if migrate_runtime and (not reviewer or not reason):raise ContractError('Runtime migration requires caller reviewer and reason')
    current_policy = current_evaluation_policy(scope)
    policy_changed = current_policy != scope['evaluation_policy']
    if policy_changed and not migrate_runtime:
        raise ContractError('Evaluation policy changed; explicit runtime migration and new scope approval are required')
    difference = policy_changes(scope['evaluation_policy'], current_policy)
    previous_scope_sha256 = scope['scope_sha256']
    if policy_changed:
        scope['evaluation_policy'] = current_policy
        scope.pop('scope_sha256')
        scope['scope_sha256'] = digest_json(scope)
    root=Path(bundle_root).resolve();out=Path(out).resolve()
    if out.exists() or any(out.is_relative_to(p) or p.is_relative_to(out) for p in (root,old)):raise ContractError('Binding output must be new and outside inputs')
    cap=strict_json(old/'capture-plan.json')
    caps=strict_json(capture_capabilities) if capture_capabilities else cap['capabilities']
    Draft202012Validator(CAPABILITIES_SCHEMA).validate(caps)
    budget=previous.get('max_dependency_files',64) if max_dependency_files is None else max_dependency_files
    context=context_for(root,candidate,out/'admission',max_dependency_files=budget)
    original_request = strict_json(old/'preparation-request.json')
    drift = judge_coverage_drift(original_request['scene']['inventory'],
                                 context['scene']['inventory'], scope['rubric'])
    bundle=Path(context['snapshot_bundle']);old_bundle=old/previous['bundle']
    for path,h in scope['source_files'].items():
        target=(bundle/path).resolve()
        if not target.is_relative_to(bundle) or target.exists():raise ContractError('Brief-source path collides with revised scene')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old_bundle/path,target)
        if sha(target)!=h:raise ContractError('Scope source changed during rebinding')
    brief_name=previous['brief']
    if brief_name:
        target=bundle/brief_name
        if target.exists():raise ContractError('Compiled brief path collides with candidate')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old_bundle/brief_name,target)
    structure=context['scene']['inventory']['scene_structure'];rate=structure['time_codes_per_second']
    duration=(structure['end_time_code']-structure['start_time_code'])/rate if rate>0 else 0
    refs=sum(f['role']=='reference_image' for f in (scope['brief'] or {}).get('files',[]))
    image_budget=min(caps['max_images'],12-refs);captures=deepcopy(scope['capture_requirements'])
    for c in captures:
        gaps=[]
        if set(c['targets'])-set(context['scene']['prim_paths']):gaps.append('Required target is absent from this candidate')
        if any(t>duration+1e-6 for t in c['times_seconds']):gaps.append('Requested time is outside this candidate; requirement remains unchanged')
        if set(c['capabilities'])-set(caps['capabilities']):gaps.append('Caller lacks requested capture capability')
        if c['min_width']>caps['max_width'] or c['min_height']>caps['max_height']:gaps.append('Requested resolution exceeds caller capability')
        if len(c['times_seconds'])>image_budget:gaps.append('Request exceeds image budget')
        if c['evidence_kind']=='motion_frames' and len(c['times_seconds'])<3:gaps.append('Scope has no eligible motion sample set')
        c['feasibility_gaps']=gaps
    for name in ('rubric.json','interpretation.json','capture-overrides.json','source-brief.json','preparation-request.json'):
        shutil.copyfile(old/name,out/name)
    save(out/'scope.json',scope)
    save(out/'capture-plan.json',dict(cap,scene_sha256=context['scene']['sha256'],requests=captures,capabilities=caps,image_budget_after_references=image_budget))
    files={str(p.relative_to(out)):sha(p) for p in bundle.rglob('*') if p.is_file()}
    files.update({p.name:sha(p) for p in out.glob('*.json')})
    plan=dict(previous,files=files,bundle=str(bundle.relative_to(out)),candidate=context['candidate'],
        scene_identity=context['scene']['identity'],scene_sha256=context['scene']['sha256'],max_dependency_files=budget,
        runtime_sha256=implementation_digest(),environment=environment_identity(),scope_sha256=scope['scope_sha256'],
        previous_plan_sha256=previous['plan_sha256'],binding=dict(scope_unchanged=not policy_changed,model_calls=0,
            judge_coverage_drift=drift,
            previous_scope_sha256=previous_scope_sha256,evaluation_policy_changed=policy_changed,policy_changes=difference,
            requires_scope_approval=policy_changed or previous.get('binding',{}).get('requires_scope_approval',False),
            previous_scene_sha256=previous['scene_sha256'],runtime_migration=bool(migrate_runtime),reviewer=reviewer,reason=reason,
            previous_environment=previous.get('environment'),previous_runtime_sha256=previous['runtime_sha256']))
    plan.pop('plan_sha256');plan['plan_sha256']=digest_json(plan);save(out/'plan.json',plan)
    _write_handoff(out,plan,captures,(scope['brief'] or {}).get('requirements',[]))
    checkpoint('binding.completed',scope_sha256=plan['scope_sha256'])
    return plan
