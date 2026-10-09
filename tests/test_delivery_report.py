"""The default report explains retained evidence without widening acceptance."""
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote

import pytest

from scene_acceptance.application import invoke
from scene_acceptance.delivery_report import assemble_report, write_delivery_report, load_evaluation
from scene_acceptance.model import ContractError, sha
from scene_acceptance.reader_report import build_overview
from scene_acceptance.triage import run_triage
from test_briefs import samples
from test_triage import case, kwargs, save

PAGES = ('index', 'checks', 'brief', 'visual', 'triage', 'human', 'evidence')


def read(path):
    return json.loads(path.read_text())


def manifest(root):
    save(root / 'manifest.json', {'files': {str(p.relative_to(root)): sha(p)
         for p in root.rglob('*') if p.is_file() and p.name != 'manifest.json'}})


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links += [v for k, v in attrs if k == 'href']


def assert_pages(root):
    folder = root / 'delivery-report'
    for name in PAGES:
        page = folder / (name + '.html')
        parser = Links()
        parser.feed(page.read_text())
        for href in parser.links:
            assert (page.parent / unquote(href.split('#')[0])).is_file(), href
    data = read(folder / 'combined.json')
    for rel, digest in read(root / 'manifest.json')['files'].items():
        assert sha(root / rel) == digest
    return data


def test_default_history_without_brief_explains_coverage(samples, tmp_path):
    result = invoke('check', bundle_root=samples / 'panel', candidate='scene.usda',
                    run_root=tmp_path / 'runs')
    assert result['exit_code'] == 0, result['errors']
    out = Path(result['storage']['output_directory'])
    assert result['report'] == str(out / 'delivery-report/index.html')
    assert 'Open the combined delivery report' in Path(result['storage']['summary_report']).read_text()
    d = assert_pages(out)
    assert d['context']['brief_supplied'] is False
    assert d['context']['brief_sources'] == []
    assert d['judge']['status'] == 'not_requested'
    assert d['triage'] is None
    assert d['context']['scene_data'] and d['core_admission']
    assert 'No-applicable-subjects is not a passed test' in (out / 'delivery-report/checks.html').read_text()


def test_brief_sources_pending_mapping_and_unchanged_requirements(samples, tmp_path):
    bundle = samples / 'panel'
    p = bundle / 'briefs/image-a.json'
    brief = read(p)
    brief['mapping_review']['status'] = 'pending'
    save(p, brief)
    result = invoke('check', bundle_root=bundle, candidate='scene.usda', brief='briefs/image-a.json',
                    out=tmp_path / 'out')
    assert result['exit_code'] == 3, result['errors']
    d = assert_pages(tmp_path / 'out')
    assert d['context']['brief_supplied'] is True
    assert d['context']['mapping_review']['status'] == 'pending'
    assert {r['role'] for r in d['context']['brief_sources']} == {'text', 'reference_image'}
    assert d['context']['supplied_views'] == []  # A reference image is not a rendered delivery.
    assert d['decision'] == 'NEEDS_REVIEW' and d['failure_count'] == 0
    assert 'Synthetic' in d['context']['brief_provenance']


@pytest.fixture
def linked(case, tmp_path):
    """Small retained evaluation around the existing real assessment fixture."""
    root = tmp_path / 'evaluation'
    path = root / 'script/report/assessment.json'
    path.parent.mkdir(parents=True)
    assessment = case[3]
    save(path, assessment)
    ov = build_overview(assessment['core_report'], assessment)
    evaluation = dict(schema_version='1.0', decision='ACCEPT_FOR_DECLARED_SCOPE', exit_code=0,
        brief_supplied=False, scene=ov['scene'], script=dict(status='completed',
        report='script/report/report.html', checks=ov['checks'], matrix=ov['matrix'],
        specifications=ov['specifications']), judge=dict(status='not_requested', findings=[]))
    save(root / 'evaluation.json', evaluation)
    manifest(root)
    modified = (*case[:4], path, case[5])
    args = kwargs(modified, tmp_path)
    result = run_triage(**args)
    assert result['execution_status'] == 'completed'
    return root, args['out']


def test_join_is_model_free_and_preserves_inputs(linked, tmp_path, monkeypatch):
    evaluation, triage = linked
    before = {str(p): sha(p) for root in linked for p in root.rglob('*') if p.is_file()}
    monkeypatch.setattr('scene_acceptance.judge.run_request', lambda *a, **k: pytest.fail('Report called a model'))
    result = invoke('report', evaluation_run=evaluation, triage_run=triage, run_root=tmp_path / 'runs')
    assert result['exit_code'] == 0, result['errors']
    assert result['data']['model_calls'] == 0
    out = Path(result['storage']['output_directory'])
    d = assert_pages(out)
    assert d['decision'] == 'ACCEPT_FOR_DECLARED_SCOPE'
    assert d['triage']['counts'] == {'routine_handling': 1}
    automatic = read(triage / 'delivery-report/combined.json')
    assert automatic['judge']['status'] == 'not_requested'
    assert before == {str(p): sha(p) for root in linked for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('fault', ['different-assessment', 'tampered-evaluation', 'different-snapshot'])
def test_join_rejects_mixed_or_tampered_records(linked, tmp_path, fault):
    evaluation, triage = linked
    if fault == 'tampered-evaluation':
        p = evaluation / 'evaluation.json'
        save(p, read(p) | {'exit_code': 2})
    else:
        p = evaluation / 'script/report/assessment.json'
        d = read(p)
        if fault == 'different-assessment':
            d['items'][0]['statement'] += ' changed'
        else:
            d['snapshot_sha256'] = '0' * 64
        save(p, d)
        manifest(evaluation)
    with pytest.raises(ContractError):
        assemble_report(evaluation_run=evaluation, triage_run=triage, out=tmp_path / 'joined')
    assert not (tmp_path / 'joined').exists()


def test_prepared_parent_pins_nested_evaluation(linked, tmp_path):
    evaluation, _ = linked
    outer = tmp_path / 'prepared'
    outer.mkdir()
    evaluation.rename(outer / 'evaluation')
    save(outer / 'prepared-result.json', {'decision': 'NEEDS_REVIEW', 'exit_code': 3,
                                       'next_action': 'review_specification'})
    manifest(outer)
    load_evaluation(outer)
    p = outer / 'evaluation/evaluation.json'
    save(p, read(p) | {'decision': 'REJECT', 'exit_code': 2})
    manifest(outer / 'evaluation')
    with pytest.raises(ContractError, match='differs'):
        load_evaluation(outer)


def test_mandatory_review_and_failures_do_not_disappear(linked, tmp_path):
    evaluation, triage = linked
    ev, assessment, _, _, _ = load_evaluation(evaluation)
    tr = read(triage / 'triage-result.json')
    ev.update(decision='NEEDS_REVIEW', exit_code=3)
    tr.update(decision='NEEDS_REVIEW', exit_code=3, next_action='provide_evidence')
    d = write_delivery_report(tmp_path / 'review', evaluation=ev, assessment=assessment, triage=tr)
    assert d['next_action'] == 'provide_evidence'
    ev.update(decision='REJECT', exit_code=2)
    d = write_delivery_report(tmp_path / 'reject', evaluation=ev, assessment=assessment, triage=tr)
    assert d['decision'] == 'REJECT' and d['exit_code'] == 2
    d = write_delivery_report(tmp_path / 'scope', evaluation=ev, assessment=assessment, triage=tr,
         prepared={'decision': 'NEEDS_REVIEW', 'exit_code': 3, 'next_action': 'review_specification'})
    assert d['next_action'] == 'review_specification'


def test_html_escapes_source_text_and_keeps_unattached_review_distinct(case, tmp_path):
    assessment = deepcopy(case[3])
    assessment['items'][0]['statement'] = '<script>alert(1)</script>'
    d = write_delivery_report(tmp_path, assessment=assessment,
        brief_context={'title': 'A & B', 'provenance': '<script>bad()</script>', 'files': []})
    assert d['context']['brief_supplied'] is True
    assert d['judge']['status'] == 'not_attached'
    page = (tmp_path / 'delivery-report/brief.html').read_text()
    assert '&lt;script&gt;' in page and '<script>bad()' not in page
    assert 'No matching visual-review record' in (tmp_path / 'delivery-report/visual.html').read_text()


@pytest.mark.parametrize('status', ['UNKNOWN', 'ERROR', 'PASS_WITH_WARNINGS', 'PARTIAL_COVERAGE'])
def test_unresolved_checks_are_visible_in_summary(linked, tmp_path, status):
    evaluation, _ = linked
    ev, assessment, _, _, _ = load_evaluation(evaluation)
    ev['script']['checks'][0]['status'] = status
    ev['script']['checks'][0]['reason'] = 'Evidence must be supplied for this check.'
    write_delivery_report(tmp_path / 'attention', evaluation=ev, assessment=assessment)
    page = (tmp_path / 'attention/delivery-report/index.html').read_text()
    assert 'No outstanding finding' not in page
    assert 'Evidence must be supplied for this check.' in page


def test_judge_concerns_are_visible_above_passing_checks(linked, tmp_path):
    evaluation, _ = linked
    ev, assessment, _, _, _ = load_evaluation(evaluation)
    ev['judge'] = dict(status='completed', model_invoked=True, findings=[dict(
        requirement_id='route-indicator', assessment='concern', explanation='Indicator contradicts route.', evidence_ids=[])])
    ev.update(decision='NEEDS_REVIEW', exit_code=3)
    write_delivery_report(tmp_path / 'attention', evaluation=ev, assessment=assessment)
    page = (tmp_path / 'attention/delivery-report/index.html').read_text()
    assert 'No outstanding finding' not in page
    assert 'Indicator contradicts route.' in page
