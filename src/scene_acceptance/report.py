"""Human-readable coverage plus portable, traceable JSON/CSV evidence."""
from pathlib import Path
import csv
import html
import json
from .model import sha
from .coverage import summarize_observations
from .reader_report import build_overview, render_overview, markdown_overview, write_overview, STYLE as READER_STYLE

STYLE='''body{font:15px/1.55 system-ui,sans-serif;color:#21313b;background:#f7f9fb;margin:0}main{max-width:1400px;margin:32px auto;padding:0 24px}h1{font-size:30px;line-height:1.2}h2{margin-top:32px}p{max-width:100ch}.scope{padding:16px;border-left:4px solid #3273a4;background:#edf4fa}.cards{display:flex;gap:12px;flex-wrap:wrap}.card{background:white;border:1px solid #d6dee5;border-radius:6px;padding:12px 20px}.card strong{display:block;font-size:24px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px;background:white}td,th{border:1px solid #d6dee5;text-align:left;padding:9px;vertical-align:top}th{background:#eaf0f5;white-space:nowrap}td:first-child{min-width:180px}.PASS,.ACCEPT_FOR_USE{color:#21633f}.FAIL,.REJECT,.ERROR,.EVALUATION_ERROR{color:#a02e25}.UNKNOWN,.PARTIAL_COVERAGE,.PASS_WITH_WARNINGS,.INSUFFICIENT_EVIDENCE{color:#805916}.NO_APPLICABLE_SUBJECTS,.NOT_SELECTED{color:#596974}a{color:#145e91}code,pre{font-size:12px;overflow-wrap:anywhere}pre{white-space:pre-wrap}details{margin-top:8px}small{display:block;color:#536472}input,select{font:inherit;padding:8px;margin:0 8px 12px 0;border:1px solid #aebbc6;border-radius:4px}footer{margin-top:32px;color:#526473}li{margin:6px 0}.inventory td:first-child{min-width:0}'''
E=lambda x:html.escape(str(x),quote=True)


def cell(value):
    # CSV remains safe to open in a spreadsheet. JSON retains exact original text.
    s='' if value is None else str(value)
    return "'"+s if s.lstrip().startswith(('=','+','-','@','\t','\r')) else s


def csv_file(path,fields,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        for row in rows: writer.writerow({k:cell(row.get(k)) for k in fields})


def evidence_rows(report):
    plan={p['id']:p for p in report['coverage'].get('planned',[])}
    subjects=[];findings=[]
    for i,r in enumerate(report['checks']):
        obs=r.get('evidence',{}).get('observations',{})
        if not isinstance(obs,dict): continue
        base=f'/checks/{i}/evidence/observations'
        a=summarize_observations(plan[r['id']],r) if r['id'] in plan else None
        if a:
            for j,row in enumerate(a['items']):
                if 'assessment' in obs: pointer=base+f'/assessment/items/{j}'
                elif 'findings' in obs and 'evidence_index' in row: pointer=base+f'/findings/{row["evidence_index"]}'
                elif 'samples' in obs and 'evidence_index' in row: pointer=base+f'/samples/{row["evidence_index"]}'
                else: pointer=base
                subjects.append(dict(check_id=r['id'],unit=a['unit'],subject=row['subject'],status=row['status'],
                                     reason=row.get('reason',''),evidence_pointer=pointer))
        for key in ('issues','findings'):
            for j,row in enumerate(obs.get(key,[])):
                if not isinstance(row,dict): continue
                if key=='findings' and row.get('status')=='PASS': continue
                findings.append(dict(kind='provider_observation',check_id=r['id'],severity=row.get('severity',row.get('status','')),
                    subject=row.get('at',row.get('object','')),message=row.get('message',row.get('reason','')),
                    evidence_pointer=base+f'/{key}/{j}'))
        if a and 'assessment' in obs:
            for j,row in enumerate(a['items']):
                if row['status']!='PASS':
                    findings.append(dict(kind='subject_outcome',check_id=r['id'],severity=row['status'],subject=row['subject'],
                        message=row.get('reason','See provider issue and check scope'),evidence_pointer=base+f'/assessment/items/{j}'))
    return subjects,findings


def write_report(report,out, *, include_overview=True):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    (out/'result.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    overview = build_overview(report)
    reader_checks={r['id']:r for r in overview['checks']}
    write_overview(overview,out,csv_file)
    audit=report['coverage'].get('audit',{})
    rows=audit.get('rows',[])
    plan={p['id']:p for p in report['coverage'].get('planned',[]) if isinstance(p,dict)}
    by_id={r['id']:r for r in report['checks']}
    fields=['id','pack','check','required','status','contract_status','unit','candidate_count','assessed_count',
            'pass_count','fail_count','warning_count','unknown_count','error_count','skipped_count','reason','evidence_pointer']
    csv_file(out/'checks.csv',fields,[{**r,**(r['counts'] or {})} for r in rows])
    subjects,findings=evidence_rows(report)
    csv_file(out/'subjects.csv',['check_id','unit','subject','status','reason','evidence_pointer'],subjects)
    csv_file(out/'findings.csv',['kind','check_id','severity','subject','message','evidence_pointer'],findings)
    if 'contract' in report['identity']:
        (out/'contract.json').write_text(json.dumps(report['identity']['contract'],indent=2)+'\n')
    counts=audit.get('check_outcomes',{})
    cards=''.join(f'<div class="card"><strong>{n}</strong>{E(label.replace("_"," ").lower())}</div>' for label,n in counts.items())
    inv=report['coverage'].get('inventory')
    inv_html='<p>Inventory unavailable: admission did not complete. Counts are unknown.</p>'
    if inv:
        data={k:v for k,v in inv.items() if isinstance(v,int)}
        inv_html='<div class="scroll"><table class="inventory"><tbody>'+''.join(f'<tr><th>{E(k.replace("_"," "))}</th><td>{v}</td></tr>' for k,v in data.items())+'</tbody></table></div><p>'+E(inv['scope'])+'</p>'
    domain_html=''.join(f'<tr><td>{E(r["domain"].replace("_"," "))}</td><td class="{E(r["status"])}">{E(r["status"])}</td><td>{E(r["note"])}<small>{E(", ".join(r["checks"]) or "No selected check")}</small></td></tr>' for r in audit.get('domains',[]))
    result_rows=[]
    for r in rows:
        c=r['counts']; original=by_id[r['id']];params=plan[r['id']]['parameters']
        label=reader_checks[r['id']]['label']
        obs=original.get('evidence',{}).get('observations',{})
        measurement=''
        if isinstance(obs,dict):
            if 'maximum_sampled_gap_m' in obs:
                measurement=f"Maximum sampled gap: {obs['maximum_sampled_gap_m']*1000:.6g} mm; allowed: {obs['max_gap_m']*1000:.6g} mm; worst sample: {obs['worst_elapsed_s']:.6g} s."
            elif 'maximum_recomputed_displacement_m' in obs:
                measurement=f"Maximum displacement: {obs['maximum_recomputed_displacement_m']*1000:.6g} mm; allowed: {params['maximum_displacement_m']*1000:.6g} mm; trajectory samples: {len(obs.get('worker',{}).get('trace',[]))}."
            elif all(k in obs for k in ('format','width','height')):
                measurement=f"{obs['format']}: {obs['width']} × {obs['height']} pixels."
        samples=[x for x in findings if x['check_id']==r['id']][:5]
        examples=''.join(f'<li><code>{E(x["subject"])}</code> — {E(x["message"])}</li>' for x in samples)
        extra=f'<details><summary>Scope, parameters and example findings</summary><p>{E(r["scope"])}</p><pre>{E(json.dumps(params,indent=2))}</pre><ul>{examples}</ul><p>Full evidence: <a href="result.json">result.json</a> <code>{E(r["evidence_pointer"])}</code>. All subject outcomes are in subjects.csv.</p></details>'
        nums=''.join(f'<td>{c[k] if c else "—"}</td>' for k in ('candidate_count','assessed_count','pass_count','fail_count','warning_count','unknown_count','error_count','skipped_count'))
        result_rows.append(f'<tr data-status="{E(r["status"])}"><td>{E(label)}<small>{E(r["id"])} · {"Required" if r["required"] else "Advisory"}</small></td><td class="{E(r["status"])}">{E(r["status"])}<small>Contract: {E(r["contract_status"])}</small></td><td>{E(r["unit"])}</td>{nums}<td>{E(r["reason"])}<p>{E(measurement)}</p>{extra}</td></tr>')
    if not rows:
        result_rows=[f'<tr><td>{E(r["id"])}</td><td>{E(r["status"])}</td><td colspan="10">{E(r["reason"])}</td></tr>' for r in report['checks']]
    core_rows=''.join(f'<li><strong>{E(r["id"])}: {E(r["status"])}</strong> — {E(r["reason"])}</li>' for r in report['checks'] if r['id'].startswith('core.'))
    note=audit.get('counting_note','Legacy report: per-object denominators were not recorded.')
    md=[f'# Scene acceptance: {report["verdict"]}', '',f'Use: {report["intended_use"]}',
        f'Required evidence complete: {report["complete"]}. Selected checks: {len(rows)}.', '',note,'',
        '| Check | Result | Unit | Candidates | Assessed | Pass | Fail | Warn | Unknown | Error | Skipped |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        c=r['counts'] or {}; md.append('| '+' | '.join(str(x).replace('|','\\|').replace('\n',' ') for x in [r['id'],r['status'],r['unit']]+[c.get(k,'—') for k in ('candidate_count','assessed_count','pass_count','fail_count','warning_count','unknown_count','error_count','skipped_count')])+' |')
    md+=['','## Coverage by area','','| Area | Coverage | Limit |','|---|---|---|']
    md += ['| '+ ' | '.join(r[k].replace('|','\\|') for k in ('domain','status','note'))+' |' for r in audit.get('domains',[])]
    md+=['','[Full JSON](result.json) · [Checks](checks.csv) · [Subject outcomes](subjects.csv) · [Findings and coverage gaps](findings.csv)','']
    if include_overview: md[4:4] = ['',markdown_overview(overview),'']
    (out/'summary.md').write_text('\n'.join(md))
    document=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Scene acceptance — {E(report['verdict'])}</title><style>{STYLE}</style></head><body><main>
<h1>What the harness checked</h1><h2 class="{E(report['verdict'])}">{E(report['verdict'])}</h2>
<p><strong>Scope:</strong> {E(report['intended_use'])}</p><p>Contract: {E(report['contract_id'])} · Required evidence complete: {E(report['complete'])} · {len(rows)} selected checks</p>
<p class="scope">This is acceptance within the recorded contract. No applicable subjects, provider skips and unselected areas are shown separately. A structural pass does not establish overall task success.</p>
{render_overview(overview) if include_overview else ''}
<div class="cards">{cards}</div><p>{E(note)}</p>
<h2>Coverage by area</h2><div class="scroll"><table><thead><tr><th>Area</th><th>Coverage</th><th>What this means</th></tr></thead><tbody>{domain_html}</tbody></table></div>
<h2>Checks and measured coverage</h2><label>Find a check <input id="search" type="search" placeholder="Rule, object or finding"></label><label>Show <select id="filter"><option value="all">All checks</option><option value="attention">Findings and coverage gaps</option><option value="PASS">Clean checks</option></select></label>
<div class="scroll" tabindex="0" role="region" aria-label="Detailed check results"><table id="checks"><thead><tr><th>Check</th><th>Result</th><th>Unit</th><th>Candidates</th><th>Assessed</th><th>Pass</th><th>Fail</th><th>Warn</th><th>Unknown</th><th>Error</th><th>Skipped</th><th>Finding and scope</th></tr></thead><tbody>{''.join(result_rows)}</tbody></table></div>
<p>Pass means no finding under that check. Warnings occupy their own subject category even when the contract permits them. “—” means the provider did not report a denominator. Findings may overlap on the same object.</p>
<h2>Input and execution</h2><ul>{core_rows}</ul><details><summary>Scene inventory</summary>{inv_html}</details>
<details><summary>Unchecked scope</summary><ul>{''.join('<li>'+E(x)+'</li>' for x in report['coverage']['unchecked'])}</ul></details>
<details><summary>Run identity</summary><pre>{E(json.dumps({k:v for k,v in report['identity'].items() if k in ('checker_sha256','contract_sha256','contract_encoding')},indent=2))}</pre></details>
<p><a href="summary.md">Readable summary</a> · <a href="checks.csv">Check table</a> · <a href="subjects.csv">All assessed subjects</a> · <a href="findings.csv">Findings and gaps</a> · <a href="result.json">Full JSON and identities</a> · <a href="manifest.json">File hashes</a></p>
<footer>Checker {E(report['checker_version'])}; OpenUSD {E(report['runtime']['usd'])}. Trusted local evaluation; selected runtime workers only.</footer></main>
<script>const rows=[...document.querySelectorAll('#checks tbody tr')];function filter(){{const q=document.querySelector('#search').value.toLowerCase(),s=document.querySelector('#filter').value;for(const r of rows){{r.hidden=!(r.textContent.toLowerCase().includes(q)&&(s==='all'||(s==='attention'?r.dataset.status!=='PASS':r.dataset.status===s)));}}}}document.querySelector('#search').addEventListener('input',filter);document.querySelector('#filter').addEventListener('change',filter);</script></body></html>'''
    document=document.replace('</style>',READER_STYLE+'</style>',1)
    (out/'report.html').write_text(document)
    (out/'manifest.json').write_text(json.dumps({'files':{p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()}},indent=2)+'\n')
