"""Read exact bounded USD fixtures, run selected rules and a CPU behavior probe.
This adapter supports only these frozen two-box inputs, not arbitrary USD assets.
"""
from pathlib import Path
import csv, hashlib, json, math, platform, sys
from importlib.metadata import version
import numpy as np
import mujoco
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade
from scene_acceptance.engine import evaluate
from scene_acceptance.contract_upgrade import copy_replay_bundle
from scene_acceptance.report import write_report
ROOT=Path(__file__).resolve().parent

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def read_fixture(path):
 s=Usd.Stage.Open(str(path)); assert UsdGeom.GetStageMetersPerUnit(s)==1 and UsdGeom.GetStageUpAxis(s)=='Z'
 assert UsdPhysics.GetStageKilogramsPerUnit(s)==1
 b=s.GetPrimAtPath('/World/Block'); ramp=s.GetPrimAtPath('/World/Ramp')
 assert set(str(p.GetPath()) for p in s.Traverse())=={'/World','/World/Physics','/World/Contact','/World/Ramp','/World/Block'}
 mat=UsdShade.MaterialBindingAPI(b).ComputeBoundMaterial('physics')[0]
 rmat=UsdShade.MaterialBindingAPI(ramp).ComputeBoundMaterial('physics')[0]
 assert mat.GetPath()==rmat.GetPath()
 pm=UsdPhysics.MaterialAPI(mat.GetPrim())
 mu=pm.GetDynamicFrictionAttr().Get(); assert mu==pm.GetStaticFrictionAttr().Get() and pm.GetRestitutionAttr().Get()==0
 result={'mu':mu,'mass':UsdPhysics.MassAPI(b).GetMassAttr().Get(),'material_evidence':mat.GetPrim().GetCustomDataByKey('evidence')}
 for name,p in [('block',b),('ramp',ramp)]:
  assert p.IsA(UsdGeom.Cube) and UsdGeom.Cube(p).GetSizeAttr().Get()==1
  ops=UsdGeom.Xformable(p).GetOrderedXformOps()
  assert [str(o.GetOpName()) for o in ops]==['xformOp:translate','xformOp:rotateY','xformOp:scale']
  assert all(not o.GetAttr().ValueMightBeTimeVarying() for o in ops)
  result[name]={'position':list(ops[0].Get()),'angle_deg':ops[1].Get(),'dimensions':list(ops[2].Get())}
 scene=UsdPhysics.Scene(s.GetPrimAtPath('/World/Physics'))
 assert list(scene.GetGravityDirectionAttr().Get())==[0,0,-1]
 result['gravity']=scene.GetGravityMagnitudeAttr().Get()
 return result

def model_xml(f,dt):
 def vec(v): return ' '.join(format(float(x),'.17g') for x in v)
 return f'''<mujoco model="bounded_incline_probe">
 <compiler angle="degree"/>
 <option timestep="{dt}" gravity="0 0 {-f['gravity']}" integrator="implicitfast" cone="elliptic" solver="Newton" iterations="100" tolerance="1e-10"/>
 <worldbody>
  <geom name="ramp" type="box" size="{vec(np.array(f['ramp']['dimensions'])/2)}" pos="{vec(f['ramp']['position'])}" axisangle="0 1 0 {f['ramp']['angle_deg']}"/>
  <body name="block" pos="{vec(f['block']['position'])}" axisangle="0 1 0 {f['block']['angle_deg']}">
   <freejoint/>
   <geom name="block_shape" type="box" size="{vec(np.array(f['block']['dimensions'])/2)}" mass="{f['mass']}"/>
  </body>
 </worldbody>
 <contact><pair geom1="ramp" geom2="block_shape" condim="3" friction="{f['mu']} {f['mu']} 0 0 0" solref="0.02 1" solimp="0.9 0.95 0.001"/></contact>
</mujoco>'''

def main():
 out=Path(sys.argv[1]).resolve()
 if out.exists(): raise SystemExit('Output exists: choose a new run directory')
 frozen=json.loads((ROOT/'frozen-inputs.json').read_text())
 for file,digest in frozen.items(): assert sha(ROOT/file)==digest, file
 p=json.loads((ROOT/'protocol.json').read_text()); out.mkdir(parents=True)
 result={'protocol_sha256':sha(ROOT/'protocol.json'),'runner_sha256':sha(Path(__file__)), 'versions':{x:version(x) for x in ['mujoco','numpy','usd-core','usd-validation-nvidia','scene-acceptance']},'platform':platform.platform(),'new_model_calls':0,'cases':{}}
 for name,expect in p['expected'].items():
  d=copy_replay_bundle(ROOT/'fixtures'/name, out/'inputs'/name); dest=out/name; dest.mkdir()
  report=evaluate(d/'contract.json',d/'scene.usda',bundle_root=d)
  write_report(report,dest/'configuration')
  f=read_fixture(d/'scene.usda'); (dest/'adapter-readback.json').write_text(json.dumps(f,indent=2)+'\n')
  c={'configuration':report['verdict'],'configuration_matches_expected':report['verdict']==expect['configuration'], 'parameter_evidence':'UNKNOWN: friction is assumed, not measured','runs':[]}
  if f['mass']>0:
   theta=math.radians(f['ramp']['angle_deg']); downhill=np.array([math.cos(theta),0,-math.sin(theta)])
   for dt in p['timesteps_s']:
    sd=dest/f'dt-{dt}'; sd.mkdir()
    xml=model_xml(f,dt); (sd/'model.xml').write_text(xml)
    m=mujoco.MjModel.from_xml_string(xml); data=mujoco.MjData(m); mujoco.mj_forward(m,data)
    start=data.qpos[:3].copy(); trace=[]
    for i in range(round(p['duration_s']/dt)+1):
     displacement=float(np.dot(data.qpos[:3]-start,downhill))
     trace.append([float(data.time),displacement,*[float(v) for v in data.qpos],int(data.ncon)])
     if i<round(p['duration_s']/dt):
      mujoco.mj_step(m,data); mujoco.mj_forward(m,data)
    with (sd/'trace.csv').open('w',newline='') as h:
     w=csv.writer(h); w.writerow(['time_s','along_slope_displacement_m','x','y','z','qw','qx','qy','qz','contacts']); w.writerows(trace)
    assert np.isfinite(np.array(trace,dtype=float)).all()
    maximum=max(abs(t[1]) for t in trace)
    behavior='PASS' if maximum<=p['maximum_displacement_m'] else 'FAIL'
    acceleration=max(0,f['gravity']*(math.sin(theta)-f['mu']*math.cos(theta)))
    summary={'dt_s':dt,'samples':len(trace),'maximum_absolute_displacement_m':maximum,'final_displacement_m':trace[-1][1], 'behavior':behavior,'matches_expected':behavior==expect['behavior'],'ideal_coulomb_displacement_m':0.5*acceleration*p['duration_s']**2,'max_warning_count':max(int(x.number) for x in data.warning),'trace_sha256':sha(sd/'trace.csv'),'model_sha256':sha(sd/'model.xml')}
    (sd/'summary.json').write_text(json.dumps(summary,indent=2)+'\n'); c['runs'].append(summary)
   c['timestep_final_difference_m']=abs(c['runs'][0]['final_displacement_m']-c['runs'][1]['final_displacement_m'])
  result['cases'][name]=c
 result['all_expected_matched']=all(c['configuration_matches_expected'] and all(r['matches_expected'] for r in c['runs']) for c in result['cases'].values())
 (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
 for file,digest in frozen.items(): assert sha(ROOT/file)==digest, file
 print(json.dumps(result,indent=2))
if __name__=='__main__': main()
