"""Coordinator readback of a frozen submitted USD; does not modify the scene."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,json,math
from pxr import Usd,UsdGeom,UsdShade
p=argparse.ArgumentParser();p.add_argument('scene',type=Path);p.add_argument('out',type=Path);args=p.parse_args()
initial=hashlib.sha256(args.scene.read_bytes()).hexdigest();stage=Usd.Stage.Open(str(args.scene));assert stage
scale=UsdGeom.GetStageMetersPerUnit(stage);start=stage.GetStartTimeCode();end=stage.GetEndTimeCode();rate=stage.GetTimeCodesPerSecond()
rows=[];materials=[];types=Counter()
for prim in stage.Traverse():
 types[prim.GetTypeName()]+=1
 row={'path':str(prim.GetPath()),'type':prim.GetTypeName()}
 animated={a.GetName():a.GetTimeSamples() for a in prim.GetAttributes() if a.GetNumTimeSamples()}
 if animated:row['animated_attributes']={k:{'count':len(v),'first':v[0],'last':v[-1]} for k,v in animated.items()}
 if prim.IsA(UsdGeom.Mesh):
  mesh=UsdGeom.Mesh(prim);row['points']=len(mesh.GetPointsAttr().Get() or []);row['faces']=len(mesh.GetFaceVertexCountsAttr().Get() or [])
  material,_=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial();row['bound_material']=str(material.GetPath()) if material else None
 if prim.IsA(UsdShade.Material):
  mat=UsdShade.Material(prim);source=mat.ComputeSurfaceSource();shader=source[0] if source else None
  m={'path':str(prim.GetPath()),'shader_id':str(shader.GetIdAttr().Get()) if shader else None,'inputs':{}}
  if shader:
   for inp in shader.GetInputs():
    value=inp.Get();m['inputs'][inp.GetBaseName()]=str(value)
  materials.append(m)
 if UsdGeom.Xformable(prim):
  row['world_origins_m']=[]
  for seconds in [0,.5,1,1.5,2,2.5,3,3.5,4]:
   tc=start+seconds*rate;v=UsdGeom.XformCache(Usd.TimeCode(tc)).GetLocalToWorldTransform(prim).ExtractTranslation()
   row['world_origins_m'].append({'elapsed_s':seconds,'time_code':tc,'xyz':[float(x)*scale for x in v]})
 rows.append(row)
report={'scene':args.scene.name,'sha256':initial,'openusd':list(Usd.GetVersion()),'metadata':{'meters_per_unit':scale,'units_authored':stage.HasAuthoredMetadata('metersPerUnit'),'up_axis':str(UsdGeom.GetStageUpAxis(stage)),'start':start,'end':end,'time_codes_per_second':rate,'clock_authored':stage.HasAuthoredMetadata('timeCodesPerSecond'),'duration_s':(end-start)/rate if rate>0 else None,'default_prim':str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else None},'type_counts':dict(types),'materials':materials,'prims':rows,'limits':'Saved USD readback at nine specified times; no collision, physical or continuous-path certification.'}
assert hashlib.sha256(args.scene.read_bytes()).hexdigest()==initial
args.out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'metadata':report['metadata'],'types':report['type_counts'],'materials':len(materials),'sha256':initial}))
