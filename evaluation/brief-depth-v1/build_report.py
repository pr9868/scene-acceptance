"""Readable local index; presentation only, never modifies experimental inputs/results."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from html import escape as esc
import json
from pathlib import Path
from urllib.parse import quote
from study import LEVELS, TASKS, save

LABELS={'coordinates':'Coordinates','base':'Base size/centre','count':'Part count','gap':'Cabinet gap','mover-size':'Mover size','clock':'Duration/clock','time-range':'Time range','endpoints':'Endpoints','trajectory':'21 positions','image':'Image pixels'}
INTRO={'simple':'Common output conventions; producer chooses dimensions, counts, timing, path and image.',
       'light':'Adds exact base dimensions/centre and repeated-part count.',
       'medium':'Adds cabinet gap, moving-part dimensions, duration, time range and two endpoints.',
       'detailed':'Adds a specified path with 21 checkpoints and an attached pixel reference.'}
STYLE='''
:root{color-scheme:light;--ink:#152936;--muted:#526575;--line:#d8e1e6;--blue:#185d88}
*{box-sizing:border-box}body{margin:0;background:#f7f9fa;color:var(--ink);font:16px/1.55 system-ui,sans-serif}
main{max-width:1380px;margin:auto;padding:32px 26px 70px}h1{font-size:clamp(28px,4vw,44px);line-height:1.15;max-width:900px;margin:12px 0 20px}h2{font-size:25px;margin:36px 0 10px}h3{font-size:19px;margin:0 0 10px}p{max-width:1040px;margin:10px 0 16px}a{color:var(--blue);text-underline-offset:3px}a:hover{color:#092f49}code{overflow-wrap:anywhere;font-size:.85em}small,.muted{color:var(--muted)}.eyebrow{font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}.card,article,.note{border:1px solid var(--line);background:white;border-radius:10px;padding:18px}.card strong{font-size:29px;display:block;overflow-wrap:anywhere}.note{border-left:4px solid #7fabbf}.scroll{overflow-x:auto;background:white;border:1px solid var(--line);border-radius:8px;margin:16px 0}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:11px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{background:#edf3f6;font-weight:650}tbody tr:last-child td{border-bottom:0}.matrix td{white-space:nowrap}.matrix td:first-child{white-space:normal;min-width:175px}.status{font-size:12px;display:inline-block;font-weight:650;border-radius:4px;padding:2px 7px;white-space:nowrap;background:#eef1f3;color:#354b59}.PASS,.ACCEPT,.ACCEPT_FOR_USE{background:#e0f3e8;color:#155632}.FAIL,.REJECT,.ERROR{background:#fae3df;color:#8a2818}.WARNING,.NEEDS_REVIEW,.UNKNOWN{background:#fff0cc;color:#735209}.NOT_SUPPLIED,.NO_APPLICABLE_SUBJECTS{background:#edf0f2;color:#465967}.filters{display:flex;gap:18px;flex-wrap:wrap;margin:16px 0}select{font:inherit;padding:7px 12px;border:1px solid #aebfc9;border-radius:4px;background:white}label{font-size:14px}.gallery{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.gallery img{width:100%;height:auto;border:1px solid var(--line);border-radius:5px}.gallery .texture{width:80px;height:80px;image-rendering:pixelated}.views{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.views img{width:100%;height:auto}details{margin:12px 0;border:1px solid var(--line);border-radius:6px;background:white;padding:12px}summary{cursor:pointer;font-weight:650}pre{font:12px/1.5 ui-monospace,monospace;max-height:520px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}.links{display:flex;flex-wrap:wrap;gap:10px 20px}.heat td{padding:9px 6px}.heat .status{font-size:11px}.nowrap{white-space:nowrap}.jump{scroll-margin-top:20px}.empty{padding:24px;color:var(--muted)}
@media(max-width:740px){main{padding:22px 14px}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.card{padding:12px}.card strong{font-size:25px}.gallery,.views{grid-template-columns:1fr}th,td{padding:9px}.note{padding:14px}}
'''

def load(path):return json.loads(path.read_text())
def tag(status):return f'<span class="status {esc(status)}">{esc(status.replace("_"," "))}</span>'
def link(path,label):return f'<a href="{quote(str(path),safe="/#")}">{esc(label)}</a>'
def jsdetail(data,label='Raw evidence'):
    return '<details><summary>'+esc(label)+'</summary><pre>'+esc(json.dumps(data,indent=2))+'</pre></details>'
def page(title,body):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+STYLE+'</style><main>'+body+'</main></html>'
def score(row,mode):
    checks=row.get('briefs',{}).get(mode,{}).get('spec_checks',[])
    return f"{sum(c['status']=='PASS' for c in checks)}/{len(checks)}" if checks else 'Unassessed'
def score_html(row,mode):
    counts=Counter(c['status'] for c in row.get('briefs',{}).get(mode,{}).get('spec_checks',[]))
    remainder=' · '.join(f'{n} {status.lower()}' for status,n in counts.items() if status!='PASS')
    return esc(score(row,mode))+(f'<br><small>{esc(remainder)}</small>' if remainder else '')
def general(row):
    return Counter(c['status'] for c in row.get('default_checks',[]))
def counts_text(row):
    counts=general(row)
    return '; '.join(f"{n} {s.lower().replace('_',' ')}" for s,n in counts.items()) or 'Not assessed'
def spec_map(row,mode='full'):return {c['id']:c for c in row.get('briefs',{}).get(mode,{}).get('spec_checks',[])}
def general_findings(row):
    found=[]
    for c in row.get('default_evidence',[]):
        if c['status']=='PASS':continue
        obs=c.get('evidence',{}).get('observations',{});assessment=obs.get('assessment',{})
        issues=obs.get('issues',[])
        found.append(dict(id=c['id'],status=c['status'],rules=obs.get('executed',[]),
            subjects=[i.get('subject') for i in assessment.get('items',[]) if i.get('status') in ('FAIL','ERROR','WARNING','UNKNOWN')],
            messages=list(dict.fromkeys(i.get('message','') for i in issues)) or [c.get('reason','')],
            counts={k:v for k,v in assessment.items() if k.endswith('_count')},unit=assessment.get('unit','')))
    return found
def aggregate_general(rows):
    byid={}
    for row in rows:
        evidence={c['id']:c for c in row.get('default_evidence',[])}
        for audit in row.get('default_checks',[]):
            cid=audit['id'];obs=evidence.get(cid,{}).get('evidence',{}).get('observations',{})
            target=byid.setdefault(cid,dict(id=cid,label=', '.join(obs.get('executed',[])) or audit.get('pack','')+'.'+audit.get('check',''),
                unit=audit.get('unit',''),scope=audit.get('scope',''),scenes=Counter(),counts=Counter()))
            target['scenes'][audit['status']]+=1
            target['counts'].update({k:v for k,v in audit.get('counts',{}).items() if isinstance(v,(int,float))})
    return list(byid.values())
def observed(check):
    obs=check.get('evidence',{}).get('observations',{})
    assess=obs.get('assessment',{});items=assess.get('items') or obs.get('findings') or []
    if not items:return esc(check.get('reason','No item evidence available'))
    fields=['subject','object','property','status','elapsed_s','observed','expected','reason','differing_pixels','compared_pixels','maximum_channel_error']
    selected=[{k:item[k] for k in fields if k in item} for item in items]
    brief=''
    for item in items:
        if item.get('status') in ('FAIL','ERROR','UNKNOWN'):
            brief=esc(item.get('reason') or f"{item.get('object',item.get('subject',''))}: observed {item.get('observed')} vs expected {item.get('expected')}");break
    return brief+jsdetail(selected,f'{len(items)} measured item(s)')

def detail(root,row):
    ident=row['id'];prefix='../';out=root/'details';out.mkdir(exist_ok=True)
    base=Path('../assessments')/ident;prod=Path('../production')/ident
    b=f'<div class="eyebrow">Saved scene · {esc(ident)}</div><h1>{esc(next(t["title"] for t in TASKS if t["id"]==row["task"]))}</h1>'
    b+=f'<p>{row["level"].title()} brief · repetition {row["repetition"]}. {esc(INTRO[row["level"]])}</p>'
    b+=link('../index.html','← All 24 trials')
    notes=root/'production'/ident/'producer-notes.txt'
    if notes.exists():b+='<details><summary>Producer’s completion claims — not verification</summary><p>'+esc(notes.read_text())+'</p></details>'
    if row.get('unassessed'):
        b+='<p class="note">No assessable delivery: '+esc(row['unassessed'])+'</p>'+jsdetail(row['trial'],'Retained generation receipt')
        (out/f'{ident}.html').write_text(page(ident,b));return
    b+='<div class="cards">'+''.join(f'<div class="card"><small>{esc(label)}</small><strong>{esc(value)}</strong></div>' for label,value in [
        ('Supplied checks passed',score(row,'provided')),('Full target checks passed',score(row,'full')),
        ('Boundable prims',str((row.get('inventory') or {}).get('boundables','Unknown'))),('General profile',row['default_verdict'].replace('ACCEPT_FOR_USE','Accepted').replace('_',' ').title())])+'</div>'
    b+='<p class="note">A full-target mismatch is an instruction-following failure only if that target was supplied in this trial. Passing these numerical checks does not resolve appearance, complete assembly intent or continuous physical behavior.</p>'
    b+='<div class="links">'+link(prod/'prompt.txt','Exact creation prompt')+link(prod/'delivery/scene.usda','Original USD')+link(prod/'response.json','Native response')+link(prod/'metrics.json','Generation receipt')+link(base/'default/report.html','General report')+link(base/'provided/report/report.html','Supplied-brief report')+link(base/'full/report/report.html','Full-target report')+'</div>'
    b+='<h2>Scene and source evidence</h2>'
    if not row.get('inventory'):b+='<p class="note">Scene discovery/admission did not produce an inventory. Treat unavailable content checks as unassessed; consult the retained errors below.</p>'
    inv=row.get('inventory') or {};structure=inv.get('scene_structure',{})
    b+=f'<p>{inv.get("prims","Unknown")} prims; {inv.get("materials","Unknown")} materials; {inv.get("time_sampled_attributes","Unknown")} time-sampled attributes; {inv.get("authored_time_samples","Unknown")} authored time samples. Root: {esc(str(structure.get("default_prim")))}. Units: {structure.get("meters_per_unit")} m. Up axis: {esc(str(structure.get("up_axis")))}.</p>'
    if inv:
        b+='<details><summary>How this scene is structured</summary><p>'+esc('; '.join(f'{kind}: {number}' for kind,number in inv.get('prim_types',{}).items()))+'</p><div class="scroll"><table><thead><tr><th>Prim path</th><th>Type</th></tr></thead><tbody>'
        for item in structure.get('hierarchy',[]):b+='<tr><td><code>'+esc(item['path'])+'</code></td><td>'+esc(item['type'])+'</td></tr>'
        b+='</tbody></table></div><p class="muted">'+esc(structure.get('hierarchy_scope',''))+'</p></details>'
    views=row.get('display_views',row.get('views',{})).get('views',[]);view_folder=row.get('display_view_folder','views')
    if views:
        b+='<div class="views">'+''.join(f'<figure><img alt="Diagnostic scene projection at {v["elapsed_s"]} seconds" src="{quote(str(base/view_folder/v["image"]))}"><figcaption>{v["elapsed_s"]} s · {len(v["covered_geometry"])} processed geometry prims · {len(v["skipped_geometry"])} skipped</figcaption></figure>' for v in views)+'</div>'
    elif row.get('view_error'):b+='<p>Projection unavailable: '+esc(row['view_error'])+'</p>'
    b+='<p class="muted">Diagnostic projections; texture appearance, actual lighting, material transparency and engineering validity are not established. Processed prim counts do not mean every part is visible.</p>'
    if row.get('display_views'):b+='<p>'+link(base/'views/view-evidence.json','Original painter-sort preview evidence')+' · '+link(base/'views-depth-v2/view-evidence.json','Depth-tested display evidence')+' · '+link('../VIEW_AMENDMENT.md','Display correction record')+'</p>'
    b+=f'<div class="gallery"><article><h3>Delivered texture</h3><img class="texture" src="{quote(str(prod/"delivery/textures/label.png"))}" alt="Delivered source pixels"></article><article><h3>Full-target reference</h3><img class="texture" src="{quote(str(prod/"delivery/briefs/reference.png"))}" alt="Reference source pixels"><p>{"Supplied during generation." if row["level"]=="detailed" else "Withheld during this generation; applied only in the later full-target assessment."}</p></article></div>'
    b+='<h2>Ten target checks, with measured evidence</h2><div class="scroll"><table><thead><tr><th>Check</th><th>Supplied to producer?</th><th>Full target result</th><th>What was measured</th></tr></thead><tbody>'
    supplied=spec_map(row,'provided');full=spec_map(row)
    for key,label in LABELS.items():
        identcheck='spec.'+key;c=full.get(identcheck)
        b+='<tr><td>'+esc(label)+'</td><td>'+('Yes' if identcheck in supplied else 'No — target added for comparison')+'</td><td>'+tag(c['status'] if c else 'UNASSESSED')+'</td><td>'+(observed(c) if c else 'No completed measurement')+'</td></tr>'
    b+='</tbody></table></div><h2>General checks and coverage</h2><p>'+esc(counts_text(row))+'. Counts below keep each check’s unit; they are not totals of independent assets.</p><div class="scroll"><table><thead><tr><th>Rule</th><th>Status</th><th>Assessed / candidates</th><th>Pass / fail / warning / unknown / error / skipped</th><th>Unit and scope</th></tr></thead><tbody>'
    for c in row.get('default_checks',[]):
        n=c.get('counts',{});numbers=' / '.join(str(n.get(k+'_count',0)) for k in ('pass','fail','warning','unknown','error','skipped'))
        b+=f'<tr><td>{esc(c["id"])}<br><small>{esc(c.get("pack","")+"."+c.get("check",""))}</small></td><td>{tag(c["status"])}</td><td>{n.get("assessed_count",0)} / {n.get("candidate_count",0)}</td><td>{numbers}</td><td>{esc(c.get("unit",""))}<br><small>{esc(c.get("scope",c.get("reason","")))}</small></td></tr>'
    b+='</tbody></table></div>'
    failures=[c for c in row.get('default_evidence',[]) if c['status']!='PASS']
    findings=general_findings(row)
    if findings:
        b+='<h3>What the general checks found</h3><div class="scroll"><table><thead><tr><th>Rule</th><th>Finding</th><th>Affected subjects</th></tr></thead><tbody>'
        for f in findings:
            b+='<tr><td>'+esc(', '.join(f['rules']) or f['id'])+'</td><td>'+esc('; '.join(f['messages']))+'</td><td>'+'<br>'.join('<code>'+esc(str(s))+'</code>' for s in f['subjects'])+'</td></tr>'
        b+='</tbody></table></div>'
    b+=jsdetail(failures,'General findings: exact paths and native evidence')
    secondary=root/'secondary/results.json'
    if secondary.exists():
        sec=next((s for s in load(secondary)['rows'] if s['id']==ident),None)
        if sec:
            b+='<h2>Separate follow-up: 201 motion positions</h2><p>This follow-up was added after the first primary results. It does not change the ten-check scores. '+tag(sec['status'])+f' · {sec.get("positions_passed",0)} passing / {sec.get("positions_assessed",0)} assessed positions.</p>'
            b+=link(Path('../secondary')/ident/'report/report.html','Open dense-motion report')
            if sec.get('check'):b+=observed(sec['check'])
            b+='<p class="muted">Passing this denser grid still does not prove continuous motion, orientation, connections or collisions.</p>'
    b+='<h2>Requirements still needing review</h2><p>Overall supplied-brief assessment: '+tag(row['briefs'].get('provided',{}).get('scope','UNASSESSED'))+'</p>'+jsdetail(row['briefs'].get('provided',{}).get('requirements',[]),'Supplied brief coverage, including unresolved qualitative requirements')
    b+='<p>Source unchanged after assessment: '+str(row.get('source_unchanged',False))+'. All raw reports and delivery hashes are retained. Boundable prims may include non-geometry items such as area lights; projected geometry counts are listed separately.</p>'
    (out/f'{ident}.html').write_text(page(ident,b))

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root
    schedule=load(root/'inputs/schedule.json');results=load(root/'assessments/results.json') if (root/'assessments/results.json').exists() else {'rows':[]}
    byid={r['id']:r for r in results['rows']};ordered=sorted(schedule,key=lambda c:([t['id'] for t in TASKS].index(c['task']),LEVELS.index(c['level']),c['repetition']))
    rows=[byid.get(c['id'],dict(**c,pending=True)) for c in ordered];completed=sum(not r.get('pending') for r in rows);delivered=sum('default_verdict' in r for r in rows)
    display_file=root/'depth-views.json'
    if display_file.exists():
        displays={r['id']:r['views'] for r in load(display_file)['rows']}
        for row in rows:
            if row['id'] in displays:row.update(display_views=displays[row['id']],display_view_folder='views-depth-v2')
    for row in rows:
        if not row.get('pending'):detail(root,row)
    aggregate=[]
    for level in LEVELS:
        rr=[r for r in rows if r['level']==level];ready=[r for r in rr if 'default_verdict' in r]
        aggregate.append(dict(level=level,planned=len(rr),assessed=len(ready),unassessed=sum('unassessed' in r for r in rr),pending=sum(r.get('pending',False) for r in rr),
            supplied_scores=[score(r,'provided') for r in ready],full_scores=[score(r,'full') for r in ready],
            general_verdicts=dict(Counter(r['default_verdict'] for r in ready)),
            supplied_check_outcomes=dict(Counter(c['status'] for r in ready for c in r['briefs'].get('provided',{}).get('spec_checks',[]))),
            full_check_outcomes=dict(Counter(c['status'] for r in ready for c in r['briefs'].get('full',{}).get('spec_checks',[])))))
    save(root/'summary.json',dict(planned=24,completed=completed,assessed=delivered,readable_scenes=sum(bool(r.get("inventory")) for r in rows),conditions=aggregate,updated_at_utc=datetime.now(timezone.utc).isoformat()))
    b='<div class="eyebrow">Private exploratory study · frozen requirements · 3 October 2026</div><h1>What changed when the brief changed?</h1><p>Three new multi-part scene tasks. Four prompt levels. Two fresh runs of each. The same harness assesses every unchanged delivery, with and without its specification.</p>'
    b+='<div class="cards">'+''.join(f'<div class="card"><small>{label}</small><strong>{value}</strong></div>' for label,value in [('Planned trials',24),('Completed attempts',completed),('Delivery reports',delivered),('Control cases matched','33 / 33')])+'</div>'
    b+='<h2>Agreement with the same full target</h2><p>Each cell shows passing rules out of ten for run 1, then run 2. Targets withheld from simpler prompts measure later alignment; they are not ignored instructions. These fractions do not include general delivery checks or unresolved review requirements.</p><div class="scroll"><table><thead><tr><th>Scene family</th>'+''.join('<th>'+level.title()+'</th>' for level in LEVELS)+'</tr></thead><tbody>'
    for task in TASKS:
        b+='<tr><td>'+esc(task['title'])+'</td>'
        for level in LEVELS:
            selected=[row for row in rows if row['task']==task['id'] and row['level']==level]
            b+='<td>'+', '.join('Pending' if row.get('pending') else link(f'details/{row["id"]}.html',score(row,'full')) for row in selected)+'</td>'
        b+='</tr>'
    b+='</tbody></table></div>'
    conclusions=root/'conclusions.json'
    if conclusions.exists():
        b+='<div class="note"><h3>What we learned</h3><ul>'
        for item in load(conclusions)['points']:
            b+='<li>'+esc(item['text'])
            if item.get('cases'):b+=' '+', '.join(link(f'details/{case}.html',case) for case in item['cases'])
            b+='</li>'
        b+='</ul>'+link('RESULTS.md','Read the complete results and limits')+'</div>'
    if completed<24:b+='<p class="note">Study in progress. Pending slots are shown explicitly; these partial results are not the final conclusion.</p>'
    b+='<div class="note"><strong>Read the comparisons separately.</strong><p><b>General checks</b> diagnose structure and declared data without a task brief. <b>Supplied checks</b> compare only measurable requirements given to that producer. <b>Full target</b> compares every scene to the same ten targets, including targets withheld from simpler prompts. A withheld target mismatch is not an ignored instruction. <b>Brief assessment</b> combines general findings, mapped requirements and unresolved review gates.</p></div>'
    b+='<div class="links">'+link('frozen-study/PROTOCOL.md','Frozen protocol')+link('freeze.json','Input/runtime freeze')+link('matrix.csv','Download trial table')+link('measurements.csv','Download every target outcome')+link('controls/summary.json','33 control receipts')+'</div>'
    if (root/'scene-deliveries.zip').exists():b+='<p>'+link('scene-deliveries.zip','Download all unchanged scene bundles')+' · '+link('scene-archive-verification.json','Archive integrity receipt')+'</p>'
    b+='<h2>What each prompt supplied</h2><div class="scroll"><table><thead><tr><th>Level</th><th>Additional information</th><th>Mapped numerical checks</th><th>Example prompt</th></tr></thead><tbody>'
    for level,n in zip(LEVELS,[1,3,8,10]):b+=f'<tr><td>{level.title()}</td><td>{esc(INTRO[level])}</td><td>{n}</td><td>'+'<br>'.join(link(f'inputs/{t["id"]}/briefs/{level}.md',t['title']) for t in TASKS)+'</td></tr>'
    b+='</tbody></table></div><p class="muted">All prompts share fixed output paths, Z-up metre coordinates, a request for at least 40 geometry prims and an output interface. These are assistant-authored synthetic briefs. Detailed depth combines more text, trajectory samples and an image, so this does not isolate any one prompt feature.</p>'
    b+='<h2>All trial results</h2><p>Scores are passing check rules / selected check rules. Rules overlap and are not independent assets. Expand a scene for measured values, exact failures, source prompts and reports.</p><div class="filters"><label>Scene family <select id="task"><option value="">All</option>'+''.join(f'<option value="{t["id"]}">{esc(t["title"])}</option>' for t in TASKS)+'</select></label><label>Prompt level <select id="level"><option value="">All</option>'+''.join(f'<option>{l}</option>' for l in LEVELS)+'</select></label></div>'
    b+='<div class="scroll"><table class="matrix"><thead><tr><th>Scene / run</th><th>Creation prompt</th><th>Supplied checks</th><th>Same full target</th><th>General result</th><th>Brief assessment</th><th>Coverage / scene size</th></tr></thead><tbody>'
    csvrows=[];measurements=[]
    for row in rows:
        ident=row['id'];state='PENDING' if row.get('pending') else 'UNASSESSED' if row.get('unassessed') else row['default_verdict']
        title=next(t['title'] for t in TASKS if t['id']==row['task'])
        name=esc(title) if row.get('pending') else link(f'details/{ident}.html',title)
        cov=esc(counts_text(row))+'<br><small>'+str((row.get('inventory') or {}).get('boundables','—'))+' boundable prims</small>'
        b+=f'<tr data-task="{row["task"]}" data-level="{row["level"]}"><td>{name}<br><small>Run {row["repetition"]}</small></td><td>{row["level"].title()}</td><td>{score_html(row,"provided")}</td><td>{score_html(row,"full")}</td><td>{tag(state)}</td><td>{tag(row.get("briefs",{}).get("provided",{}).get("scope","UNASSESSED"))}</td><td>{cov}</td></tr>'
        csvrows.append(dict(id=ident,task=row['task'],level=row['level'],repetition=row['repetition'],status=state,supplied_pass_selected=score(row,'provided'),full_pass_selected=score(row,'full'),boundable_prims=(row.get('inventory') or {}).get('boundables'),general_counts=counts_text(row),supplied_scope=row.get('briefs',{}).get('provided',{}).get('scope','UNASSESSED'),unassessed_reason=row.get('unassessed','')))
        supplied=spec_map(row,'provided')
        for key,label in LABELS.items():
            cid='spec.'+key;c=spec_map(row).get(cid,{})
            measurements.append(dict(trial=ident,task=row['task'],level=row['level'],repetition=row['repetition'],check=cid,label=label,supplied_to_producer=cid in supplied,full_target_status=c.get('status','PENDING' if row.get('pending') else 'UNASSESSED'),reason=c.get('reason',''),evidence_json=json.dumps(c.get('evidence',{}))))
    b+='</tbody></table></div>'
    general_summary=aggregate_general(rows)
    b+='<details><summary>General coverage across completed scenes — all 27 rules</summary><p>Counts are summed within each rule and its own unit across deliveries. They are not a total of distinct assets. Stage callbacks do not expose per-object coverage.</p><div class="scroll"><table><thead><tr><th>Rule</th><th>Scene outcomes</th><th>Assessed / candidates</th><th>Subject pass / fail / warning / unknown / error / skipped</th><th>Unit</th></tr></thead><tbody>'
    general_csv=[]
    for g in general_summary:
        counts=g['counts'];outcomes='; '.join(f'{n} {s}' for s,n in g['scenes'].items());numbers=' / '.join(str(counts.get(k+'_count',0)) for k in ('pass','fail','warning','unknown','error','skipped'))
        b+=f'<tr><td>{esc(g["label"])}<br><small>{esc(g["id"])}</small></td><td>{esc(outcomes)}</td><td>{counts.get("assessed_count",0)} / {counts.get("candidate_count",0)}</td><td>{numbers}</td><td>{esc(g["unit"])}</td></tr>'
        general_csv.append(dict(id=g['id'],label=g['label'],scene_outcomes=outcomes,unit=g['unit'],scope=g['scope'],**counts))
    b+='</tbody></table></div>'+link('general-coverage.csv','Download general coverage counts')+'</details>'
    b+='<details><summary>Which targets passed? — every trial and target</summary><p>Every cell uses the full target. The scene detail marks which targets the producer had received.</p><div class="scroll"><table class="heat"><thead><tr><th>Trial</th>'+''.join('<th>'+esc(v)+'</th>' for v in LABELS.values())+'</tr></thead><tbody>'
    for row in rows:
        m=spec_map(row);b+='<tr><td>'+esc(row['id'])+'</td>'+''.join('<td>'+tag(m.get('spec.'+k,{}).get('status','PENDING' if row.get('pending') else 'UNASSESSED'))+'</td>' for k in LABELS)+'</tr>'
    b+='</tbody></table></div></details><details><summary>Browse the saved scenes</summary><p>Each thumbnail is a diagnostic surface projection at the saved stage’s midpoint. It helps locate the scene; it does not certify visual or physical quality.</p><div class="gallery">'
    for row in rows:
        vv=row.get('display_views',row.get('views',{})).get('views',[]);view_folder=row.get('display_view_folder','views')
        if not vv:continue
        v=vv[1];b+='<article><h3>'+link(f'details/{row["id"]}.html',row['id'])+'</h3>'+f'<img loading="lazy" src="assessments/{row["id"]}/{view_folder}/{v["image"]}" alt="Diagnostic projection of {row["id"]}"><p>Supplied {score(row,"provided")} · full target {score(row,"full")} · {len(v["covered_geometry"])} processed geometry prims</p></article>'
    b+='</div></details><h2>What these checks can and cannot establish</h2><div class="scroll"><table><thead><tr><th>Category</th><th>Evidence collected</th><th>Remaining limit</th></tr></thead><tbody><tr><td>General delivery</td><td>27 selected baseline diagnostics, with actual subject counts, warnings, skips and no-applicable subjects.</td><td>Valid structure does not determine the desired dimensions, layout, motion or image.</td></tr><tr><td>Mapped specification</td><td>Explicit sizes, counts, gap, metadata, clock, sampled world positions and decoded image pixels.</td><td>Only the declared comparison is covered. Correct bounds do not prove shape; correct pixels do not prove visible mapping.</td></tr><tr><td>Still needing review</td><td>Qualitative component completeness, credible arrangement, rendered appearance and continuous motion are retained as unresolved requirements.</td><td>No physical calibration, simulator behavior, real safety clearance, image aesthetics or complete engineering acceptance was tested.</td></tr></tbody></table></div>'
    secondary=root/'secondary/results.json'
    if secondary.exists():
        sr=load(secondary)['rows'];sm={s['id']:s for s in sr}
        b+='<h2>Separate follow-up: motion between the original checkpoints</h2><p>This exploratory addition uses 201 elapsed-second positions against the same target path. It was added after the first primary results; the original scores above stay unchanged. Only detailed producers received the continuous path requirement. '+link('frozen-secondary/SECONDARY_SAMPLING.md','Read the follow-up protocol')+'</p><div class="scroll"><table><thead><tr><th>Trial</th><th>Original 21-point rule</th><th>201-point rule</th><th>Passing positions / assessed</th></tr></thead><tbody>'
        for row in rows:
            s=sm.get(row['id']);primary=spec_map(row).get('spec.trajectory',{}).get('status','UNASSESSED')
            if s:b+='<tr><td>'+esc(row['id'])+'</td><td>'+tag(primary)+'</td><td>'+tag(s['status'])+'</td><td>'+str(s.get('positions_passed',0))+' / '+str(s.get('positions_assessed',0))+'</td></tr>'
        b+='</tbody></table></div><p>A constructed 21-point circular path passed the original checkpoints but failed 132 of 201 denser positions. An analytically rotating control passed 201/201. These two controls are separate from the original 33 and from model errors. Two earlier follow-up runner setup failures are retained as excluded pilots. Passing a finite grid remains insufficient for continuous proof.</p>'
    b+='<p>All 33 scripted controls matched their expected outcome before generation. The interior-motion mutation kept endpoints correct but failed the 21-point check. The changed image stayed readable but failed exact pixels. These are measurement controls, not model-produced errors.</p><p class="muted">Only two repetitions per family and level. The trials are correlated, use shared output conventions, and have no independently supplied human brief. This evidence cannot establish a general model failure rate, every possible failure the harness can catch, or time saved. Requested model: gpt-6-astra / high; resolved snapshot unavailable. No repair feedback was used.</p>'
    b+='<script>function filter(){const t=document.getElementById("task").value,l=document.getElementById("level").value;document.querySelectorAll("tr[data-task]").forEach(r=>r.hidden=!!((t&&r.dataset.task!==t)||(l&&r.dataset.level!==l)))}document.getElementById("task").addEventListener("change",filter);document.getElementById("level").addEventListener("change",filter);</script>'
    (root/'index.html').write_text(page('Brief depth scene study',b))
    for name,records in [('matrix.csv',csvrows),('measurements.csv',measurements),('general-coverage.csv',general_csv)]:
        if not records:continue
        with (root/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    print(json.dumps(dict(completed=completed,assessed=delivered,index=str(root/'index.html'))))

if __name__=='__main__':main()
