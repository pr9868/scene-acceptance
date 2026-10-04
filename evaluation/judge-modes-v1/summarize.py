"""Build a readable index from retained outcomes; never invoke a model or change a result."""
import argparse
from collections import Counter
import csv
from html import escape
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def E(value):
    return escape(str(value), quote=True)


def summarize(root):
    plan=read(root/'plan.json')
    if not (root/'results.json').exists():
        raise ValueError('Wait for every scheduled case; pending reviews cannot be silently omitted')
    rows=[];concerns=[];bounded=[];errors=[]
    for job in plan:
        folder=root/'runs'/job['id'];receipt=read(folder/'receipt.json');result=read(folder/'evaluation/evaluation.json')
        core_dir=folder/'evaluation/script';core_dir=core_dir/'report' if job['brief'] else core_dir
        core=read(core_dir/('core-result.json' if job['brief'] else 'result.json'))
        checks=result['script']['checks'];general=next(m for m in result['script']['matrix'] if m['id']=='general')
        target=[c for c in checks if c['id'].startswith('spec.')]
        measured=Counter(c['status'] for c in target)
        opinions=result['judge']['findings'];inventory=result['scene']['inventory']
        row=dict(id=job['id'],scene_id=job['scene_id'],phase=job['phase'],family=job['task'],creation_brief=job['level'],
                 repetition=job['repetition'],evaluation_brief='full target' if job['brief'] else 'none',
                 exposure=job['exposure'],geometry_prims=inventory['boundables'],prims=inventory['prims'],meshes=inventory['meshes'],
                 general=general,full_target=dict(measured),full_target_checks=len(target),
                 artifact_verdict=result['script']['artifact_verdict'],scope_verdict=result['script']['declared_scope_verdict'],
                 execution_status=result['execution_status'],judge_status=result['judge']['status'],decision=result['decision'],
                 opinions=result['judge']['counts'],elapsed_seconds=receipt['elapsed_seconds'],usage=result['judge'].get('usage'),
                 errors=result['errors'],source_unchanged=result['source_unchanged'],
                 findings=opinions,report=f"runs/{job['id']}/evaluation/report.html")
        rows.append(row)
        for item in opinions:
            item=dict(case=job['id'],scene_id=job['scene_id'],phase=job['phase'],**item)
            if item['assessment']=='concern': concerns.append(item)
            if item.get('model_assessment',item['assessment'])!=item['assessment']:bounded.append(item)
        errors.extend(dict(case=job['id'],error=e) for e in result['errors'])
    primary=[r for r in rows if r['phase']=='primary'];by_id={r['id']:r for r in rows};repeats=[]
    for r in rows:
        if r['phase']!='repeat':continue
        original=by_id[r['scene_id']]
        before={i['requirement_id']:i for i in original['findings']};after={i['requirement_id']:i for i in r['findings']}
        changed=[dict(item=k,first=before[k]['assessment'],repeat=after[k]['assessment']) for k in before.keys()&after.keys()
                 if before[k]['assessment']!=after[k]['assessment']]
        repeats.append(dict(scene_id=r['scene_id'],repeat_id=r['id'],first_status=original['judge_status'],repeat_status=r['judge_status'],
                            comparable_items=len(before.keys()&after.keys()),changed=changed))
    counts=Counter();[counts.update(r['opinions']) for r in primary]
    general_status=Counter();[general_status.update({k:r['general'][k] for k in ('pass','warning','fail','unknown','not_applicable','error')}) for r in primary]
    summary=dict(primary_scenes=len(primary),planned_reviews=len(rows),completed_reviews=sum(r['judge_status']=='completed' for r in rows),
                 primary_completed=sum(r['judge_status']=='completed' for r in primary),primary_opinions=dict(counts),
                 primary_general_rule_outcomes=dict(general_status),primary_script_rejections=sum(r['artifact_verdict']=='REJECT' or r['scope_verdict']=='REJECT' for r in primary),
                 repeated_reviews=repeats,context_probes=[r['id'] for r in rows if r['phase']=='context'],
                 evidence_bounded_opinions=len(bounded),errors=errors,rows=rows,concerns=concerns,bounded=bounded,
                 limitation='Opinions are advisory. Counts are correlated criterion assessments, not assets or a calibrated detection rate. Script-aware agreement is not independent rediscovery.')
    save(root/'analysis.json',summary)
    with (root/'matrix.csv').open('w',newline='') as f:
        fields=['id','phase','family','creation_brief','evaluation_brief','exposure','geometry_prims','meshes','general_pass','general_warning','general_fail','general_unknown','general_not_applicable','target_pass','target_fail','target_unknown','target_checks','judge_status','consistent','concern','unknown','decision','report']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in rows:
            line={k:r[k] for k in ('id','phase','family','creation_brief','evaluation_brief','exposure','geometry_prims','meshes','judge_status','decision','report')}
            line.update({'general_'+k:r['general'][k] for k in ('pass','warning','fail','unknown','not_applicable')})
            line.update({'target_'+k.lower():r['full_target'].get(k,0) for k in ('PASS','FAIL','UNKNOWN')});line['target_checks']=r['full_target_checks']
            line.update({k:r['opinions'].get(k,0) for k in ('consistent','concern','unknown')});writer.writerow(line)
    def link(r):return f'<a href="{E(r["report"])}">{E(r["id"])}</a>'
    def outcome(r):
        if r['judge_status']!='completed':return E(r['judge_status'])
        c=r['opinions'];return f'{c.get("consistent",0)} consistent · {c.get("concern",0)} concern · {c.get("unknown",0)} unknown'
    def table(case_rows):
        body=''
        for r in case_rows:
            g=r['general'];t=r['full_target'];issues=', '.join(x['requirement_id'].replace('review.','').replace('brief.','brief: ') for x in r['findings'] if x['assessment']=='concern') or 'No concern opinion'
            if r['judge_status']!='completed':issues='Review unavailable; see error record'
            body+=f'<tr><th>{link(r)}<small>{E(r["geometry_prims"])} geometry prims · {E(r["meshes"])} meshes</small></th><td>{E(r["creation_brief"])}</td><td>{g["pass"]} / {g["warning"]} / {g["fail"]} / {g["unknown"]} / {g["not_applicable"]}</td><td>{t.get("PASS",0)} / {r["full_target_checks"]}<small>{t.get("FAIL",0)} fail · {t.get("UNKNOWN",0)} unknown</small></td><td>{outcome(r)}</td><td>{E(issues)}</td></tr>'
        return '<div class="scroll" tabindex="0"><table><thead><tr><th>Scene and structure</th><th>Created with</th><th>General<br>pass / warn / fail / unknown / N/A</th><th>Full-target checks passed</th><th>Model opinions</th><th>Concern area</th></tr></thead><tbody>'+body+'</tbody></table></div>'
    repeat_html=''
    for x in repeats:
        changes='; '.join(f'{i["item"]}: {i["first"]} → {i["repeat"]}' for i in x['changed']) or 'No opinion category changed'
        repeat_html+=f'<tr><th>{E(x["scene_id"])}</th><td>{x["comparable_items"]}</td><td>{E(changes)}</td><td>{link(by_id[x["repeat_id"]])}</td></tr>'
    concern_html=''
    corroboration_path=root/'corroboration.json';corroboration=read(corroboration_path) if corroboration_path.exists() else {'items':[]}
    for c in concerns:
        independent=next((x for x in corroboration['items'] if x['case']==c['case'] and x['requirement_id']==c['requirement_id']),None)
        follow=(independent['status']+': '+independent['explanation']) if independent else 'Unverified advisory claim; no separate corroboration recorded'
        concern_html+=f'<tr><th>{link(by_id[c["case"]])}<small>{E(c["requirement_id"])}</small></th><td>{E(c["explanation"])}<small>{E(", ".join(c["evidence_ids"]))}</small></td><td>{E(follow)}'+(f'<small><a href="{E(independent["evidence"])}">Follow-up evidence</a></small>' if independent and independent.get('evidence') else '')+'</td></tr>'
    errors_html=''.join(f'<li>{E(x["case"])}: {E(x["error"])}</li>' for x in errors) or '<li>No model execution failures in this batch.</li>'
    limits='''<ul><li>All primary reviews see the full target brief. A target withheld during creation is a later alignment test, not an ignored instruction.</li><li>The 10 target tests measure selected requirements. They do not cover every sentence or all 62–70 visible geometry objects.</li><li>Three schematic views provide geometry and limited frame-to-frame evidence. They do not show real surface textures, lighting, continuous motion or validated physics.</li><li>Default reviewers do not see script outcomes. Numeric requirements without measurement evidence remain unknown; the scripts still assess them.</li><li>Model opinions do not change measured failures, approve a human review, or certify a machine. A traceable citation can still support a mistaken explanation.</li><li>These synthetic briefs, rubric and initial review follow-ups are assistant-authored. This is not an independent quality benchmark.</li></ul>'''
    intro=f'<p class="eyebrow">Local implementation study · 3 October 2026</p><h1>What the checks found, and what the model could review</h1><p>One CLI, two separate evidence channels. {len(primary)} unchanged synthetic scene deliveries were evaluated with the general rules and full target brief. The optional reviewer saw saved evidence with script outcomes withheld.</p><div class="cards"><article><b>{summary["completed_reviews"]} / {len(rows)}</b><span>model reviews completed</span></article><article><b>{summary["primary_script_rejections"]} / {len(primary)}</b><span>primary scenes rejected by script scope</span></article><article><b>{counts.get("concern",0)}</b><span>primary concern opinions; not proven defects</span></article></div>'
    context_rows=[by_id['gantry-detailed-02']]+[r for r in rows if r['phase']=='context']
    context_html=''
    for r in context_rows:context_html+=f'<tr><th>{link(r)}</th><td>{E(r["evaluation_brief"])}</td><td>{E(r["exposure"])}</td><td>{outcome(r)}</td></tr>'
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Scene harness — script and model review study</title><style>
:root{{color-scheme:light;font:16px/1.55 system-ui,sans-serif;color:#182b36;background:#f5f7f8}}body{{margin:0}}main{{max-width:1240px;margin:auto;padding:32px 24px 72px}}h1{{font-size:clamp(1.8rem,4vw,2.7rem);line-height:1.15;max-width:900px}}h2{{margin-top:2.6rem}}p{{max-width:980px}}a{{color:#075a78}}.eyebrow{{color:#526974;font-size:.85rem}}.cards{{display:flex;gap:16px;flex-wrap:wrap;margin:25px 0}}.cards article{{background:white;border:1px solid #d6e0e4;border-radius:8px;padding:18px;flex:1;min-width:185px}}b{{display:block;font-size:1.8rem}}span,small{{display:block}}small{{font-weight:400;color:#536570;font-size:.78rem;margin-top:5px}}.scroll{{max-width:100%;overflow:auto;border:1px solid #d6e0e4;border-radius:7px;background:white}}table{{border-collapse:collapse;width:100%;font-size:.88rem;min-width:880px}}th,td{{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #dbe3e6}}thead{{background:#e7eff2}}th{{font-weight:600}}td{{overflow-wrap:anywhere}}.notes{{padding:18px 22px;background:#eaf1f3;border-radius:8px}}li{{margin:8px 0}}.links{{font-size:.9rem}}@media(max-width:600px){{main{{padding:22px 16px 48px}}.cards{{gap:8px}}.cards article{{min-width:0;flex-basis:100%}}}}
</style></head><body><main>{intro}<p class="links"><a href="matrix.csv">Download table</a> · <a href="analysis.json">All results and opinions</a> · <a href="frozen-study/PROTOCOL.md">Frozen protocol</a> · <a href="verification.json">Verification receipt</a> · <a href="../ADMISSION_AMENDMENT.md">View-input correction</a> · <a href="../review-v2/HOST_AMENDMENT.md">Host-launch record</a></p><div class="notes"><strong>How to read this report</strong><p>General counts are outcomes across 27 rules, not counts of accepted assets. Full-target counts are the 10 selected requirement checks. Model counts use a different unit: advisory items. Open a scene for exact subjects, observed/expected values, images and model explanations.</p></div>
<h2>All 24 scenes</h2>{table(sorted(primary,key=lambda r:(r['family'],['simple','light','medium','detailed'].index(r['creation_brief']),r['repetition'])))}
<h2>Same scene, different context</h2><p>The full-brief blind review, no-brief review and script-aware review use the same gantry delivery. Script-aware agreement is assisted interpretation, not independent detection.</p><div class="scroll"><table><tr><th>Review</th><th>Analysis brief</th><th>Script exposure</th><th>Model opinions</th></tr>{context_html}</table></div>
<h2>Repeated opinions</h2><p>Each chosen detailed scene was reviewed twice from fresh contexts with the same evidence content. Both answers are retained; no majority vote or preferred answer is selected.</p><div class="scroll"><table><tr><th>Scene</th><th>Comparable items</th><th>Opinion-category changes</th><th>Second review</th></tr>{repeat_html}</table></div>
<h2>Exact concerns and follow-up</h2><p>These are the model's own explanations, including any uncertain or mistaken interpretation. Corroboration is a separate retained measurement or source inspection; it never rewrites the model response.</p><div class="scroll"><table><tr><th>Review and item</th><th>Model explanation and citations</th><th>Separate follow-up</th></tr>{concern_html or '<tr><td colspan="3">No concern opinions.</td></tr>'}</table></div>
<h2>What remains unassessed</h2>{limits}<p>{len(bounded)} raw opinions were changed to unknown because their citations did not satisfy the declared evidence requirement. Raw and effective opinions remain side by side in each report.</p><h2>Execution record</h2><ul>{errors_html}</ul><p>The initial image-limit failures and subsequent host-launch failures are retained separately; neither produced a model response. The final batch never retries or replaces a model answer.</p></main></body></html>'''
    (root/'index.html').write_text(html)
    markdown=['# Script and model review study','',f'{summary["completed_reviews"]}/{len(rows)} model reviews completed; {summary["primary_completed"]}/24 primary reviews completed. Primary opinions: '+str(dict(counts))+'.','',summary['limitation'],'','| Scene | Creation brief | Geometry prims | General P/W/F/?/N/A | Full target passed | Model consistent/concern/unknown |','|---|---|---:|---|---|---|']
    for r in sorted(primary,key=lambda r:r['id']):
        g=r['general'];c=r['opinions'];markdown.append(f'| [{r["id"]}]({r["report"]}) | {r["creation_brief"]} | {r["geometry_prims"]} | '+ '/'.join(str(g[k]) for k in ('pass','warning','fail','unknown','not_applicable'))+f' | {r["full_target"].get("PASS",0)}/{r["full_target_checks"]} | '+ '/'.join(str(c.get(k,0)) for k in ('consistent','concern','unknown'))+' |')
    markdown+=['','Read [the interactive report](index.html) for context probes, repeats, exact concerns and limits. Raw and effective opinions remain in [analysis.json](analysis.json).']
    (root/'RESULTS.md').write_text('\n'.join(markdown)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('rows','concerns','bounded')}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();summarize(a.root.resolve())
