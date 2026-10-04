"""Diagnostic surface projections of saved USD, not an RTX/material render."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
from pxr import Gf, Usd, UsdGeom, UsdShade
from scene_acceptance.artifact import EvidenceBundle, UsdArtifact
from scene_acceptance.model import sha
from scene_acceptance.profiles import baseline_contract

def polygons(prim,time):
    if prim.IsA(UsdGeom.Cube):
        s=UsdGeom.Cube(prim).GetSizeAttr().Get(time)/2
        pts=[(x*s,y*s,z*s) for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        faces=[[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    elif prim.IsA(UsdGeom.Cylinder):
        p=UsdGeom.Cylinder(prim);r=p.GetRadiusAttr().Get(time);h=p.GetHeightAttr().Get(time)/2;axis=p.GetAxisAttr().Get(time)
        pts=[]
        for z in (-h,h):
            for i in range(20):
                x,y=r*math.cos(i*math.tau/20),r*math.sin(i*math.tau/20)
                pts.append((z,x,y) if axis=='X' else (x,z,y) if axis=='Y' else (x,y,z))
        faces=[list(range(20)),list(range(20,40))]+[[i,(i+1)%20,(i+1)%20+20,i+20] for i in range(20)]
    elif prim.IsA(UsdGeom.Sphere):
        r=UsdGeom.Sphere(prim).GetRadiusAttr().Get(time);pts=[]
        for j in range(9):
            for i in range(16):
                phi=j*math.pi/8;theta=i*math.tau/16
                pts.append((r*math.sin(phi)*math.cos(theta),r*math.sin(phi)*math.sin(theta),r*math.cos(phi)))
        faces=[[j*16+i,j*16+(i+1)%16,(j+1)*16+(i+1)%16,(j+1)*16+i] for j in range(8) for i in range(16)]
    elif prim.IsA(UsdGeom.Mesh):
        p=UsdGeom.Mesh(prim);pts=p.GetPointsAttr().Get(time);counts=p.GetFaceVertexCountsAttr().Get(time);indices=p.GetFaceVertexIndicesAttr().Get(time)
        if pts is None or counts is None or indices is None or len(pts)>100000: raise ValueError('Missing or excessive mesh arrays')
        faces=[];offset=0
        for n in counts:
            face=list(indices[offset:offset+n]);offset+=n
            if n<3 or any(i<0 or i>=len(pts) for i in face):raise ValueError('Invalid face indices')
            faces.append(face)
    else: raise ValueError('Unsupported geometry type '+prim.GetTypeName())
    return pts,faces

def render(bundle,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);bundle=Path(bundle)
    c,_=baseline_contract(bundle,'scene.usda');artifact=UsdArtifact(EvidenceBundle(bundle,c['allowed_dependencies']),'scene.usda');stage=artifact.stage
    rate=stage.GetTimeCodesPerSecond();start=stage.GetStartTimeCode();records=[];times=[];fit=[]
    up=str(UsdGeom.GetStageUpAxis(stage))
    duration=(stage.GetEndTimeCode()-start)/rate
    if not math.isfinite(duration) or duration<0: raise ValueError("Invalid stage duration for diagnostic views")
    for seconds in (0,round(duration/2,6),round(duration,6)):
        tc=Usd.TimeCode(start+seconds*rate);xf=UsdGeom.XformCache(tc);surfaces=[];covered=[];skipped=[]
        for prim in stage.Traverse():
            if not prim.IsA(UsdGeom.Gprim):continue
            if UsdGeom.Imageable(prim).ComputeVisibility(tc)==UsdGeom.Tokens.invisible:continue
            try:
                pts,faces=polygons(prim,tc);matrix=xf.GetLocalToWorldTransform(prim)
                world=[matrix.Transform(Gf.Vec3d(*p)) for p in pts]
                if up=='Y':world=[Gf.Vec3d(p[0],-p[2],p[1]) for p in world]
                if not all(math.isfinite(v) for p in world for v in p):raise ValueError('Non-finite geometry')
                colors=UsdGeom.Gprim(prim).GetDisplayColorAttr().Get(tc);color=list(colors[0]) if colors else [.52,.62,.7]
                material,_=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
                if material:
                    shader,_,_=material.ComputeSurfaceSource()
                    value=shader.GetInput('diffuseColor').Get(tc) if shader else None
                    if value is not None:color=list(value)
                rgb=tuple(round(max(0,min(1,x))*255) for x in color)
                for face in faces:
                    poly=[world[i] for i in face];proj=[((p[0]-p[1])*.707,(p[0]+p[1])*.35-p[2]) for p in poly]
                    depth=sum(p[0]+p[1]+p[2]*.7 for p in poly)/len(poly)
                    surfaces.append((depth,proj,rgb))
                    if not any(s in prim.GetName().lower() for s in ('floor','ground','backdrop')):fit.extend(proj)
                covered.append(str(prim.GetPath()))
            except Exception as exc:skipped.append({'path':str(prim.GetPath()),'reason':str(exc)})
        times.append(surfaces);records.append(dict(elapsed_s=seconds,covered_geometry=covered,skipped_geometry=skipped))
    coords=fit or [p for surfaces in times for _,poly,_ in surfaces for p in poly]
    if not coords:raise ValueError('No projected surfaces')
    low=[min(p[i] for p in coords) for i in (0,1)];high=[max(p[i] for p in coords) for i in (0,1)]
    scale=min(570/max(high[0]-low[0],.001),290/max(high[1]-low[1],.001))
    for record,surfaces in zip(records,times):
        image=Image.new('RGB',(640,400),(245,247,249));draw=ImageDraw.Draw(image)
        for depth,poly,rgb in sorted(surfaces,key=lambda x:x[0]):
            screen=[(35+(p[0]-low[0])*scale,65+(p[1]-low[1])*scale) for p in poly]
            draw.polygon(screen,fill=rgb,outline=(75,85,95))
        draw.rectangle((0,0,640,48),fill=(245,247,249));draw.rectangle((0,368,640,400),fill=(245,247,249))
        draw.text((16,12),f"Saved USD surface projection - {record['elapsed_s']} s",fill=(20,30,45))
        draw.text((16,30),'Flat colours; texture mapping, lighting and physical behavior are not rendered.',fill=(60,70,80))
        draw.text((16,378),f"{len(record['covered_geometry'])} geometry prims shown; {len(record['skipped_geometry'])} unsupported/skipped",fill=(20,30,45))
        path=out/f"t{record['elapsed_s']}.png";image.save(path);record['image']=path.name;record['sha256']=sha(path)
    result=dict(candidate=artifact.identity,views=records,renderer_sha256=sha(Path(__file__)),
                authored_up_axis=up,display_up_axis='Z (Y-up scenes rotated for display only)',
                framing='Floor/ground/backdrop named prims are drawn but excluded from automatic framing; the saved scene is never changed.',
                limitation='Diagnostic orthographic surface projections; no ray tracing, material texture, hidden-surface correctness or engineering certification. Cylinder and sphere tessellation is a visualization approximation.')
    (out/'view-evidence.json').write_text(json.dumps(result,indent=2)+'\n');return result
