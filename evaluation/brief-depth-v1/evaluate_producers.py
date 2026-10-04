"""Three frozen assessments, preserving every completed slot and original delivery."""
import argparse
import json
from pathlib import Path
from scene_acceptance.briefs import evaluate_brief
from scene_acceptance.engine import implementation_digest
from scene_acceptance.model import sha
from scene_acceptance.profiles import baseline_contract, discovery_failure_report
from scene_acceptance.pack_engine import evaluate_packs
from scene_acceptance.report import write_report
from diagnostic_views import render
from study import save

def main():
    p=argparse.ArgumentParser();p.add_argument('--production',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=a.resume)
    schedule=json.loads((a.production/'dispatch.json').read_text())['schedule'];rows=[]
    receipt=a.out/'results.json'
    if a.resume and receipt.exists():
        previous=json.loads(receipt.read_text());assert previous['checker_sha256']==implementation_digest();rows=previous['rows']
    for planned in schedule:
        case=a.production/planned['id'];metrics=case/'metrics.json'
        if not metrics.exists() or planned['id'] in {r['id'] for r in rows}:continue
        trial=json.loads(metrics.read_text());row=dict(**planned,trial=trial)
        if trial['status']!='DELIVERED':row['unassessed']=trial['error']
        else:
            bundle=case/'delivery';target=a.out/planned['id'];target.mkdir(exist_ok=False)
            hashes=json.loads((case/'delivery-manifest.json').read_text())['files']
            assert all(sha(bundle/k)==v for k,v in hashes.items())
            try:
                c,_=baseline_contract(bundle,'scene.usda');core=evaluate_packs(None,'scene.usda',bundle_root=bundle,contract_data=c)
            except Exception as exc:core=discovery_failure_report(exc,bundle,64,'scene.usda')
            write_report(core,target/'default')
            row.update(default_verdict=core['verdict'],inventory=core.get('coverage',{}).get('inventory'),
                       default_checks=core.get('coverage',{}).get('audit',{}).get('rows',[]),
                       default_evidence=core.get('checks',[]),briefs={})
            for mode,level in [('provided',planned['level']),('full','detailed')]:
                try:
                    result=evaluate_brief(f'briefs/{level}.json','scene.usda',bundle_root=bundle,out=target/mode)
                    checked=result.get('core_report') or {}
                    row['briefs'][mode]=dict(core=result['core_verdict'],scope=result['assessment_verdict'],
                        requirements=result.get('items',[]),
                        spec_checks=[x for x in checked.get('checks',[]) if x['id'].startswith('spec.')],errors=result.get('errors',[]))
                except Exception as exc:row['briefs'][mode]=dict(error=type(exc).__name__+': '+str(exc),spec_checks=[])
            try:row['views']=render(bundle,target/'views')
            except Exception as exc:row['view_error']=type(exc).__name__+': '+str(exc)
            assert all(sha(bundle/k)==v for k,v in hashes.items());row['source_unchanged']=True
        rows.append(row)
        rows.sort(key=lambda r:next(i for i,c in enumerate(schedule) if c['id']==r['id']))
        save(receipt,dict(checker_sha256=implementation_digest(),schedule=schedule,rows=rows))
        print(json.dumps(dict(id=row['id'],status=trial['status'],default=row.get('default_verdict'),
            supplied=[c['status'] for c in row.get('briefs',{}).get('provided',{}).get('spec_checks',[])],
            full=[c['status'] for c in row.get('briefs',{}).get('full',{}).get('spec_checks',[])])),flush=True)

if __name__=='__main__':main()
