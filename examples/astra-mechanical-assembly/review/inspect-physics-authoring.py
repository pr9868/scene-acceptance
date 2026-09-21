"""Inspect the frozen assembly's authored USD physics representation; no simulation."""
from pathlib import Path
import hashlib, json
from pxr import Usd, UsdPhysics

root=Path(__file__).resolve().parents[1]
path=root/'submission/output/crank_slider.usdc'
digest=hashlib.sha256(path.read_bytes()).hexdigest()
assert digest==json.loads((root/'evidence/submission-manifest.json').read_text())['output/crank_slider.usdc']
stage=Usd.Stage.Open(str(path))
apis={'rigid_bodies':UsdPhysics.RigidBodyAPI,'colliders':UsdPhysics.CollisionAPI,
      'mass_properties':UsdPhysics.MassAPI,'physics_materials':UsdPhysics.MaterialAPI,
      'articulation_roots':UsdPhysics.ArticulationRootAPI}
found={name:[] for name in apis}
found.update({'joints':[],'physics_scenes':[]})
authored_properties=[]
other_physics_schemas=[]
for prim in stage.TraverseAll():
    for name,api in apis.items():
        if prim.HasAPI(api):found[name].append(str(prim.GetPath()))
    if prim.IsA(UsdPhysics.Joint):found['joints'].append(str(prim.GetPath()))
    if prim.IsA(UsdPhysics.Scene):found['physics_scenes'].append(str(prim.GetPath()))
    for schema in prim.GetAppliedSchemas():
        if 'phys' in schema.lower():other_physics_schemas.append({'prim':str(prim.GetPath()),'schema':schema})
    for prop in prim.GetAuthoredProperties():
        if prop.GetName().startswith(('physics:','physx')):authored_properties.append(str(prop.GetPath()))
assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
record={'method':'Coordinator read-only inspection of the submitted USD through OpenUSD, after the original production task. No solver, simulation, agent repair or behavioral evaluation was run.',
        'scene_sha256':digest,'openusd_version':list(Usd.GetVersion()),
        'schema_counts':{k:len(v) for k,v in found.items()},'schema_paths':found,
        'authored_physics_properties':authored_properties,'applied_physics_schemas':other_physics_schemas,
        'interpretation':('Authored physics configuration is present; inspect the schema paths and properties before deciding scope.' if any(found.values()) or authored_properties or other_physics_schemas else 'The inspected stage has no authored UsdPhysics bodies, colliders, mass APIs, physical-material APIs, articulation roots, joints or physics scene. Its saved animation is not a delivered rigid-body simulation model.'),
        'limits':'Checks the composed stage in its saved configuration, not another file, engine-side model or future conversion. It neither validates dynamic behavior nor rejects the original visualization brief.'}
(root/'evidence/coordinator-physics-authoring.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'counts':record['schema_counts'],'properties':len(authored_properties),'scene_unchanged':True}))
