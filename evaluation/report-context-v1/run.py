"""Generate new report examples from copied frozen artifacts; preserve all originals."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from scene_acceptance import evaluate
from scene_acceptance.model import sha
from scene_acceptance.profiles import baseline_contract
from scene_acceptance.pack_engine import evaluate_packs
from scene_acceptance.report import write_report, E, STYLE
from scene_acceptance.review import assess
from scene_acceptance.review.__main__ import write_report as write_review

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('consolidation_replay',ROOT/'evaluation/consolidation-v1/run.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def save(path,obj): path.write_text(json.dumps(obj,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    fixtures=ROOT/'evaluation/consolidation-v1/fixtures'
    frozen={str(p.relative_to(fixtures)):sha(p) for p in fixtures.rglob('*') if p.is_file()}
    rows=[]
    for id,fixture,label,mode in [
        ('general-panel','original-panel-png','Textured panel — general diagnostics only','baseline'),
        ('wrong-texture','panel-wrong-readable-texture','Readable texture with the wrong preset content','preset'),
        ('human-source-control','original-panel-png','Synthetic reporting control — recorded human specification','synthetic-human')]:
        case=out/id;bundle=case/'delivery';shutil.copytree(fixtures/fixture,bundle)
        if mode=='baseline':
            c,_=baseline_contract(bundle,'scene.usda');c['report_context']={'scene_name':label}
            r=evaluate_packs(None,'scene.usda',bundle_root=bundle,contract_data=c)
        else:
            c=helper.migrate_contract(bundle);c['report_context']={'scene_name':label}
            if mode=='synthetic-human':
                for check in c['checks']:
                    if check['id'] in ('brief.panel.dimensions','brief.panel.pixels'):
                        check['specification_source']={'provided_by':'human','reference':'Synthetic provenance control for software verification; NOT an actual human instruction'}
            save(bundle/'contract.json',c)
            r=evaluate('contract.json','scene.usda',bundle_root=bundle,expected_contract_sha256=sha(bundle/'contract.json'))
        write_report(r,case/'report')
        rows.append(dict(id=id,label=label,artifact=r['verdict'],scope='No full specification map supplied'))
    case=out/'motion-review'
    subprocess.run([sys.executable,str(ROOT/'examples/declared-scope/prepare.py'),'--out',str(case)],check=True,stdout=subprocess.DEVNULL)
    r=assess('plan.json',review_root=case/'owner',bundle_root=case/'delivery',expected_plan_sha256=sha(case/'owner/plan.json'))
    write_review(r,case/'report')
    assert r['core_verdict']=='ACCEPT_FOR_USE' and r['assessment_verdict']=='NEEDS_REVIEW'
    rows.append(dict(id='motion-review',label='Crank-slider — passing samples and unresolved continuous motion',artifact=r['core_verdict'],scope=r['assessment_verdict']))
    for row in rows:
        overview=json.loads((out/row['id']/'report/overview.json').read_text())
        row['matrix']=overview['matrix'];row['human_specification_entries']=overview['human_specifications']
    assert rows[0]['matrix'][0]['total']==27 and rows[0]['human_specification_entries']==0
    assert rows[1]['artifact']=='REJECT' and rows[1]['human_specification_entries']==0
    assert rows[2]['human_specification_entries']==2 and rows[2]['artifact']=='ACCEPT_FOR_USE'
    assert all(sha(fixtures/p)==h for p,h in frozen.items())
    save(out/'summary.json',rows);save(out/'input-integrity.json',{'unchanged':True,'files':frozen})
    table=''.join(f'<tr><td><a href="{E(r["id"])}/report/report.html">{E(r["label"])}</a></td><td>{E(r["artifact"])}</td><td>{E(r["scope"])}</td></tr>' for r in rows)
    (out/'index.html').write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Scene and specification reports</title><style>{STYLE}</style><main><h1>Scene and specification reports</h1><p>New reports from copied saved artifacts. No producer code or model calls. The human-source example is a clearly labeled synthetic reporting control, not a claim about an actual human brief.</p><div class="scroll"><table><thead><tr><th>Scene / example</th><th>Artifact result</th><th>Specification coverage</th></tr></thead><tbody>{table}</tbody></table></div><p><a href="summary.json">Result records</a> · <a href="input-integrity.json">Original-file integrity</a></p></main></html>')
    print(json.dumps({'reports':len(rows),'original_files_unchanged':len(frozen)}))


if __name__=='__main__': main()
