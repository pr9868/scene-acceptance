"""Stable routing hints and comparisons; never conflate unassessed with fixed."""
from pathlib import Path
from .model import ContractError,strict_json


def actionable_findings(evaluation,captures=(),mapping_review=None,approval=None):
    rows=[]
    if approval and approval['status'] != 'approved':
        rejected = approval['status'] == 'rejected'
        rows.append(dict(id='scope.approval-rejected' if rejected else 'scope.approval-pending',
            kind='review',status='rejected' if rejected else 'pending',next_action='review_specification',
            reason=approval['reason'],reviewer=approval['reviewer'],scope_sha256=approval['scope_sha256'],
            guidance='Revise the proposed scope and prepare it again before requesting approval.' if rejected else
                     'Review the proposed scope before granting approval.'))
    for c in evaluation['script']['checks']:
        status=c['status']
        action='repair_scene' if status=='FAIL' else 'fix_environment' if status=='ERROR' else 'provide_evidence' if status in ('UNKNOWN','PARTIAL_COVERAGE','PARTIAL') else 'none'
        rows.append(dict(id='check:'+c['id'],kind='script',status=status,next_action=action,
            subject=dict(unit=c.get('subject_unit'),scope=c.get('coverage')),parameters=c.get('parameters'),observed_values=c.get('observed_values'),
            evidence_pointer=c.get('evidence_pointer'),reason=c.get('reason'),counts=c.get('subject_counts')))
    for r in evaluation['judge']['findings']:
        rows.append(dict(id='judge:'+r['requirement_id'],kind='advisory',status=r['assessment'],
            next_action='review_finding' if r['assessment']=='concern' else 'provide_evidence' if r['assessment']=='unknown' else 'none',
            evidence_ids=r['evidence_ids'],reason=r['explanation']))
    for c in captures:
        rows.append(dict(id='capture:'+c['request_id'],kind='evidence',status=c['status'],targets=c['targets'],
            next_action='none' if c['status']=='supplied' else 'provide_evidence',reason='; '.join(c['gaps'])))
    if mapping_review=='pending' and not approval:rows.append(dict(id='scope:mapping',kind='review',status='pending',next_action='review_specification',reason='Caller scope approval is pending'))
    for i,error in enumerate(evaluation['errors']):rows.append(dict(id=f'execution:{i}',kind='execution',status='ERROR',next_action='fix_environment',reason=error))
    return rows


def primary_next_action(decision, findings):
    """Route a caller's next step without hiding independent measured findings."""
    if decision == 'EVALUATION_ERROR':
        return 'fix_environment'
    if decision == 'REJECT':
        return 'repair_scene'
    actions = {row['next_action'] for row in findings}
    for action in ('review_specification', 'provide_evidence', 'review_finding'):
        if action in actions:
            return action
    return 'none'


def compare_runs(previous_path,current):
    path=Path(previous_path)
    if path.is_dir():path=path/'prepared-result.json'
    if path.stat().st_size>8388608:raise ContractError('Previous result exceeds 8 MiB')
    old=strict_json(path)
    same_scope=bool(current.get('scope_sha256')) and old.get('scope_sha256')==current['scope_sha256']
    before={r['id']:r for r in old.get('findings',[])};after={r['id']:r for r in current['findings']}
    changes=[]
    for id in sorted(before.keys()|after.keys()):
        a=before.get(id);b=after.get(id)
        if not a:state='newly_assessed'
        elif not b:state='not_assessed_in_current_run'
        elif a['status']==b['status']:state='unchanged'
        elif same_scope and b['status'] in ('PASS','consistent','supplied'):state='improved_in_stated_scope'
        else:state='changed'
        changes.append(dict(id=id,previous=a and a['status'],current=b and b['status'],change=state))
    return dict(same_scope=same_scope,previous_scene_sha256=old.get('scene_sha256'),current_scene_sha256=current.get('scene_sha256'),changes=changes,
                limitation='Advisory consistency is not a measured fix; missing current checks are unassessed, not resolved.')
