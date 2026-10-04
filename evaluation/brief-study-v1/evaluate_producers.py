"""Run the same frozen evaluator/briefs over every unchanged model delivery."""
import argparse
import json
from pathlib import Path
from scene_acceptance.briefs import evaluate_brief
from scene_acceptance.engine import implementation_digest
from scene_acceptance.model import sha
from scene_acceptance.profiles import baseline_contract,discovery_failure_report
from scene_acceptance.pack_engine import evaluate_packs
from scene_acceptance.report import write_report
from render_views import render

def main():
    p=argparse.ArgumentParser();p.add_argument('--production',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--resume',action='store_true');args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=args.resume);rows=[]
    if args.resume and (args.out/'results.json').exists():
        previous=json.loads((args.out/'results.json').read_text())
        assert previous['checker_sha256']==implementation_digest(),'Cannot mix evaluator revisions in one report'
        rows=previous['rows']
    # Per-case completion receipts also support incremental assessment while independent trials run.
    trials=[]
    for rep in range(1,4):
        for arm in ('simple','detailed'):
            receipt=args.production/f'{arm}-{rep:02d}/metrics.json'
            if receipt.exists(): trials.append(json.loads(receipt.read_text()))
    for trial in trials:
        if trial['id'] in {r.get('id',r.get('trial',{}).get('id')) for r in rows}:continue
        case=args.production/trial['id'];bundle=case/'delivery';target=args.out/trial['id'];target.mkdir()
        if trial['status']!='DELIVERED':
            rows.append(dict(trial=trial,unassessed=trial['error']));continue
        hashes=json.loads((case/'delivery-manifest.json').read_text())['files']
        assert all(sha(bundle/k)==v for k,v in hashes.items())
        try:
            c,_=baseline_contract(bundle,'scene.usda');r=evaluate_packs(None,'scene.usda',bundle_root=bundle,contract_data=c)
        except Exception as exc:r=discovery_failure_report(exc,bundle,64,'scene.usda')
        write_report(r,target/'default')
        row=dict(id=trial['id'],arm=trial['arm'],repetition=trial['repetition'],default_verdict=r['verdict'],
                 inventory=r['coverage'].get('inventory'),default_checks=r['coverage'].get('audit',{}).get('rows',[]),briefs={})
        for mode in ('text','image','changed'):
            result=evaluate_brief(f'briefs/{mode}.json','scene.usda',bundle_root=bundle,out=target/mode)
            core=result.get('core_report')
            row['briefs'][mode]=dict(core=result['core_verdict'],scope=result['assessment_verdict'],
                requirements=[{k:x[k] for k in ('id','statement','status','check_ids','review_required')} for x in result.get('items',[])],
                spec_checks=[x for x in (core or {}).get('checks',[]) if x['id'].startswith('spec.')],
                errors=result.get('errors',[]))
        try:row['views']=render(bundle,target/'views')
        except Exception as exc:row['view_error']=type(exc).__name__+': '+str(exc)
        assert all(sha(bundle/k)==v for k,v in hashes.items())
        row['source_unchanged']=True;rows.append(row)
        (args.out/'results.json').write_text(json.dumps(dict(checker_sha256=implementation_digest(),rows=rows),indent=2)+'\n')
        print(json.dumps({k:row[k] for k in ('id','default_verdict','source_unchanged')}),flush=True)

if __name__=='__main__':main()
