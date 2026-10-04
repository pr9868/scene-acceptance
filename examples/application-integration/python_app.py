"""Example host application calling the installed harness; no shell or HTTP server."""
import json
from pathlib import Path
import subprocess
import sys


def check_scene(request):
    out = Path(request['out']).expanduser().resolve()
    bundle = Path(request['bundle_root']).expanduser().resolve()
    brief = request.get('brief')
    argv = [request['harness'], '--bundle-root', str(bundle),
            '--candidate', request['candidate'], '--out', str(out)]
    if brief is not None:
        argv += ['--brief', brief]
    for field in ('mode','judge_config','views','rubric','judge_exposure'):
        if request.get(field) is not None: argv += ['--'+field.replace('_','-'),request[field]]
    try:
        process = subprocess.run(argv, capture_output=True, text=True,
                                 timeout=request.get('timeout_seconds', 120), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(status='invocation_error', process_exit_code=None, error=str(exc))
    try:
        summary = json.loads(process.stdout)
        if request.get('mode') is not None:
            report=out/'report.html'; result_path=out/'evaluation.json'
            if Path(summary['report']).resolve()!=report or Path(summary['result']).resolve()!=result_path or not report.is_file():
                raise ValueError('Unified report paths disagree')
            result=json.loads(result_path.read_text())
            expected={'ACCEPT_FOR_USE':0,'ACCEPT_FOR_DECLARED_SCOPE':0,'REJECT':2,'NEEDS_REVIEW':3,'EVALUATION_ERROR':4}.get(result['decision'])
            if result['schema_version']!='1.0' or result['mode']!=request['mode'] or result['decision']!=summary['decision'] or result['execution_status']!=summary['execution_status'] or expected!=process.returncode or result['exit_code']!=process.returncode:
                raise ValueError('Unified process status and assessment disagree')
            return dict(status='reported',process_exit_code=process.returncode,artifact_verdict=result['script']['artifact_verdict'],
                        declared_scope_verdict=result['script']['declared_scope_verdict'],judge_status=result['judge']['status'],
                        report=str(report),result=result,diagnostics=process.stderr)
        directory = out / 'report' if brief is not None else out
        report = directory / 'report.html'
        if Path(summary['report']).resolve() != report or not report.is_file():
            raise ValueError('No completed report at the expected output path')
        result_path = directory / 'core-result.json'
        if not result_path.is_file():
            result_path = directory / 'result.json'
        result = json.loads(result_path.read_text())
        artifact = summary.get('core_verdict', summary.get('verdict'))
        scope = summary.get('assessment_verdict')
        verdict = scope if brief is not None else artifact
        expected = {'ACCEPT_FOR_USE': 0, 'ACCEPT_FOR_DECLARED_SCOPE': 0,
                    'REJECT': 2, 'INSUFFICIENT_EVIDENCE': 3, 'NEEDS_REVIEW': 3,
                    'EVALUATION_ERROR': 4}.get(verdict)
        if expected is None or expected != process.returncode or result['verdict'] != artifact:
            raise ValueError('Process status and saved assessment disagree')
        assessment_path = directory / 'assessment.json'
        assessment = json.loads(assessment_path.read_text()) if assessment_path.is_file() else None
        return dict(status='reported', process_exit_code=process.returncode,
                    artifact_verdict=artifact, declared_scope_verdict=scope,
                    report=str(report), result=result, assessment=assessment,
                    diagnostics=process.stderr)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return dict(status='invocation_error', process_exit_code=process.returncode,
                    error=str(exc), diagnostics=process.stderr, raw_stdout=process.stdout)


if __name__ == '__main__':
    response = check_scene(json.loads(Path(sys.argv[1]).read_text()))
    print(json.dumps(response, indent=2))
    sys.exit(response['process_exit_code'] if response['status'] == 'reported' else 4)
