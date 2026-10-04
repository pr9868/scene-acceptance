"""Create a copied motion example with a deliberately pending caller review plan."""
import argparse
import json
from pathlib import Path
import shutil
import shlex
from scene_acceptance.model import sha, digest_json
from scene_acceptance.contract_upgrade import propose_upgrade
from scene_acceptance.supplemental import four_job_pack
from scene_acceptance.review.schemas import LAYERS

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    bundle=out/'delivery';owner=out/'owner';owner.mkdir()
    shutil.copytree(ROOT/'evaluation/consolidation-v1/fixtures/original-motion',bundle)
    contract=json.loads((bundle/'contract.json').read_text())
    contract['report_context']={'scene_name':'Crank-slider — sampled checks and continuous-motion requirement'}
    retained_contract_sha256 = sha(bundle/'contract.json')
    retained_contract_digest = digest_json(json.loads((bundle/'contract.json').read_text()))
    old_brief_pin = contract['packs']['fresh.brief'].copy()
    contract['packs'].pop('fresh.brief')
    pack=four_job_pack();contract['packs'][pack.id]={'version':pack.version,'sha256':pack.describe()['implementation_sha256']}
    for check in contract['checks']:
        if check['pack']=='fresh.brief':check['pack']=pack.id
    contract, upgrades = propose_upgrade(contract)
    upgrades['original_sha256'] = retained_contract_digest
    upgrades['original_file_sha256'] = retained_contract_sha256
    upgrades['prior_migrations'] = [dict(before_pack='fresh.brief', after_pack=pack.id,
        before_pin=old_brief_pin, after_pin=contract['packs'][pack.id],
        reason='Explicit migration of the retained local supplemental provider to the installed pack')]
    upgrades['requires_review'] = True
    (bundle/'contract-upgrades.json').write_text(json.dumps(upgrades,indent=2)+'\n')
    (bundle/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    def item(id,statement,checks,review):
        return dict(id=id,layer='explicit',statement=statement,basis='Example only; caller must confirm requirements and relevance',
                    required=True,check_ids=checks,review_required=review,decision_id=None,inference_authorization=None,
                    specification_source={'provided_by':'preset','reference':'Packaged four-job example; not a new human specification'},
                    areas=['motion'],coverage_declaration={'extent':'partial' if review else 'full',
                    'reason':'Finite samples do not establish correctness at every instant' if review else 'The stated finite sample schedule is directly measured; mapping still needs caller review'})
    plan=dict(schema_version='1.0',id='motion-review-example',intended_use='Explore sampled evidence and the remaining continuous-motion obligation',
              contract='contract.json',contract_sha256=sha(bundle/'contract.json'),candidate='scene.usda',baseline=None,
              mapping_review=dict(status='pending',reviewer='Unassigned',reason='Caller must review requirement-to-check relevance'),
              layers={n:dict(scope='included' if n=='explicit' else 'excluded',reason='Only explicit requirements are demonstrated; exclusions need caller review for another use') for n in LAYERS},
              items=[item('sampled-attachments','Both attachments within 0.5 mm at declared sample times',['brief.motion.connections'],False),
                     item('continuous-attachments','Both attachments within 0.5 mm at every intended time',[],True)])
    (owner/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(shlex.join(['check-3d','--review-plan','plan.json','--review-root',str(owner),'--plan-sha256',sha(owner/'plan.json'),
                      '--bundle-root',str(bundle),'--out',str(out/'report')]))


if __name__=='__main__':main()
