"""Read back the exported USD at frames and subframes; verify actual world poses."""
from pxr import Usd, UsdGeom, UsdShade, Gf
from pathlib import Path
import json, math
ROOT=Path(__file__).resolve().parents[1]
s=Usd.Stage.Open(str(ROOT/'output/crank_slider.usdc'))
prims=list(s.Traverse()); byname={p.GetName():p for p in prims}
assert s.GetStartTimeCode()==0 and s.GetEndTimeCode()==240
assert s.GetTimeCodesPerSecond()==60 and s.GetFramesPerSecond()==60
assert UsdGeom.GetStageMetersPerUnit(s)==1 and UsdGeom.GetStageUpAxis(s)=='Z'
assert s.GetDefaultPrim().IsValid()
names=['Crank_Center','Crank_Pin','Slider_Pin','Connecting_Rod_Pose']
assert all(n in byname for n in names)
maxerr={'radius_m':0.,'rod_length_m':0.,'slider_guide_m':0.,'rod_start_pin_m':0.,'rod_end_pin_m':0.,'analytical_slider_m':0.}
samples=[]
for i in range(961):
    f=i/4; cache=UsdGeom.XformCache(Usd.TimeCode(f))
    def pos(n):return cache.GetLocalToWorldTransform(byname[n]).Transform(Gf.Vec3d(0,0,0))
    c,p,q=[pos(n) for n in names[:3]]
    rodmat=cache.GetLocalToWorldTransform(byname['Connecting_Rod_Pose'])
    theta=2*math.pi*f/240
    expected=-.09+.035*math.cos(theta)+math.sqrt(.11**2-(.035*math.sin(theta))**2)
    errs={'radius_m':abs((p-c).GetLength()-.035),'rod_length_m':abs((q-p).GetLength()-.11),'slider_guide_m':max(abs(q[1]),abs(q[2]-.102)),'rod_start_pin_m':(rodmat.Transform(Gf.Vec3d(0,0,0))-p).GetLength(),'rod_end_pin_m':(rodmat.Transform(Gf.Vec3d(.110,0,0))-q).GetLength(),'analytical_slider_m':abs(q[0]-expected)}
    for k,v in errs.items():maxerr[k]=max(maxerr[k],v)
    if i%240==0:samples.append({'frame':f,'crank_center':list(c),'crank_pin':list(p),'slider_pin':list(q)})
assert max(maxerr.values())<.000015,maxerr
def endpoints(f):
    cache=UsdGeom.XformCache(Usd.TimeCode(f))
    return [cache.GetLocalToWorldTransform(byname[n]) for n in names]
loop_error=max(abs(a[i][j]-b[i][j]) for a,b in zip(endpoints(0),endpoints(240)) for i in range(4) for j in range(4))
assert loop_error<1e-6
meshes=[p for p in prims if p.IsA(UsdGeom.Mesh)]; mats=[p for p in prims if p.IsA(UsdShade.Material)]
assert len(meshes)>80 and len(mats)>=7
for p in meshes:
    m=UsdGeom.Mesh(p);points=m.GetPointsAttr().Get()
    assert points and all(math.isfinite(v) for pt in points for v in pt)
    assert UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()[0]
report={'status':'PASS','usd_version':Usd.GetVersion(),'metadata':{'metersPerUnit':1,'upAxis':'Z','fps':60,'timeCodesPerSecond':60,'start':0,'end':240,'seconds':4},'mesh_count':len(meshes),'material_count':len(mats),'samples_tested':961,'maximum_errors':maxerr,'loop_matrix_max_error':loop_error,'reference_paths':{n:str(byname[n].GetPath()) for n in names},'quarter_cycle_poses':samples,'note':'Subframe transforms linearly interpolate 60 Hz samples; up to 15 micrometres tolerance, not physical validation.'}
(ROOT/'logs/usd-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
