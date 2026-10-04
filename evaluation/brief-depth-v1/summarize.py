"""Evidence tables from retained receipts; rules and assets remain different units."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from build_report import LABELS, general_findings, score, spec_map
from study import TASKS, LEVELS, save

def table(headers,records):
    def cell(v):return str(v).replace('|',' / ').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+['| '+' | '.join(cell(v) for v in row)+' |' for row in records])+'\n'

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root
    results=json.loads((root/'assessments/results.json').read_text());rows=results['rows']
    assert len(rows)==24,'Final summary requires all planned slots'
    runs=json.loads((root/'production/runs.json').read_text());assert len(runs)==24
    delivered=[r for r in rows if 'default_verdict' in r];readable=[r for r in delivered if r.get('inventory')]
    status=Counter(r['status'] for r in runs);gen=Counter(r['default_verdict'] for r in delivered)
    b='# What the brief-depth study found\n\n'
    b+=f'All 24 planned attempts completed across three synthetic task families, four brief levels and two fresh repetitions. {status.get("DELIVERED",0)} produced complete adapter deliveries; {len(readable)} produced scene inventories. All original scenes and source images were retained unchanged. This is a small exploratory study of constrained direct USD generation, not a general model benchmark.\n\n'
    b+='[Open the readable comparison report](index.html). Each trial links the exact prompt, original USD, source/reference pixels, general report, supplied-brief report, full-target report and measured evidence.\n\n'
    b+='## Same target, different creation information\n\nThe following cells show passing rules out of the same ten full-target rules, in repetition 1 / repetition 2 order. A target withheld from the producer is a later alignment comparison, not an ignored instruction.\n\n'
    family=[]
    for task in TASKS:
        record=[task['title']]
        for level in LEVELS:
            rr=sorted([r for r in rows if r['task']==task['id'] and r['level']==level],key=lambda r:r['repetition'])
            record.append(', '.join(score(r,'full') for r in rr))
        family.append(record)
    b+=table(['Scene family','Simple','Light','Medium','Detailed'],family)
    b+='\n## Requirements actually supplied\n\nAll conditions shared output conventions. Simple supplied one mapped coordinate check; light three checks; medium eight; detailed ten. Assembly completeness and appearance remained separate review requirements. An all-pass fraction here covers only selected numeric rules.\n\n'
    level_records=[];levels=[]
    for level,n in zip(LEVELS,[1,3,8,10]):
        rr=[r for r in rows if r['level']==level];provided=[c for r in rr for c in r.get('briefs',{}).get('provided',{}).get('spec_checks',[])];c=Counter(x['status'] for x in provided)
        accepted=sum(r.get('default_verdict')=='ACCEPT_FOR_USE' for r in rr)
        all_supplied=sum(len(spec_map(r,'provided'))==n and all(x['status']=='PASS' for x in spec_map(r,'provided').values()) for r in rr)
        level_records.append([level.title(),n,f'{all_supplied}/6',f'{accepted}/6',', '.join(f'{k}: {v}' for k,v in c.items())])
        levels.append(dict(level=level,selected_per_delivery=n,all_supplied_numeric_pass=all_supplied,general_accepted=accepted,provided_outcomes=dict(c)))
    b+=table(['Creation level','Mapped rules per scene','Scenes passing every supplied numeric rule','General profile accepted','Supplied rule outcomes'],level_records)
    b+='\n## Per-target results, with supplied and withheld targets separated\n\n'
    target_records=[]
    for key,label in LABELS.items():
        cid='spec.'+key;sup=Counter();withheld=Counter()
        for row in rows:
            c=spec_map(row).get(cid)
            if c:(sup if cid in spec_map(row,'provided') else withheld)[c['status']]+=1
        target_records.append([label,', '.join(f'{k}: {v}' for k,v in sup.items()) or 'Unassessed',', '.join(f'{k}: {v}' for k,v in withheld.items()) or 'Not withheld'])
    b+=table(['Target','When supplied during creation','When added only for assessment'],target_records)
    b+='\n## What the general checks caught\n\n'
    b+='General verdicts: '+', '.join(f'{s}: {n}' for s,n in gen.items())+'. These are delivery-profile outcomes, not engineering or visual certification. The 27 baseline rules retain no-applicable subjects rather than treating absent physics as tested physics.\n\n'
    fault_records=[];faults=[]
    for row in rows:
        for finding in general_findings(row):
            record=dict(trial=row['id'],**finding);faults.append(record)
            count=finding['counts'];fault_records.append([row['id'],', '.join(finding['rules']) or finding['id'],
                f"{count.get('fail_count','?')} failed / {count.get('assessed_count','?')} assessed {finding['unit']}",
                '; '.join(finding['messages']),', '.join(str(s) for s in finding['subjects'])])
    b+=table(['Trial','Rule','Coverage','Finding','Affected subjects'],fault_records) if faults else 'No general failures were observed in this cohort.\n'
    b+='\nThese are per-rule evaluations. A prim failing two rules is not two distinct assets. Native stage validators may expose only one stage invocation rather than per-asset coverage.\n\n'
    failed_subjects={(f['trial'],str(s)) for f in faults for s in f['subjects']}
    fault_counts=Counter()
    for f in faults:
        for rule in f['rules']:fault_counts[rule]+=f['counts'].get('fail_count',0)
    b+='Across these general findings: '+', '.join(f'{rule}: {count} failed prim-rule evaluations' for rule,count in fault_counts.items())+f'. They affected {len(failed_subjects)} distinct (scene, prim-path) pairs.\n\n'
    b+='## Supplied numeric requirements that did not pass\n\n'
    mismatches=[]
    for row in rows:
        for check in row.get('briefs',{}).get('provided',{}).get('spec_checks',[]):
            if check['status']=='PASS':continue
            obs=check.get('evidence',{}).get('observations',{});items=obs.get('assessment',{}).get('items') or obs.get('findings',[])
            failures=[x for x in items if x.get('status')!='PASS']
            reason=next((x.get('reason') for x in failures if x.get('reason')),check['reason'])
            mismatches.append([row['id'],check['id'],check['status'],len(failures),len(items),reason])
    b+=table(['Trial','Check','Status','Nonpassing measured items','Items measured','Evidence'],mismatches) if mismatches else 'Every supplied numeric check passed in this cohort. This does not resolve unmapped or qualitative requirements.\n'
    b+='\n## Denser motion follow-up — separate from primary results\n\n'
    secondary=json.loads((root/'secondary/results.json').read_text())['rows'];assert len(secondary)==24
    follow=[];newfails=[]
    for row in rows:
        s=next(x for x in secondary if x['id']==row['id']);primary=spec_map(row).get('spec.trajectory',{}).get('status','UNASSESSED')
        follow.append([row['id'],primary,s['status'],f"{s.get('positions_passed',0)}/{s.get('positions_assessed',0)}",'Yes' if row['level']=='detailed' else 'No'])
        if primary=='PASS' and s['status']=='FAIL':newfails.append(row['id'])
    b+='After inspecting the first two primary results, a separately frozen follow-up sampled 201 positions from the same target paths. It never changed the ten-check primary scores. A constructed 21-point circular path passed those checkpoints but failed 132/201 denser positions; an analytically rotating control passed 201/201. Two control-runner setup errors are retained as excluded pilots.\n\n'
    b+=table(['Trial','21-point rule','201-point rule','Passing positions / assessed','Continuous path supplied?'],follow)
    b+='\nOriginal 21-point pass / denser-grid fail cases: '+(', '.join(newfails) if newfails else 'none in the generated cohort')+'. Finite sampling still cannot certify the whole continuous interval, orientation, connections or collisions.\n\n'
    b+='## Interpretation limits\n\n- The original 33 deliberate measurement controls matched their expected outcomes. They are controls, not model errors.\n- Requirement maps were assistant-authored before generation at the owner’s request. No independent human ground-truth review is claimed.\n- General diagnostics do not know the desired part count, dimensions, path or pixel image without an explicit target. Conversely, a supplied target can pass while a general delivery rule fails.\n- A detailed brief can improve alignment without establishing complete acceptance. Geometry bounds do not prove shape, source pixels do not prove visible mapping, and samples do not prove continuous behavior.\n- Two repetitions per family and level do not establish population rates or “always/never” claims. Image addition, text detail, explicit samples and tolerance presentation are bundled together.\n- Every condition shares output/naming conventions and a request for at least 40 visible geometry prims. This differs from an unconstrained one-line prompt or a tool-using modelling workflow.\n- The requested model was gpt-6-astra with high reasoning. The resolved snapshot is unavailable. All contexts were fresh and tools disabled. No feedback or repairs were supplied.\n- No simulator, GPU application run, physical calibration, optional model judge or complete visual review was performed. The original qualitative review gates remain explicit.\n\n'
    b+='[Frozen protocol](frozen-study/PROTOCOL.md) · [Original freeze](freeze.json) · [Secondary addendum](frozen-secondary/SECONDARY_SAMPLING.md) · [Raw measurements CSV](measurements.csv) · [Integrity verification](verification.json).\n'
    (root/'RESULTS.md').write_text(b)
    save(root/'analysis.json',dict(levels=levels,general_verdicts=dict(gen),general_findings=faults,
        supplied_nonpassing=mismatches,primary_pass_secondary_fail=newfails,readable_scenes=len(readable),delivered=len(delivered),
        failed_rule_evaluations=dict(fault_counts),distinct_affected_scene_prim_pairs=len(failed_subjects)))
    print(json.dumps(dict(rows=len(rows),readable=len(readable),general=dict(gen),levels=levels,denser_new_failures=newfails)))

if __name__=='__main__':main()
