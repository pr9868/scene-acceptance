"""Replay frozen artifacts without editing originals or running producer programs."""
import argparse
import json
from pathlib import Path
import shutil
from scene_acceptance import evaluate
from scene_acceptance.contract_upgrade import propose_upgrade
from scene_acceptance.model import sha, digest_json
from scene_acceptance.report import write_report
from scene_acceptance.supplemental import four_job_pack

ROOT = Path(__file__).resolve().parent


def save(path, value): path.write_text(json.dumps(value, indent=2) + '\n')


def migrate_contract(bundle):
    c = json.loads((bundle/'contract.json').read_text())
    retained_contract_sha256 = sha(bundle/'contract.json')
    retained_contract_digest = digest_json(json.loads((bundle/'contract.json').read_text()))
    old_brief_pin = c['packs']['fresh.brief'].copy()
    c['packs'].pop('fresh.brief')
    pack = four_job_pack()
    c['packs'][pack.id] = {'version':pack.version,'sha256':pack.describe()['implementation_sha256']}
    for check in c['checks']:
        if check['pack'] == 'fresh.brief': check['pack'] = pack.id
    c, upgrades = propose_upgrade(c)
    upgrades['original_sha256'] = retained_contract_digest
    upgrades['original_file_sha256'] = retained_contract_sha256
    upgrades['prior_migrations'] = [dict(before_pack='fresh.brief', after_pack=pack.id,
        before_pin=old_brief_pin, after_pin=c['packs'][pack.id],
        reason='Explicit migration of the retained local supplemental provider to the installed pack')]
    upgrades['requires_review'] = True
    save(bundle/'contract-upgrades.json', upgrades)
    save(bundle/'contract.json',c)
    return c


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    frozen=json.loads((ROOT/'frozen-inputs.json').read_text())
    assert all(sha(ROOT/p)==h for p,h in frozen.items())
    rows=[]
    for case in json.loads((ROOT/'cases.json').read_text()):
        directory=args.out/case['id'];bundle=directory/'bundle'
        shutil.copytree(ROOT/'fixtures'/case['id'],bundle)
        migrate_contract(bundle)
        result=evaluate('contract.json','scene.usda',bundle_root=bundle,
                        baseline_path='baseline.usda' if case['job']=='tray-translated' else None,
                        expected_contract_sha256=sha(bundle/'contract.json'))
        write_report(result,directory/'report')
        matched=result['verdict']!='ACCEPT_FOR_USE' if case['expected']=='NOT_ACCEPTED' else result['verdict']==case['expected']
        rows.append(case | {'actual':result['verdict'],'matched':matched,
                           'checks':{r['id']:r['status'] for r in result['checks']}})
        save(args.out/'summary.json',rows)
        print(case['id'],result['verdict'],flush=True)
    assert all(sha(ROOT/p)==h for p,h in frozen.items())
    assert all(r['matched'] for r in rows), rows


if __name__=='__main__': main()
