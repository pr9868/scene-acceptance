"""Exact adapter copied from the published incline experiment; admission tightened by worker."""
import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade

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

