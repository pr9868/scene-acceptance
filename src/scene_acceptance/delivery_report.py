"""One saved-delivery view; presentation never reruns checks or grants approval."""

from collections import Counter
from pathlib import Path
import json
import os
from urllib.parse import quote

from .model import ContractError, sha, strict_json
from .reader_report import build_overview


def _inside(root, name):
    path = (root / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ContractError("Report reference escapes its saved run")
    return path


def _read(path):
    if not path.is_file() or path.stat().st_size > 33554432:
        raise ContractError("Report input must be a JSON file of at most 32 MiB")
    return strict_json(path)


def _verified(root, name):
    path = _inside(root, name)
    manifest = _read(root / 'manifest.json')
    if not path.is_file() or manifest.get('files', {}).get(name) != sha(path):
        raise ContractError("Saved report is missing or differs from its manifest: " + name)
    return _read(path)


def load_evaluation(folder):
    """Read an explicit saved evaluation, including a prepared outer gate."""
    root = Path(folder).resolve()
    prepared = None
    outer = None
    if (root / 'prepared-result.json').is_file():
        outer = root
        prepared = _verified(root, 'prepared-result.json')
        root = root / 'evaluation'
    def read_saved(name):
        if outer:
            _verified(outer, 'evaluation/' + name)
        return _verified(root, name)

    evaluation = read_saved('evaluation.json')
    if evaluation.get('schema_version') != '1.0':
        raise ContractError('Unsupported saved evaluation version')
    assessment = None
    assessment_path = None
    report = evaluation.get('script', {}).get('report')
    if report:
        path = _inside(root, report).parent / 'assessment.json'
        if path.is_file():
            assessment_path = path
            assessment = read_saved(str(path.relative_to(root)))
    context = {}
    for key, names in {
        'brief_context': ('script/report/brief-context.json',),
        'core': ('script/result.json',),
        'review_context': ('evidence/context.json',),
    }.items():
        for name in names:
            if (root / name).is_file():
                context[key] = read_saved(name)
                break
    if not context.get('brief_context') and context.get('review_context'):
        context['brief_context'] = context['review_context'].get('brief')
    return evaluation, assessment, prepared, assessment_path, context


def matching_evaluation(assessment_path, expected_sha256):
    """Only the known evaluator layout is discoverable, never a workspace scan."""
    path = Path(assessment_path).resolve()
    if not path.is_file() or sha(path) != expected_sha256:
        return None
    # Both direct and prepared calls place the assessment at script/report/.
    if path.parent.name != 'report' or path.parent.parent.name != 'script':
        return None
    root = path.parent.parent.parent
    if not (root / 'evaluation.json').is_file():
        return None
    if (root.parent / 'prepared-result.json').is_file() and root.name == 'evaluation':
        root = root.parent
    evaluation, assessment, prepared, selected, context = load_evaluation(root)
    if selected != path or sha(selected) != expected_sha256:
        raise ContractError('Triage and evaluation refer to different assessments')
    return evaluation, assessment, prepared, context


def assemble_report(*, evaluation_run, out, triage_run=None):
    """Combine old runs without modifying them or asking a model again."""
    out = Path(out).resolve()
    roots = [Path(p).resolve() for p in (evaluation_run, triage_run) if p]
    if out.exists() or any(out.is_relative_to(p) or p.is_relative_to(out) for p in roots):
        raise ContractError('Combined report output must be new and outside saved inputs')
    evaluation, assessment, prepared, assessment_path, context = load_evaluation(evaluation_run)
    triage = None
    provenance = [{'label': 'Saved evaluation', 'path': str(Path(evaluation_run).resolve())}]
    if triage_run:
        root = Path(triage_run).resolve()
        triage = _verified(root, 'triage-result.json')
        from jsonschema import Draft202012Validator
        from .triage import result_schema

        Draft202012Validator(result_schema(triage['schema_version'])).validate(triage)
        if (assessment_path is None or sha(assessment_path) != triage['assessment_sha256']
                or assessment['snapshot_sha256'] != triage['snapshot_sha256']):
            raise ContractError('Triage does not belong to this exact assessment')
        if _verified(root, 'assessment.json') != assessment:
            raise ContractError('Retained triage assessment differs from the evaluation')
        provenance.append({'label': 'Saved triage', 'path': str(root)})
    out.mkdir(parents=True)
    result = write_delivery_report(out, evaluation=evaluation, assessment=assessment,
                                  triage=triage, prepared=prepared, provenance=provenance, **context)
    _save(out / 'manifest.json', {'files': {
        str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()
    }})
    return dict(kind='combined-delivery-report', execution_status='completed',
                decision=result['decision'], exit_code=result['exit_code'],
                report=str(out / 'delivery-report/index.html'), model_calls=0,
                note='Presentation of retained results; no new evaluation or approval.')


def _save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def write_delivery_report(out, *, evaluation=None, assessment=None, triage=None,
                          prepared=None, core=None, provenance=(), brief_context=None, review_context=None):
    """Generate a summary and separate detail pages beside existing raw reports."""
    out = Path(out)
    folder = out / 'delivery-report'
    folder.mkdir(parents=True, exist_ok=True)
    core = core or (assessment or {}).get('core_report')
    # These are files produced by this operation, never a workspace-wide scan.
    for base in (out, out / 'script/report', out / 'evaluation/script/report'):
        if brief_context is None and (base / 'brief-context.json').is_file():
            brief_context = _read(base / 'brief-context.json')
    if review_context and brief_context is None:
        brief_context = review_context.get('brief')
    overview = build_overview(core, assessment) if core else {}
    script = (evaluation or {}).get('script') or {
        'status': ('error' if core.get('verdict') == 'EVALUATION_ERROR' else 'completed') if core else 'not_attached',
        'artifact_verdict': (core or {}).get('verdict'),
        'declared_scope_verdict': (assessment or {}).get('assessment_verdict'),
        'checks': overview.get('checks', []), 'matrix': overview.get('matrix', []),
        'specifications': overview.get('specifications', []),
    }
    judge = (evaluation or {}).get('judge') or {
        'status': 'not_attached', 'findings': [], 'counts': {},
    }
    brief_supplied = (evaluation or {}).get('brief_supplied')
    if brief_supplied is None and (brief_context or (assessment or {}).get('mapping_review')):
        brief_supplied = True
    elif brief_supplied is None and core and assessment is None:
        brief_supplied = False
    scene = (evaluation or {}).get('scene') or overview.get('scene') or {}
    outcomes = [x for x in (prepared, evaluation, triage) if x]
    if not evaluation and not prepared and (assessment or core):
        verdict = (assessment or {}).get('assessment_verdict') or core['verdict']
        code = {'REJECT': 2, 'NEEDS_REVIEW': 3, 'INSUFFICIENT_EVIDENCE': 3,
                'EVALUATION_ERROR': 4}.get(verdict, 0)
        outcomes.insert(0, {'decision': verdict, 'exit_code': code})
    # An outer prepared scope rejection or any error must not disappear when
    # a later reviewer only considers selected obligations.
    rank = {0: 0, 3: 1, 2: 2, 4: 3}
    winner = max(enumerate(outcomes), key=lambda pair: (rank[pair[1]['exit_code']],
                 pair[0] if pair[1]['exit_code'] == 3 else -pair[0]))[1] if outcomes else {
        'decision': 'NOT_ASSESSED', 'exit_code': 3}
    if prepared and prepared.get('next_action') == 'review_specification' and winner['exit_code'] != 4:
        winner = prepared
    rows = script.get('checks', [])
    failure_rows = [r for r in rows if r['status'] == 'FAIL']
    warnings = [r for r in rows if r['status'] in ('PASS_WITH_WARNINGS', 'WARNING')
                or (r.get('subject_counts') or {}).get('warning_count', 0)]
    specs = script.get('specifications', [])
    context = {
        'brief_supplied': brief_supplied,
        'brief_title': (brief_context or {}).get('title'),
        'brief_provenance': (brief_context or {}).get('provenance'),
        'brief_sources': [{k: v for k, v in row.items() if k in (
            'path', 'role', 'caption', 'mime', 'sha256', 'source_location')}
            for row in (brief_context or {}).get('files', [])],
        'supplied_views': [row for row in (review_context or {}).get('evidence', [])
                           if row.get('role') == 'scene_view'],
        'producer_decisions': [r['producer_decision'] for r in (assessment or {}).get('items', [])
                               if r.get('producer_decision')],
        'scope_gaps': (assessment or {}).get('gaps', []),
        'script_status': script.get('status'),
        'packs': sorted({r['pack'] for r in rows if r.get('pack')}),
        'mapping_review': (prepared or {}).get('mapping_review') or (assessment or {}).get('mapping_review') or (brief_context or {}).get('mapping_review'),
        'requirement_sources': list({json.dumps(s.get('source', {}), sort_keys=True): s.get('source', {})
                                     for s in specs}.values()),
        'scene_data': bool(scene.get('inventory')),
        'judge_status': judge['status'],
        'visual_model_invoked': judge.get('model_invoked'),
        'visual_evidence': judge.get('evidence_coverage', {}),
        'triage_evidence': [],
    }
    request_path = out / 'model/request.json'
    if triage and request_path.is_file():
        request = _read(request_path)
        context['triage_evidence'] = (request.get('policy') or {}).get('evidence', [])
    if triage and not context['triage_evidence']:
        # The separately supplied source folder remains explicit, rather than
        # inferring that all producer files were read by the model.
        for source in provenance:
            if source['label'] == 'Saved triage':
                policy = _verified(Path(source['path']), 'policy.json')
                context['triage_evidence'] = policy.get('evidence', [])
    data = dict(schema_version='1.0', kind='combined-delivery-report',
                decision=winner['decision'], exit_code=winner['exit_code'],
                next_action=winner.get('next_action'), scene=scene, context=context,
                script=script, assessment=assessment, triage=triage, prepared=prepared,
                judge=judge, evaluation_errors=(evaluation or {}).get('errors', []), core_admission=[r for r in (core or {}).get('checks', [])
                                          if r['id'].startswith('core.')],
                check_counts=dict(Counter(r['status'] for r in rows)),
                failure_count=len(failure_rows), warning_count=len(warnings),
                source_outcomes=[{'decision': r['decision'], 'exit_code': r['exit_code']} for r in outcomes],
                evidence_links=[], provenance=list(provenance),
                note='Saved evidence within the recorded scope. This report makes no new model call, discovers no new defects and grants no approval.')
    # Copy structured source records, not the whole scene, for a durable reader view.
    sources = folder / 'sources'
    sources.mkdir(exist_ok=True)
    for name, value in [('evaluation', evaluation), ('assessment', assessment),
                        ('triage', triage), ('prepared', prepared), ('core', core),
                        ('brief', brief_context), ('review-context', review_context)]:
        if value is not None:
            _save(sources / (name + '.json'), value)
            data['evidence_links'].append({'label': name.title() + ' snapshot',
                                          'href': 'sources/' + name + '.json'})
    for name in ('report.html', 'review-requests.json', 'policy.json', 'model/request.json',
                 'model/response.json', 'model/stdout.log', 'model/stderr.log'):
        if (out / name).is_file():
            data['evidence_links'].append({'label': name, 'href': '../' + quote(name)})
    for source in provenance:
        path = Path(source['path']) / 'report.html'
        if path.is_file():
            data['evidence_links'].append({'label': source['label'] + ' original report',
                'href': quote(os.path.relpath(path, folder))})
    _save(folder / 'combined.json', data)
    from .delivery_report_html import render_pages

    render_pages(folder, data)
    return data
