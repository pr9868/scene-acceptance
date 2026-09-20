"""Constructed inputs. Freeze these before running the evaluator or simulator."""
from pathlib import Path
import hashlib, json, math
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, Gf
ROOT = Path(__file__).resolve().parent
fixtures = ROOT / 'fixtures'
fixtures.mkdir(exist_ok=True)
protocol = {
 'id':'incline-physics-v1', 'date':'2026-09-19',
 'provenance':'Constructed by the coding assistant following the author\'s request for use-specific evaluation evidence; not an agent benchmark.',
 'task':'Maximum absolute along-slope displacement <= 0.010 m over one simulated second.',
 'angle_deg':20, 'mass_kg':1, 'block_dimensions_m':[0.2,0.2,0.1],
 'ramp_dimensions_m':[20,2,0.2], 'initial_surface_gap_m':0.0001,
 'gravity_m_s2':9.81, 'friction_assumptions':[0.15,0.65], 'timesteps_s':[0.001,0.0005],
 'duration_s':1, 'maximum_displacement_m':0.010,
 'expected':{'low_friction':{'configuration':'ACCEPT_FOR_USE','behavior':'FAIL'},'high_friction':{'configuration':'ACCEPT_FOR_USE','behavior':'PASS'},'negative_mass':{'configuration':'REJECT','behavior':'NOT_RUN'}},
 'reference':'Ideal rigid Coulomb incline calculation for diagnosis only; no physical measurement. Both friction values are assumptions.',
 'sensitivity':'Halve timestep with all other solver settings held fixed; retain difference, not a convergence proof.',
 'scope':'Two boxes, one rigid block, fixed ramp, equal static/dynamic friction, no texture, actuator, robot or arbitrary USD import.'
}
(ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
a = math.radians(20)
n = Gf.Vec3d(math.sin(a),0,math.cos(a))
contract = {
 'schema_version':'2.0','id':'incline-configuration','intended_use':'Check only the selected USD physics configuration rules; no stability or real-world accuracy claim.',
 'profile':{'id':'incline-configuration','version':'1.0.0'},'artifact_format':'usd-local-v1',
 'allowed_dependencies':[],'evidence_sources':[], 'packs':{'nvidia.asset-validator':{'version':'1.0.0'}},
 'checks':[{'id':'physics.configuration','pack':'nvidia.asset-validator','check':'rules','required':True,
  'parameters':{'rules':['MassChecker','RigidBodyChecker','ColliderChecker'],'warnings_as_failures':False}}]
}
for name,mu,mass in [('low_friction',0.15,1),('high_friction',0.65,1),('negative_mass',0.65,-1)]:
 d=fixtures/name; d.mkdir(exist_ok=True)
 s=Usd.Stage.CreateNew(str(d/'scene.usda'))
 UsdGeom.SetStageMetersPerUnit(s,1); UsdGeom.SetStageUpAxis(s,UsdGeom.Tokens.z)
 UsdPhysics.SetStageKilogramsPerUnit(s,1)
 w=UsdGeom.Xform.Define(s,'/World'); s.SetDefaultPrim(w.GetPrim())
 scene=UsdPhysics.Scene.Define(s,'/World/Physics')
 scene.CreateGravityDirectionAttr(Gf.Vec3f(0,0,-1)); scene.CreateGravityMagnitudeAttr(9.81)
 mat=UsdShade.Material.Define(s,'/World/Contact')
 m=UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
 m.CreateStaticFrictionAttr(mu); m.CreateDynamicFrictionAttr(mu); m.CreateRestitutionAttr(0)
 mat.GetPrim().SetCustomDataByKey('evidence','assumed: no measurement supplied')
 for obj,dim,pos in [('Ramp',(20,2,.2),n*(-.1)),('Block',(.2,.2,.1),n*.0501)]:
  c=UsdGeom.Cube.Define(s,'/World/'+obj); c.CreateSizeAttr(1)
  x=UsdGeom.Xformable(c)
  x.AddTranslateOp().Set(pos); x.AddRotateYOp().Set(20); x.AddScaleOp().Set(Gf.Vec3f(*dim))
  UsdPhysics.CollisionAPI.Apply(c.GetPrim())
  UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(mat,materialPurpose='physics')
  if obj=='Block':
   UsdPhysics.RigidBodyAPI.Apply(c.GetPrim()); UsdPhysics.MassAPI.Apply(c.GetPrim()).CreateMassAttr(mass)
 s.GetRootLayer().Save()
 (d/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
files=[ROOT/'protocol.json',*fixtures.rglob('*')]
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.is_file()}
(ROOT/'frozen-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Frozen',len(manifest),'input files')
