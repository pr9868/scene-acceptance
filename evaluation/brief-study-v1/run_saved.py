"""Phase one: unchanged retained delivery, several counterfactual briefs."""
import argparse
import json
from pathlib import Path
from scene_acceptance.briefs import evaluate_brief
from scene_acceptance.engine import implementation_digest
from scene_acceptance.model import sha
from scene_acceptance.pack_engine import evaluate_packs
from scene_acceptance.profiles import baseline_contract
from scene_acceptance.report import write_report

def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);root=args.inputs/'panel'
    original={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
    c,_=baseline_contract(root,'scene.usda');r=evaluate_packs(None,'scene.usda',bundle_root=root,contract_data=c)
    write_report(r,args.out/'default')
    rows=[dict(condition='default',core=r['verdict'],scope='No brief supplied',report='default/report.html')]
    for mode in ('size','image-a','image-b','conflict'):
        r=evaluate_brief(f'briefs/{mode}.json','scene.usda',bundle_root=root,out=args.out/mode)
        rows.append(dict(condition=mode,core=r['core_verdict'],scope=r['assessment_verdict'],report=f'{mode}/report/report.html',
                         requirements=[{'id':x['id'],'status':x['status']} for x in r['items']]))
    assert all(sha(root/p)==h for p,h in original.items())
    (args.out/'results.json').write_text(json.dumps(dict(rows=rows,source_hashes=original,unchanged=True,checker_sha256=implementation_digest()),indent=2)+'\n')
    print(json.dumps(rows,indent=2))

if __name__=='__main__': main()
