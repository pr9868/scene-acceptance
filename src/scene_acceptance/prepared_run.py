"""Consume frozen preparation and caller-produced evidence without reinterpretation."""
from collections import Counter
import argparse
import json
import shutil
from pathlib import Path
from jsonschema import Draft202012Validator
from .model import ContractError, sha, strict_json
from .preparation import load_preparation, RECEIPT_SCHEMA
from .review_context import context_for, intact, save
from .evaluation import evaluate_scene


def validate_receipt(plan, capture, manifest, receipt, view_root):
    requests=capture['requests'];known={c['id'] for c in requests};submitted={}
    if receipt is not None:
        Draft202012Validator(RECEIPT_SCHEMA).validate(receipt)
        if receipt['plan_sha256']!=plan['plan_sha256'] or receipt['scene_sha256']!=plan['scene_sha256']: raise ContractError('Receipt is bound to another plan or scene')
        ids=[r['request_id'] for r in receipt['requests']]
        if len(set(ids))!=len(ids) or set(ids)-known: raise ContractError('Receipt has duplicate or unknown request IDs')
        submitted={r['request_id']:r for r in receipt['requests']}
    views={v['id']:v for v in (manifest or {}).get('views',[])}
    if len(views)>capture['image_budget_after_references']: raise ContractError('Returned views exceed the frozen caller image budget')
    sizes={}
    if views:
        from PIL import Image
        for v in views.values():
            with Image.open(Path(view_root)/v['path']) as im: sizes[v['id']]=im.size
    rows=[];per_requirement={}
    for c in requests:
        r=submitted.get(c['id']);gaps=list(c['feasibility_gaps']);selected=[];eligible=set()
        if not r: gaps.append('No caller receipt for this request')
        elif r['status']=='unavailable':
            if r['view_ids']: raise ContractError('Unavailable receipt must not claim supplied views')
            gaps.append(r['reason'])
        else:
            if set(r['view_ids'])-views.keys(): raise ContractError('Receipt cites unknown view IDs')
            selected=[views[i] for i in r['view_ids']]
            if not selected: gaps.append('Supplied receipt contains no views')
            for t in c['times_seconds']:
                candidates=[v for v in selected if abs(v['time_seconds']-t)<=1e-6
                    and c.get('view_role',c['id']) in v.get('view_roles',[])
                    and (c.get('camera_id') is None or c['camera_id']==v['camera_id'])
                    and (c.get('projection') is None or c['projection']==v['projection'])
                    and set(c['targets'])<=set(v['covered_prims']) and set(c['capabilities'])<=set(v['capabilities'])
                    and sizes[v['id']][0]>=c['min_width'] and sizes[v['id']][1]>=c['min_height']]
                if not candidates: gaps.append(f'No qualifying view at {t:g} seconds with requested targets, fidelity and resolution')
                eligible.update(v['id'] for v in candidates)
            if c['evidence_kind']=='motion_frames':
                cameras={(v['camera_id'],v['camera'],v['projection'],v['method']) for v in selected}
                if len(cameras)!=1: gaps.append('Motion request requires one declared fixed camera and capture method')
        row=dict(request_id=c['id'],requirement_ids=c['requirement_ids'],purpose=c['purpose'],targets=c['targets'],
            times_seconds=c['times_seconds'],view_role=c.get('view_role',c['id']),camera_guidance=c.get('camera_guidance'),
            camera_id=c.get('camera_id'),projection=c.get('projection'),sharing_group=c.get('sharing_group'),status='missing' if gaps else 'supplied',gaps=gaps,
            view_ids=[v['id'] for v in selected],eligible_view_ids=sorted(eligible),caller_reason=r['reason'] if r else None)
        rows.append(row)
        for rid in c['requirement_ids']: per_requirement.setdefault(rid,[]).append(row)
    # One physical image cannot silently stand in for distinct requested viewpoints.
    uses={}
    for row in rows:
        for vid in row['eligible_view_ids']:
            key=views[vid].get('sha256',vid)
            uses.setdefault(key,[]).append(row)
    for group in uses.values():
        distinct={r['request_id']:r for r in group}
        if len(distinct)>1:
            shared={r['sharing_group'] for r in distinct.values()};roles={r['view_role'] for r in distinct.values()}
            if len(shared)!=1 or None in shared or len(roles)!=1:
                for row in distinct.values():
                    row['status']='missing';row['gaps'].append('Image reused across distinct capture requests without an explicit common role/sharing group')
    policy={rid:dict(ready=all(r['status']=='supplied' for r in group),
                    evidence_ids=sorted({'view:'+v for r in group if r['status']=='supplied' for v in r['eligible_view_ids']})) for rid,group in per_requirement.items()}
    return rows,policy


def _evidence_preflight(folder,plan,bundle,out,views,receipt):
    capture=strict_json(folder/'capture-plan.json');preflight=None;hashes={}
    try:
        if bool(views)!=bool(receipt):raise ContractError('Views and their capture receipt must be supplied together')
        if receipt:
            if Path(receipt).stat().st_size>1048576:raise ContractError('Capture receipt exceeds 1 MiB')
            hashes[str(Path(receipt).resolve())]=sha(receipt)
        preflight=context_for(bundle,plan['candidate'],out,brief=plan['brief'],views=views,
                              rubric=folder/'rubric.json',max_dependency_files=plan['max_dependency_files'])
        rows,policy=validate_receipt(plan,capture,strict_json(views) if views else None,
                                    strict_json(receipt) if receipt else None,Path(views).resolve().parent if views else None)
        return rows,policy,preflight,None,hashes
    except Exception as exc:
        error=type(exc).__name__+': '+str(exc)
        rows=[dict(request_id=c['id'],requirement_ids=c['requirement_ids'],purpose=c['purpose'],targets=c['targets'],
            times_seconds=c['times_seconds'],status='invalid',gaps=[error],view_ids=[]) for c in capture['requests']]
        return rows,{},preflight,error,hashes


def validate_prepared_evidence(*,preparation,out,expected_plan_sha256=None,views=None,receipt=None):
    folder,plan=load_preparation(preparation,expected_plan_sha256);out=Path(out).resolve()
    if out.exists() or out.is_relative_to(folder) or folder.is_relative_to(out):raise ContractError('Evidence output must be new and outside preparation')
    if any(p and Path(p).resolve().is_relative_to(out) for p in (views,receipt)):raise ContractError('Evidence output overlaps input')
    rows,policy,context,error,hashes=_evidence_preflight(folder,plan,folder/plan['bundle'],out/'preflight',views,receipt)
    load_preparation(folder,plan['plan_sha256'])
    if (context and not intact(context)) or any(not Path(p).is_file() or sha(p)!=h for p,h in hashes.items()):error='Evidence changed during validation'
    result=dict(schema_version='1.0',plan_sha256=plan['plan_sha256'],scene_sha256=plan['scene_sha256'],
        capture_requests=rows,evidence_policy=policy,model_calls=0,errors=[error] if error else [],
        execution_status='failed' if error else 'completed',exit_code=4 if error else 3 if any(r['status']!='supplied' for r in rows) else 0)
    out.mkdir(parents=True,exist_ok=True)
    save(out/'evidence-result.json',result)
    return result


def evaluate_prepared(*,preparation,out,expected_plan_sha256=None,mode='checks',views=None,receipt=None,judge_config=None,judge_exposure='withheld',approval=None,previous_run=None,review_record=None,runtime_dependency_evidence=None):
    from .execution import checkpoint
    checkpoint('prepared_evaluation.started')
    folder,plan=load_preparation(preparation,expected_plan_sha256);out=Path(out).resolve()
    if out.exists() or out.is_relative_to(folder) or folder.is_relative_to(out): raise ContractError('Run output must be new and outside preparation')
    if mode not in ('checks','judge','both'): raise ContractError('Unknown mode')
    if mode=='checks' and any(x is not None for x in (views,receipt,judge_config)): raise ContractError('Evidence and judge options require judge or both mode')
    if mode=='checks' and judge_exposure!='withheld': raise ContractError('Script-aware review requires both mode')
    if mode!='checks' and judge_config is None: raise ContractError('Explicit judge configuration required')
    for p in (views,receipt,judge_config,approval,previous_run,review_record,runtime_dependency_evidence):
        if p and Path(p).resolve().is_relative_to(out): raise ContractError('Run output overlaps supplied input')
    capture=strict_json(folder/'capture-plan.json');rows=[];policy=None;preflight=None;evidence_error=None;approval_data=None;input_hashes={str(folder/'plan.json'):sha(folder/'plan.json')}
    drift=plan.get('binding',{}).get('judge_coverage_drift')
    from .scope import load_scope
    runtime_policy=load_scope(folder,plan)['evaluation_policy'].get('runtime_dependencies',{})
    if runtime_dependency_evidence:
        input_hashes[str(Path(runtime_dependency_evidence).resolve())]=sha(runtime_dependency_evidence)
    bundle=folder/plan['bundle'];budget=plan.get('max_dependency_files',64)
    if approval:
        from .scope import read_approval
        approval_data=read_approval(approval,plan['scope_sha256']);input_hashes[str(Path(approval).resolve())]=sha(approval)
        out.mkdir(parents=True,exist_ok=True);save(out/'scope-approval.json',approval_data)
        if approval_data['status']=='approved' and plan['brief']:
            # Derive a run-local reviewed mapping; the original scope/packet never changes.
            approved_bundle=out/'approved-inputs'
            for name,h in plan['files'].items():
                source=(folder/name).resolve()
                if source.is_relative_to(bundle):
                    target=approved_bundle/source.relative_to(bundle);target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,target)
                    if sha(target)!=h:raise ContractError('Prepared source changed during approval snapshot')
            bundle=approved_bundle
            brief=strict_json(bundle/plan['brief'])
            brief['mapping_review']=dict(status='reviewed',reviewer=approval_data['reviewer'],reason=approval_data['reason'])
            save(bundle/plan['brief'],brief)
    if mode!='checks':
        checkpoint('evidence.validation')
        rows,policy,preflight,evidence_error,hashes=_evidence_preflight(folder,plan,bundle,out/'preflight',views,receipt)
        input_hashes.update(hashes)
    result=evaluate_scene(bundle_root=bundle,candidate=plan['candidate'],out=out/'evaluation',mode=mode,brief=plan['brief'],
        expected_brief_sha256=sha(bundle/plan['brief']) if plan['brief'] else None,judge_config=judge_config,
        views=views,rubric=folder/'rubric.json' if mode!='checks' else None,judge_exposure=judge_exposure,evidence_policy=policy,
        evidence_error=evidence_error,evidence_requirements=dict(requests=capture['requests'],receipts=rows),max_dependency_files=budget,review_record=review_record,
        runtime_dependency_evidence=runtime_dependency_evidence,runtime_dependency_policy=runtime_policy.get('policy','local-only'),
        runtime_environment_sha256=runtime_policy.get('environment_sha256'))
    unchanged=all(Path(p).is_file() and sha(p)==h for p,h in input_hashes.items()) and (preflight is None or intact(preflight))
    try: load_preparation(folder,plan['plan_sha256'])
    except Exception: unchanged=False
    decision,code=result['decision'],result['exit_code']
    if not unchanged: decision,code='EVALUATION_ERROR',4
    elif approval_data and approval_data['status']!='approved' and code!=4:decision,code='NEEDS_REVIEW',3
    elif (plan.get('binding', {}).get('requires_scope_approval')
          and not (approval_data and approval_data['status'] == 'approved') and code == 0):
        decision, code = 'NEEDS_REVIEW', 3
    elif (runtime_policy.get('policy')=='caller-attested'
          and not (approval_data and approval_data['status']=='approved') and code==0):
        decision, code = 'NEEDS_REVIEW', 3
    elif mode!='checks' and drift and drift['status']=='needs_review' and code==0:
        decision, code = 'NEEDS_REVIEW', 3
    elif mode!='checks' and any(r['status']=='missing' for r in rows) and code==0: decision,code='NEEDS_REVIEW',3
    report=dict(schema_version='1.0',plan_sha256=plan['plan_sha256'],scene_sha256=plan['scene_sha256'],candidate=plan['candidate'],
        mode=mode,mapping_review=('reviewed' if approval_data['status']=='approved' else 'pending') if approval_data else plan['mapping_review'],
        scope_sha256=plan.get('scope_sha256'),approval=approval_data,execution_status=result['execution_status'],errors=result['errors'],routes=plan['routes'],decision=decision,exit_code=code,
        unchanged=unchanged,capture_counts=dict(Counter(r['status'] for r in rows)),capture_requests=rows,
        evidence_policy=policy,evaluation_report='evaluation/report.html',
        script_verdict=result['script']['artifact_verdict'],scope_verdict=result['script']['declared_scope_verdict'],
        judge_counts=result['judge'].get('counts',{}),
        limitations=['Supplied means declared capture metadata meets the plan; visibility and rendering truth remain unverified.',
                    'A migrated evaluation policy requires approval of the new scope before acceptance.',
                    'Judge opinions cannot approve the interpreted mapping or clear a measured failure.',
                    'Check counts and per-asset coverage are in the linked evaluation report.',
                    'Checks-only mode does not assess requested visual evidence.'])
    from .findings import actionable_findings,compare_runs,primary_next_action
    report['findings']=actionable_findings(result,rows,report['mapping_review'],approval_data)
    if drift:
        report['judge_coverage_drift']=drift
        if drift['status']=='needs_review':
            report['findings'].append(dict(id='scope.judge-coverage-drift',kind='review',status='UNKNOWN',
                next_action='review_specification',reason=drift['reason'],missing_requirement_ids=drift['missing_requirement_ids'],
                guidance='Prepare a new scope with the revised candidate and review its judge questions and capture requests. Existing scope approval does not add the missing coverage.',
                judge_requested=mode!='checks',
                limitation='Checks-only mode preserves its measured result; the frozen judge scope does not cover these new scene areas.' if mode=='checks' else
                           'The frozen judge scope omits newly applicable areas; no acceptance from this judge run clears that gap.'))
    if (plan.get('binding', {}).get('requires_scope_approval')
            and not (approval_data and approval_data['status'] == 'approved')):
        report['findings'].append({
            'id': 'scope.evaluation-policy-review',
            'kind': 'review',
            'status': 'UNKNOWN',
            'next_action': 'review_specification',
            'reason': 'Evaluation policy changed. Review binding.policy_changes in plan.json and approve the new scope before acceptance.',
            'scope_sha256': plan['scope_sha256'],
        })
    if (runtime_policy.get('policy')=='caller-attested'
            and not (approval_data and approval_data['status']=='approved')):
        report['findings'].append(dict(id='scope.runtime-dependency-policy-review',kind='review',status='UNKNOWN',
            next_action='review_specification',scope_sha256=plan['scope_sha256'],
            reason='Approve the scope containing the caller-attested runtime dependency policy and pinned target environment before acceptance.'))
    report['next_action']=primary_next_action(decision,report['findings'])
    report['comparison']=compare_runs(previous_run,report) if previous_run else None
    save(out/'prepared-result.json',report)
    _report(out,report)
    save(out/'manifest.json',{'files':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p!=out/'manifest.json'}})
    return report


def _report(out,report):
    from .report import E,STYLE
    rows=''.join(f'<tr><td>{E(r["request_id"])}</td><td>{E(r["purpose"])}</td><td>{E(r["status"])}</td><td>{E(", ".join(r["view_ids"]) or "None")}</td><td>{E("; ".join(r["gaps"]))}</td></tr>' for r in report['capture_requests'])
    actions=''.join(f'<tr><td>{E(r["id"])}</td><td>{E(r["status"])}</td><td>{E(r["next_action"].replace("_"," "))}</td><td>{E(r.get("reason") or "")}</td></tr>' for r in report['findings'] if r['next_action']!='none')
    comparison=report.get('comparison')
    changes=''.join(f'<tr><td>{E(r["id"])}</td><td>{E(r["previous"] or "Not assessed")}</td><td>{E(r["current"] or "Not assessed")}</td><td>{E(r["change"].replace("_"," "))}</td></tr>' for r in (comparison or {}).get('changes',[]) if r['change']!='unchanged')
    details=f'<h2>Next actions</h2><p>Next step: {E(report["next_action"].replace("_", " "))}</p><table><tr><th>Finding</th><th>Status</th><th>Action</th><th>Reason</th></tr>{actions}</table>'
    if comparison:details+=f'<h2>Compared with previous run</h2><p>Same requirements: {E(str(comparison["same_scope"]))}. {E(comparison["limitation"])}</p><table><tr><th>Finding</th><th>Before</th><th>Now</th><th>Change</th></tr>{changes}</table>'
    (out/'report.html').write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Prepared scene evaluation</title><style>{STYLE}</style><main><h1>{E(report["decision"])}</h1><p>Scene: {E(report["candidate"])} · Mode: {E(report["mode"])} · Mapping review: {E(report["mapping_review"])}</p><p>Script: {E(report["script_verdict"] or "Not requested")} · Declared scope: {E(report["scope_verdict"] or "Not assessed")} · Judge: {E(str(report["judge_counts"]))}</p><h2>Caller evidence coverage</h2><p>{E(str(report["capture_counts"]))}</p><table><tr><th>Request</th><th>Purpose</th><th>Coverage</th><th>Views</th><th>Missing evidence</th></tr>{rows}</table>{details}<p><a href="evaluation/report.html">Full checks, subject counts and judge findings</a> · <a href="prepared-result.json">Machine-readable handoff result</a></p><p>{E(" ".join(report["limitations"]))}</p></main></html>')


def main(argv=None):
    from .application import evaluate_main
    return evaluate_main(argv)

if __name__=='__main__':raise SystemExit(main())
