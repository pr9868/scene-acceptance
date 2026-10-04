"""Replay the retained controls with integrity checks that survive Python -O."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent


class VerificationError(RuntimeError):
    """A replay or its retained inputs do not satisfy the recorded expectation."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)
    return bool(condition)


def read_json(path):
    return json.loads(path.read_text())


def verify_files(root, manifest):
    files = manifest['files']
    require(bool(files), 'Manifest contains no retained files')
    matches = {}
    for relative, digest in files.items():
        path = (root / relative).resolve()
        require(path.is_relative_to(root.resolve()), 'Manifest path escapes companion: ' + relative)
        require(path.is_file(), 'Retained file is missing: ' + relative)
        matches[relative] = hashlib.sha256(path.read_bytes()).hexdigest() == digest
        require(matches[relative], 'Retained file differs: ' + relative)
    return matches


def verify_checker(actual, expected):
    return require(actual == expected, 'Installed checker differs from the manifest')


def verify_pytest(path):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == 'testsuite' else list(root.iter('testsuite'))
    count = sum(int(suite.attrib.get('tests', 0)) for suite in suites)
    require(count > 0, 'Pytest recorded no software tests')
    require(all(int(suite.attrib.get(key, 0)) == 0 for suite in suites
                for key in ('failures', 'errors', 'skipped')),
            'Pytest recorded failures, errors or skipped tests')
    return count


def compare_saved_reports(current, retained):
    current_paths = {p.parent.name: p for p in current.glob('*/result.json')}
    retained_paths = {p.parent.name: p for p in retained.glob('*/result.json')}
    require(bool(current_paths) and current_paths.keys() == retained_paths.keys(),
            'Replay report set differs: ' + current.name)
    matches = {}
    for name, path in sorted(current_paths.items()):
        actual, expected = read_json(path), read_json(retained_paths[name])
        actual_checks = {c['id']: c['status'] for c in actual['checks']}
        expected_checks = {c['id']: c['status'] for c in expected['checks']}
        matches[name] = actual['verdict'] == expected['verdict'] and actual_checks == expected_checks
        require(matches[name], 'Replay decision or check status differs: ' + name)
    return matches


def compare_physics(actual, expected):
    require(actual['cases'].keys() == expected['cases'].keys(), 'Physics case set differs')
    matches = {}
    for name, case in actual['cases'].items():
        saved = expected['cases'][name]
        require(case['configuration'] == saved['configuration'], 'Physics configuration differs: ' + name)
        require(len(case['runs']) == len(saved['runs']), 'Physics run count differs: ' + name)
        for index, (run, old) in enumerate(zip(case['runs'], saved['runs'])):
            value, reference = run['final_displacement_m'], old['final_displacement_m']
            key = name + ':' + str(index)
            matches[key] = (math.isfinite(value) and math.isfinite(reference)
                            and abs(value - reference) < 1e-9
                            and run['dt_s'] == old['dt_s']
                            and run['behavior'] == old['behavior'])
            require(matches[key], 'Physics observation or decision differs: ' + key)
    require(bool(matches), 'No physics observations were compared')
    return matches


def summarize(root, out, manifest, implementation_digest):
    checks = {}
    test_count = verify_pytest(out / 'pytest.xml')
    packs = read_json(out / 'packs/summary.json')
    mesh = read_json(out / 'mesh/summary.json')
    for name, summary, expected_count, retained in (
        ('packs', packs, 22, 'evaluation/packs-v1/runs/final'),
        ('mesh', mesh, 32, 'evaluation/mesh-v1/runs/final-comparison'),
    ):
        checks[name + '_case_count'] = require(
            summary['summary']['matches'] == summary['summary']['cases'] == expected_count,
            name + ' case counts or expected outcomes differ')
        checks[name + '_decisions'] = all(compare_saved_reports(out / name, root / retained).values())

    content = read_json(out / 'content/summary.json')
    checks['content'] = require(len(content) == 4 and all(x['matched'] for x in content.values()),
                                'Content probe outcomes differ')
    timing = read_json(out / 'timing/summary.json')
    checks['timing'] = require(timing['matches'] == timing['cases'] == 17, 'Timing outcomes differ')
    consolidation = read_json(out / 'consolidation/summary.json')
    checks['consolidation'] = require(len(consolidation) == 21 and all(x['matched'] for x in consolidation),
                                      'Consolidation outcomes differ')
    reader_reports = read_json(out / 'reader-reports/summary.json')
    checks['reader_reports'] = require(len(reader_reports) == 4, 'Reader report count differs')
    brief_reports = read_json(out / 'brief-reports/results.json')
    checks['brief_reports'] = require(
        len(brief_reports['rows']) == 5 and brief_reports['unchanged']
        and [row['scope'] for row in brief_reports['rows']] == [
            'No brief supplied', 'ACCEPT_FOR_DECLARED_SCOPE', 'ACCEPT_FOR_DECLARED_SCOPE',
            'REJECT', 'NEEDS_REVIEW'], 'Brief report outcomes or input integrity differ')
    physics = read_json(out / 'physics/summary.json')
    checks['physics_expected'] = require(physics['all_expected_matched'], 'Physics expected outcomes differ')
    checks['physics_observations'] = all(compare_physics(
        physics, read_json(root / 'article-evidence/physics-experiment/runs/first/summary.json')).values())
    retained = verify_files(root, manifest)
    checks['retained_files'] = all(retained.values())
    digest = implementation_digest()
    checks['installed_checker'] = verify_checker(digest, manifest['checker_sha256'])
    return {
        'checker_sha256': digest, 'retained_files_verified': len(retained),
        'software_tests': test_count, 'pack_cases': packs['summary']['cases'],
        'mesh_cases': mesh['summary']['cases'], 'timing_cases': timing['cases'],
        'consolidation_cases': len(consolidation), 'reader_report_cases': len(reader_reports),
        'brief_report_cases': len(brief_reports['rows']), 'content_probes': len(content),
        'physics_configuration_cases': len(physics['cases']),
        'simulator_runs': sum(len(case['runs']) for case in physics['cases'].values()),
        'model_calls': 0, 'verification_checks': checks,
        'decisions_and_recorded_physics_observations_match': bool(checks) and all(checks.values()),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    out = Path(parser.parse_args(argv).out).resolve()
    if out == ROOT or ROOT in out.parents:
        parser.error('Choose output outside the companion')
    out.mkdir(parents=True, exist_ok=False)
    manifest = read_json(ROOT / 'MANIFEST.json')
    verify_files(ROOT, manifest)
    from scene_acceptance.engine import implementation_digest
    verify_checker(implementation_digest(), manifest['checker_sha256'])

    def run(name, command):
        with (out / (name + '.log')).open('w') as log:
            subprocess.run([sys.executable, *command], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                           check=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    run('pytest', ['-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--junitxml', str(out / 'pytest.xml'), 'tests'])
    verify_pytest(out / 'pytest.xml')
    for name, script in (
        ('packs', 'evaluation/packs-v1/run.py'), ('mesh', 'evaluation/mesh-v1/run.py'),
        ('timing', 'evaluation/motion-timing-v1/run.py'), ('consolidation', 'evaluation/consolidation-v1/run.py'),
        ('reader-reports', 'evaluation/report-context-v1/run.py'), ('brief-inputs', 'evaluation/brief-study-v1/prepare.py'),
    ):
        run(name, [script, '--out', str(out / name)])
    run('brief-reports', ['evaluation/brief-study-v1/run_saved.py', '--inputs', str(out / 'brief-inputs'),
                          '--out', str(out / 'brief-reports')])
    run('content', ['article-evidence/run-content-probes.py', str(out / 'content')])
    run('physics', ['article-evidence/physics-experiment/run.py', str(out / 'physics')])
    result = summarize(ROOT, out, manifest, implementation_digest)
    (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        raise SystemExit('Verification failed: ' + str(exc))
