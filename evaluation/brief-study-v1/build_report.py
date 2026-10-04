"""Reader-facing tables linked to complete, unchanged per-scene evidence."""
from collections import Counter
import argparse
import json
from pathlib import Path
from scene_acceptance.report import E,STYLE
from scene_acceptance.model import sha

def counts(rows):
    c=Counter(x['status'] for x in rows)
    return f"{c['PASS']} pass / {c['FAIL']} fail / {c['UNKNOWN']} unknown / {c['ERROR']} error"

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args();root=args.root
    saved=json.loads((root/'saved-scene/results.json').read_text())
    evaluated=json.loads((root/'evaluated/results.json').read_text()) if (root/'evaluated/results.json').exists() else {'rows':[]}
    results=sorted(evaluated['rows'],key=lambda r:(r.get('repetition',r.get('trial',{}).get('repetition',0)),r.get('arm',r.get('trial',{}).get('arm'))!='simple'));parts=[]
    parts.append('<h1>What changes when the harness gets a brief?</h1><p>Private exploratory study · saved-scene comparison, six fresh creation trials, and optional model review.</p>')
    parts.append('<p><strong>Observed result:</strong> the three scenes created with the detailed brief passed 7/7, 7/7 and 6/7 planned requirement checks. The simple-prompt scenes each matched 0/7 of those later targets. Every scene still had a default validation failure. The last detailed run reversed the supplied reference image.</p>')
    parts.append('<p class="scope"><strong>Three different questions:</strong> Can the saved scene be read and structurally checked? Does it meet this particular brief? Does it satisfy the qualitative or continuous behavior that the available measurements cannot establish?</p>')
    parts.append('<p>The sample briefs were authored by the assistant at the owner’s request. They demonstrate user-style text and image inputs; they are not independently supplied human requirements. Original source files and exact mappings appear in every brief report.</p>')
    parts.append('<h2>1. Same scene, different assessment brief</h2><p>The retained panel was not regenerated or edited. These later briefs are counterfactual assignments; a rejection under a different target is not a defect against its original assignment.</p><div class="scroll"><table><tr><th>Evaluator receives</th><th>Script result</th><th>Declared scope</th><th>What changed</th></tr>')
    descriptions={'default':'27 general checks; no panel-size or reference-pixel target.','size':'Adds the 240 × 160 mm size requirement.','image-a':'Adds the matching 256 × 256 reference image.','image-b':'Changes only the required reference to different quadrant pixels; 65,536 pixels disagree.','conflict':'Keeps the matching measurements but explicitly records contradictory width instructions; clarification remains required.'}
    for r in saved['rows']:
        parts.append(f'<tr><td><a href="saved-scene/{E(r["report"])}">{E(r["condition"])}</a></td><td>{E(r["core"])}</td><td>{E(r["scope"])}</td><td>{E(descriptions[r["condition"]])}</td></tr>')
    parts.append('</table></div><div class="cards"><div class="card">Reference A<br><img width="160" src="inputs/panel/briefs/reference-a.png" alt="Reference A: red green blue white quadrants"></div><div class="card">Reference B<br><img width="160" src="inputs/panel/briefs/reference-b.png" alt="Reference B: green red white blue quadrants"></div></div>')
    parts.append('<h2>2. Brief before creation versus brief only at assessment</h2><p>Six fresh Astra calls: simple and detailed text+image prompts, repeated three times in interleaved order. All use the same common output conventions. Each delivered scene is assessed against the same default, text-only, text+image and changed-target requirements.</p><p><a href="inputs/simple-prompt.txt">Exact simple prompt</a> · <a href="inputs/detailed-prompt.txt">Exact detailed prompt</a> · <a href="inputs/cell/briefs/image.md">Assessment brief</a> · <a href="inputs/cell/briefs/changed.md">Changed-target brief</a></p><p>The image condition adds the exact warning pattern. The changed-target condition asks for a 1.4 m cabinet gap instead of 0.9 m and reverses the reference image. It was supplied only during evaluation.</p><img width="128" style="image-rendering:pixelated" src="inputs/cell/briefs/warning-a.png" alt="Normative yellow and black warning image"><img width="128" style="image-rendering:pixelated;margin-left:20px" src="inputs/cell/briefs/warning-b.png" alt="Counterfactual reversed warning image">')
    parts.append('<p>Counts below are selected requirement checks, not a score or count of independent assets. Open-ended visual and continuous-motion obligations are listed separately.</p><div class="scroll"><table><tr><th>Creation run</th><th>Scene structure</th><th>Default diagnostics</th><th>Text brief: measurements</th><th>Text + image brief: measurements</th><th>Changed targets: measurements</th><th>Remaining scope</th></tr>')
    for r in results:
        if 'unassessed' in r:
            parts.append(f'<tr><td>{E(r["trial"]["id"])}</td><td colspan="6">No delivery: {E(r["unassessed"])}</td></tr>');continue
        id=r['id'];inv=r['inventory'] or {};structure=f"{inv.get('prims','?')} prims; {inv.get('meshes','?')} meshes; {inv.get('boundables','?')} boundable prims; {inv.get('animated_transform_prims','?')} animated prims"
        cells=''.join(f'<td><a href="evaluated/{id}/{mode}/report/report.html">{E(counts(r["briefs"][mode]["spec_checks"]))}</a><small>{E(r["briefs"][mode]["core"])}</small></td>' for mode in ('text','image','changed'))
        general=Counter(x['status'] for x in r['default_checks'])
        gtext='; '.join(f'{n} {s.lower().replace("_"," ")}' for s,n in general.items())
        unknown=[x['id'] for x in r['briefs']['image']['requirements'] if x['status']=='UNKNOWN']
        parts.append(f'<tr><td>{E(id)}<small>{"Detailed text + image at creation" if r["arm"]=="detailed" else "Simple prompt; detailed brief first seen at assessment"}</small></td><td>{E(structure)}</td><td><a href="evaluated/{id}/default/report.html">{E(r["default_verdict"])}</a><small>{E(gtext)}</small></td>{cells}<td>{E(", ".join(unknown) or "See complete scope report")}</td></tr>')
    parts.append('</table></div>')
    parts.append('<h2>3. What was measured and what it found</h2><p>All six scenes are compared with the original text+image brief here. Expand a measurement for actual values, targets and assessed subjects. These results are distinct from general structural findings.</p><div class="scroll"><table><tr><th>Measurement</th>'+''.join('<th>'+E(r['id'])+'</th>' for r in results if 'id' in r)+'</tr>')
    ids=['spec.deck','spec.rollers','spec.aisle','spec.carton','spec.clock','spec.motion','spec.warning-image']
    labels=dict(zip(ids,['Conveyor dimensions and centre','Exactly 12 rollers','Cabinet gap ≥ 0.9 m','Carton dimensions','4 seconds at 24 time codes/s','Carton position at 21 times','Warning image matches reference']))
    for check_id in ids:
        parts.append('<tr><th>'+E(labels[check_id])+'<small>'+E(check_id)+'</small></th>')
        for r in results:
            if 'id' not in r:continue
            check=next((c for c in r['briefs']['image']['spec_checks'] if c['id']==check_id),None)
            if check:
                evidence=check['evidence'].get('observations',{})
                parts.append(f'<td class="{E(check["status"])}"><strong>{E(check["status"])}</strong><details><summary>Measured evidence</summary><p>{E(check["reason"])}</p><pre>{E(json.dumps(evidence,indent=2))}</pre></details></td>')
            else:parts.append('<td>Not assessed; see admission result</td>')
        parts.append('</tr>')
    parts.append('</table></div>')
    for r in results:
        if 'id' not in r:continue
        parts.append(f'<details><summary>{E(r["id"])} — scene views and structural findings</summary>')
        if 'views' in r:
            parts.append('<p>Diagnostic projections from saved geometry at 0, 2 and 4 seconds. Flat colours; no texture/shader rendering or physical verification.</p><div class="cards">')
            for v in r['views']['views']:
                parts.append(f'<a href="evaluated/{r["id"]}/views/{v["image"]}"><img width="320" style="max-width:100%" src="evaluated/{r["id"]}/views/{v["image"]}" alt="{E(r["id"])} diagnostic scene projection at {v["elapsed_s"]} seconds"></a>')
            parts.append('</div>')
        else:parts.append('<p>'+E(r.get('view_error','View unavailable'))+'</p>')
        finding=[x for x in r['default_checks'] if x['status'] not in ('PASS','NO_APPLICABLE_SUBJECTS')]
        parts.append('<ul>'+''.join(f'<li>{E(x["id"])}: {E(x["status"])} — {E(x["reason"])}</li>' for x in finding)+'</ul></details>')
        raw=json.loads((root/f'evaluated/{r["id"]}/default/result.json').read_text())
        failure_rows=[]
        for check in raw['checks']:
            obs=check.get('evidence',{}).get('observations',{})
            if not isinstance(obs,dict):continue
            a=obs.get('assessment',{})
            for subject in a.get('items',[]):
                if subject['status']!='FAIL':continue
                message=subject.get('reason') or '; '.join(dict.fromkeys(x.get('message','') for x in obs.get('issues',[])))
                failure_rows.append(f'<tr><td>{E(check["id"])}</td><td><code>{E(subject["subject"])}</code></td><td>{E(message)}</td></tr>')
        if failure_rows:
            parts.append(f'<details><summary>{E(r["id"])} — exact objects with default-check failures</summary><div class="scroll"><table><tr><th>Check</th><th>Object</th><th>How the validator found it</th></tr>'+''.join(failure_rows)+'</table></div><p>Objects can occur under more than one rule. These are selected delivery-profile findings, not proof that the scene is unusable in every renderer.</p></details>')
    audit_file=root/'mapping-audit/results.json'
    if audit_file.exists():
        audit=json.loads(audit_file.read_text())['rows']
        parts.append('<h2>4. Coverage improvement found during the study</h2><p>The original map omitted two requirements already present in the frozen brief: the coordinate system and exact time-code endpoints. These supplemental checks were added after generation began. The original seven-check comparison above remains preserved; see the <a href="MAPPING-AMENDMENT.md">mapping audit</a>.</p><div class="scroll"><table><tr><th>Scene</th><th>Authored Z-up/metre units</th><th>Authored time codes 0–96</th><th>Complete mapped report</th></tr>')
        for r in sorted(audit,key=lambda x:(x['repetition'],x['arm']!='simple')):
            c={x['id']:x for x in r['briefs']['image']['spec_checks']}
            cells=''.join('<td>'+E(c[id]['status'])+'<small>'+E('; '.join(i['reason'] for i in c[id]['evidence']['observations']['assessment']['items']))+'</small></td>' for id in ('spec.coordinates','spec.time-range'))
            parts.append(f'<tr><td>{E(r["id"])}</td>{cells}<td><a href="mapping-audit/{r["id"]}/image/report/report.html">Nine measurements plus unresolved scope</a></td></tr>')
        parts.append('</table></div><p>Full source text does not guarantee full check coverage. The application or reviewer must confirm the mapping. Required parts, continuous motion and visible texture use still need evidence beyond these measurements.</p>')
    parts.append('<h2>5. Optional model reviewer</h2><p>This is a separate advisory channel. It receives the same frozen brief, the original seven-check mapping, script evidence and explicitly supplied diagnostic images. A model opinion does not modify a measured result, approve a requirement or prove physical validity. Because it sees the script findings, agreement is not independent rediscovery of those defects.</p>')
    judges=[]
    for path in sorted((root/'judges').glob('*/judge-result.json')):
        r=json.loads(path.read_text());opinions=Counter(x['assessment'] for x in (r['response'] or {}).get('items',[]))
        if (path.parent/'EXCLUDED.md').exists():
            parts.append(f'<p>Retained but excluded pilot: <a href="judges/{path.parent.name}/report.html">{E(path.parent.name)}</a>. Its diagnostic view had a display-axis error; see <a href="VIEW-AMENDMENT.md">the correction record</a>.</p>')
            continue
        judges.append(dict(id=path.parent.name,status=r['status'],opinions=dict(opinions),script=r['script_verdict_unchanged']))
    if judges:
        parts.append('<div class="scroll"><table><tr><th>Case</th><th>Review status</th><th>Opinions</th><th>Unchanged script verdict</th></tr>')
        for j in judges:
            opinion_text='; '.join(f'{n} {kind}' for kind,n in j['opinions'].items())
            parts.append(f'<tr><td><a href="judges/{j["id"]}/report.html">{E(j["id"])}</a></td><td>{E(j["status"])}</td><td>{E(opinion_text)}</td><td>{E(j["script"])}</td></tr>')
        parts.append('</table></div>')
    else:parts.append('<p>Live review not yet recorded. Deterministic software adapter controls are separate from model evidence.</p>')
    notes=root/'LEARNINGS.html'
    if notes.exists():parts.append(notes.read_text())
    parts.append('<h2>Study limits and reproducibility</h2><ul><li>Three independent-context repetitions per arm, one requested model family, interleaved order, no controlled random seed and no repair feedback. This is not a general failure rate or an independent benchmark.</li><li>Bounded tool-disabled USD authoring, not the full tool-using Astra apps. The delivery adapter saves the model’s USD unchanged and converts its 8×8 palette to PNG. It does not repair scenes.</li><li>The earlier demo scenes were not rebuilt here. A later brief cannot establish how their original creation would have differed.</li><li>Passing sampled positions and image pixels leaves continuous motion, rendered appearance, physical behavior and omitted intent unresolved.</li><li>All initial infrastructure failures are retained. The old standalone CLI rejected Astra before generation; retry used the newer bundled CLI with unchanged prompts and requirements.</li></ul><p><a href="frozen-protocol/PROTOCOL.md">Frozen protocol</a> · <a href="pre-generation-freeze.json">Source/input hashes</a> · <a href="INFRASTRUCTURE-AMENDMENT.md">CLI recovery record</a> · <a href="evaluated/results.json">Detailed study data</a> · <a href="RESULTS.md">Findings and limits</a></p>')
    extra='table{font-size:13px}td:first-child{min-width:135px}pre{max-height:350px;overflow:auto;max-width:360px}details{margin:12px 0}img{border:1px solid #ccd4dc}th{position:sticky;top:0}#study-table{table-layout:auto}'
    (root/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Brief-aware harness study</title><style>'+STYLE+extra+'</style><main>'+''.join(parts)+'</main></html>')
    (root/'reader-summary.json').write_text(json.dumps(dict(saved_scene=saved['rows'],judges=judges,creation_trials=len(results)),indent=2)+'\n')
    print(root/'index.html')

if __name__=='__main__':main()
