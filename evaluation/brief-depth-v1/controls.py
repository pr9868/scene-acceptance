"""Known numeric fixtures and explicit perturbations, never producer failures."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
from pxr import Gf, Usd, UsdGeom
from scene_acceptance.briefs import evaluate_brief
from scene_acceptance.engine import implementation_digest
from study import TASKS, samples, raster, save

REPO=Path(__file__).resolve().parents[2]

def cube(stage,path,size,center):
    p=UsdGeom.Cube.Define(stage,path);p.CreateSizeAttr(1)
    p.CreateExtentAttr([(-.5,-.5,-.5),(.5,.5,.5)])
    p.AddTranslateOp().Set(Gf.Vec3d(*center));p.AddScaleOp().Set(Gf.Vec3d(*size))
    p.CreateDisplayColorAttr([(.4,.6,.7)]);return p

def fixture(task,destination,inputs):
    shutil.copytree(REPO/'evaluation/consolidation-v1/fixtures/original-panel-png',destination)
    shutil.copytree(inputs/task['id']/'briefs',destination/'briefs')
    raster(destination/'textures/label.png',task['pixels'])
    stage=Usd.Stage.Open(str(destination/'scene.usda'))
    stage.SetStartTimeCode(0);stage.SetEndTimeCode(task['duration']*24);stage.SetTimeCodesPerSecond(24)
    cube(stage,'/World/Base',task['size'],task['center'])
    cube(stage,'/World/Cabinet',[.4,.4,1],[0,task['size'][1]/2+task['gap']+.45,.5])
    mover=cube(stage,task['mover'],task['mover_size'],samples(task)[0]['world_origin_m'])
    attr=mover.GetPrim().GetAttribute('xformOp:translate')
    for sample in samples(task):attr.Set(Gf.Vec3d(*sample['world_origin_m']),sample['elapsed_s']*24)
    UsdGeom.Xform.Define(stage,task['repeated'])
    for i in range(task['count']):
        c=UsdGeom.Cylinder.Define(stage,task['repeated']+f'/Part{i:02d}')
        c.CreateRadiusAttr(.035);c.CreateHeightAttr(.15);c.CreateAxisAttr('Z')
        c.CreateExtentAttr([(-.035,-.035,-.075),(.035,.035,.075)])
        c.AddTranslateOp().Set(Gf.Vec3d(-.7+.2*i,0,task['center'][2]+task['size'][2]/2+.075))
    # Extra boxes make this a visibility/count control, not a claimed realistic assembly.
    for i in range(40):cube(stage,f'/World/ControlDetail{i:02d}',[.04,.04,.04],[-1+.05*i,-.5,.25])
    stage.GetRootLayer().Save()

def perturb(task,bundle,kind):
    stage=Usd.Stage.Open(str(bundle/'scene.usda'))
    if kind=='coordinates':UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.y)
    elif kind=='base':stage.GetAttributeAtPath('/World/Base.xformOp:scale').Set(Gf.Vec3d(task['size'][0]*1.1,*task['size'][1:]))
    elif kind=='count':UsdGeom.Cylinder.Define(stage,task['repeated']+'/Extra')
    elif kind=='gap':
        a=stage.GetAttributeAtPath('/World/Cabinet.xformOp:translate');v=a.Get();a.Set(Gf.Vec3d(v[0],v[1]-.6,v[2]))
    elif kind=='mover-size':stage.GetAttributeAtPath(task['mover']+'.xformOp:scale').Set(Gf.Vec3d(task['mover_size'][0]*1.2,*task['mover_size'][1:]))
    elif kind=='clock':stage.SetTimeCodesPerSecond(12)
    elif kind=='time-range':stage.SetStartTimeCode(1);stage.SetEndTimeCode(task['duration']*24+1)
    elif kind in ('endpoints','trajectory'):
        sample=samples(task)[-1 if kind=='endpoints' else 10]
        a=stage.GetAttributeAtPath(task['mover']+'.xformOp:translate');t=sample['elapsed_s']*24;v=a.Get(t)
        a.Set(Gf.Vec3d(v[0]+.05,v[1],v[2]),t)
    elif kind=='image':
        from PIL import Image
        p=bundle/'textures/label.png';im=Image.open(p).copy();v=im.getpixel((0,0));im.putpixel((0,0),tuple(255-x for x in v));im.save(p)
    stage.GetRootLayer().Save()

def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False);rows=[]
    for task in TASKS:
        positive=a.out/'scenes'/f"{task['id']}-positive";positive.parent.mkdir(exist_ok=True)
        fixture(task,positive,a.inputs)
        for kind in ['positive','coordinates','base','count','gap','mover-size','clock','time-range','endpoints','trajectory','image']:
            bundle=positive
            if kind!='positive':
                bundle=a.out/'scenes'/f"{task['id']}-{kind}";shutil.copytree(positive,bundle);perturb(task,bundle,kind)
            result=evaluate_brief('briefs/detailed.json','scene.usda',bundle_root=bundle,out=a.out/'reports'/f"{task['id']}-{kind}")
            core=result['core_report'];statuses={c['id']:c['status'] for c in core['checks']}
            selected={k:v for k,v in statuses.items() if k.startswith('spec.')}
            matched=(len(selected)==10 and all(v=='PASS' for v in selected.values())) if kind=='positive' else selected.get('spec.'+kind)=='FAIL'
            if kind=='trajectory':matched=matched and selected['spec.endpoints']=='PASS'
            if kind=='image':matched=matched and statuses['audit.textures']=='PASS'
            rows.append(dict(task=task['id'],control=kind,matched=matched,core_verdict=core['verdict'],checks=selected))
            save(a.out/'summary.json',dict(checker_sha256=implementation_digest(),cases=rows))
            print(json.dumps(rows[-1]),flush=True)
    assert len(rows)==33 and all(r['matched'] for r in rows),'Control mismatch; inspect retained evidence before generation'

if __name__=='__main__':main()
