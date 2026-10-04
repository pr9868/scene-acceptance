"""Post-freeze follow-up, kept separate from the ten primary comparisons."""
import argparse
import json
from pathlib import Path
import shutil
from pxr import Gf, Usd, UsdGeom
from scene_acceptance.engine import implementation_digest
from scene_acceptance.model import sha
from scene_acceptance.profiles import baseline_contract, discovery_failure_report
from scene_acceptance.pack_engine import evaluate_packs
from scene_acceptance.packs import default_registry
from scene_acceptance.report import write_report
from study import TASKS, position, save, SOURCE

def assess(bundle,task,out):
    try:
        contract,_=baseline_contract(bundle,'scene.usda')
        contract['id']='secondary-201-'+task['id'];contract['profile']={'id':'secondary-trajectory201','version':'1.0.0'}
        contract['intended_use']='Exploratory 201-sample position comparison; no continuous proof; separate from the frozen primary study'
        desc=default_registry().get('motion.timing').describe()
        contract['packs']={'motion.timing':{'version':desc['version'],'sha256':desc['implementation_sha256']}}
        contract['checks']=[dict(id='secondary.trajectory201',pack='motion.timing',check='positions',required=True,
            specification_source=SOURCE,parameters=dict(path=task['mover'],tolerance_m=.001,
            samples=[dict(elapsed_s=round(i*task['duration']/200,8),world_origin_m=position(task,i*task['duration']/200)) for i in range(201)]))]
        out.mkdir(parents=True,exist_ok=False);save(out/'contract.json',contract)
        result=evaluate_packs(None,'scene.usda',bundle_root=bundle,contract_data=contract)
    except Exception as exc:result=discovery_failure_report(exc,bundle,64,'scene.usda')
    write_report(result,out/'report')
    c=next((x for x in result.get('checks',[]) if x['id']=='secondary.trajectory201'),None)
    items=(c or {}).get('evidence',{}).get('observations',{}).get('findings',[])
    return dict(status=c['status'] if c else 'UNASSESSED',verdict=result['verdict'],check=c,
                positions_assessed=len(items),positions_passed=sum(x['status']=='PASS' for x in items),
                positions_failed=sum(x['status']=='FAIL' for x in items))

def controls(root):
    out=root/'secondary-controls';out.mkdir(exist_ok=False)
    task=next(t for t in TASKS if t['id']=='rotary');source=root/'controls/scenes/rotary-positive'
    chord=assess(source,task,out/'chord-21')
    assert chord['status']=='FAIL' and chord['positions_assessed']==201 and chord['positions_failed']>0
    assert all(x['status']=='PASS' for i,x in enumerate(chord['check']['evidence']['observations']['findings']) if i%10==0)
    exact=out/'rotary-analytic';shutil.copytree(source,exact)
    stage=Usd.Stage.Open(str(exact/'scene.usda'));m=UsdGeom.Xformable(stage.GetPrimAtPath(task['mover']))
    translate,scale=m.GetOrderedXformOps();translate.GetAttr().Clear();translate.Set(Gf.Vec3d(.65,0,1.05))
    rotate=m.AddRotateZOp(UsdGeom.XformOp.PrecisionDouble);rotate.Set(0.,0);rotate.Set(180.,96)
    m.SetXformOpOrder([rotate,translate,scale]);stage.GetRootLayer().Save()
    circular=assess(exact,task,out/'analytic-circle')
    assert circular['status']=='PASS' and circular['positions_passed']==201
    save(out/'summary.json',dict(chord=chord,analytic=circular,checker_sha256=implementation_digest()))
    print(json.dumps(dict(chord=chord['status'],chord_failed=chord['positions_failed'],analytic=circular['status'])))

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--controls',action='store_true');a=p.parse_args();root=a.root
    if a.controls:controls(root);return
    out=root/'secondary';out.mkdir(exist_ok=True);receipt=out/'results.json'
    rows=json.loads(receipt.read_text())['rows'] if receipt.exists() else []
    for path in sorted((root/'production').glob('*/metrics.json')):
        metrics=json.loads(path.read_text())
        if metrics['id'] in {r['id'] for r in rows}:continue
        row={k:metrics[k] for k in ('id','task','level','repetition')}
        if metrics['status']!='DELIVERED':row.update(status='UNASSESSED',reason=metrics['error'])
        else:
            bundle=path.parent/'delivery';hashes=json.loads((path.parent/'delivery-manifest.json').read_text())['files']
            assert all(sha(bundle/f)==h for f,h in hashes.items())
            row.update(assess(bundle,next(t for t in TASKS if t['id']==metrics['task']),out/metrics['id']))
            assert all(sha(bundle/f)==h for f,h in hashes.items())
        rows.append(row);save(receipt,dict(checker_sha256=implementation_digest(),rows=rows))
        print(json.dumps({k:v for k,v in row.items() if k!='check'}),flush=True)

if __name__=='__main__':main()
