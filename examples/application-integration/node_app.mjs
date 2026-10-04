// Example host application. A process argument array preserves spaces in paths.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';

export function checkScene(request) {
  const out = resolve(request.out);
  const brief = request.brief;
  const args = ['--bundle-root', resolve(request.bundle_root),
    '--candidate', request.candidate, '--out', out];
  if (brief != null) args.push('--brief', brief);
  for (const key of ['mode', 'judge_config', 'views', 'rubric', 'judge_exposure'])
    if (request[key] != null) args.push('--' + key.replaceAll('_', '-'), request[key]);
  const child = spawnSync(request.harness, args, {
    encoding: 'utf8', shell: false,
    timeout: (request.timeout_seconds ?? 120) * 1000,
    maxBuffer: 8 * 1024 * 1024,
  });
  if (child.error || child.signal) return {
    status: 'invocation_error', process_exit_code: child.status,
    error: String(child.error ?? `Process ended with signal ${child.signal}`),
  };
  try {
    const summary = JSON.parse(child.stdout);
    if (request.mode != null) {
      const report = join(out, 'report.html'), resultPath = join(out, 'evaluation.json');
      if (!existsSync(report) || realpathSync(summary.report) !== realpathSync(report) || realpathSync(summary.result) !== realpathSync(resultPath))
        throw new Error('Unified report paths disagree');
      const result = JSON.parse(readFileSync(resultPath, 'utf8'));
      const expected = {ACCEPT_FOR_USE:0, ACCEPT_FOR_DECLARED_SCOPE:0, REJECT:2, NEEDS_REVIEW:3, EVALUATION_ERROR:4}[result.decision];
      if (result.schema_version !== '1.0' || result.mode !== request.mode || result.decision !== summary.decision || result.execution_status !== summary.execution_status || expected !== child.status || result.exit_code !== child.status)
        throw new Error('Unified process status and assessment disagree');
      return {status:'reported', process_exit_code:child.status, artifact_verdict:result.script.artifact_verdict,
        declared_scope_verdict:result.script.declared_scope_verdict, judge_status:result.judge.status,
        report:realpathSync(report), result, diagnostics:child.stderr};
    }
    const directory = brief != null ? join(out, 'report') : out;
    const report = join(directory, 'report.html');
    if (!existsSync(report) || realpathSync(summary.report) !== realpathSync(report))
      throw new Error('No completed report at the expected output path');
    const core = join(directory, 'core-result.json');
    const result = JSON.parse(readFileSync(existsSync(core) ? core : join(directory, 'result.json'), 'utf8'));
    const artifact = summary.core_verdict ?? summary.verdict;
    const scope = summary.assessment_verdict ?? null;
    const expected = {
      ACCEPT_FOR_USE: 0, ACCEPT_FOR_DECLARED_SCOPE: 0, REJECT: 2,
      INSUFFICIENT_EVIDENCE: 3, NEEDS_REVIEW: 3, EVALUATION_ERROR: 4,
    }[brief != null ? scope : artifact];
    if (expected === undefined || expected !== child.status || result.verdict !== artifact)
      throw new Error('Process status and saved assessment disagree');
    const assessmentFile = join(directory, 'assessment.json');
    return {
      status: 'reported', process_exit_code: child.status,
      artifact_verdict: artifact, declared_scope_verdict: scope,
      report: realpathSync(report), result,
      assessment: existsSync(assessmentFile) ? JSON.parse(readFileSync(assessmentFile, 'utf8')) : null,
      diagnostics: child.stderr,
    };
  } catch (error) {
    return { status: 'invocation_error', process_exit_code: child.status,
      error: String(error), diagnostics: child.stderr, raw_stdout: child.stdout };
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const response = checkScene(JSON.parse(readFileSync(process.argv[2], 'utf8')));
  console.log(JSON.stringify(response, null, 2));
  process.exitCode = response.status === 'reported' ? response.process_exit_code : 4;
}
