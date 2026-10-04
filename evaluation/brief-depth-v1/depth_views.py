"""Depth-tested diagnostic projections. Original painter-sort previews remain retained."""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from pxr import Gf, Usd, UsdGeom, UsdShade
from scene_acceptance.artifact import EvidenceBundle, UsdArtifact
from scene_acceptance.profiles import baseline_contract
from scene_acceptance.model import sha
from diagnostic_views import polygons
from study import save

W,H=960,600

def triangle(canvas,depth,vertices,color):
    v=np.asarray(vertices,dtype=float)
    left=max(0,int(math.floor(v[:,0].min())));right=min(canvas.shape[1]-1,int(math.ceil(v[:,0].max())))
    top=max(0,int(math.floor(v[:,1].min())));bottom=min(canvas.shape[0]-1,int(math.ceil(v[:,1].max())))
    if right<left or bottom<top:return
    a,b,c=v;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(den)<1e-12:return
    yy,xx=np.mgrid[top:bottom+1,left:right+1];xx=xx+.5;yy=yy+.5
    u=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den
    z=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den
    t=1-u-z;candidate=u*a[2]+z*b[2]+t*c[2]
    patch=depth[top:bottom+1,left:right+1];mask=(u>=-1e-9)&(z>=-1e-9)&(t>=-1e-9)&(candidate>patch)
    patch[mask]=candidate[mask];canvas[top:bottom+1,left:right+1][mask]=color

def control():
    # The near triangle must win even when the distant triangle is submitted last.
    pixels=np.zeros((20,20,3),dtype=np.uint8);depth=np.full((20,20),-np.inf)
    tri=[(2,2,3),(18,2,3),(2,18,3)];triangle(pixels,depth,tri,(255,0,0))
    triangle(pixels,depth,[(x,y,1) for x,y,z in tri],(0,0,255));assert tuple(pixels[5,5])==(255,0,0)
    triangle(pixels,depth,[(x,y,4) for x,y,z in tri],(0,255,0));assert tuple(pixels[5,5])==(0,255,0)

def render(bundle,out):
    out.mkdir(parents=True,exist_ok=False)
    contract,_=baseline_contract(bundle,'scene.usda');artifact=UsdArtifact(EvidenceBundle(bundle,contract['allowed_dependencies']),'scene.usda');stage=artifact.stage
    rate=stage.GetTimeCodesPerSecond();start=stage.GetStartTimeCode();duration=(stage.GetEndTimeCode()-start)/rate
    if not math.isfinite(duration) or duration<0:raise ValueError('Invalid duration')
    up=str(UsdGeom.GetStageUpAxis(stage));frames=[];fit=[]
    for seconds in (0,round(duration/2,6),round(duration,6)):
        tc=Usd.TimeCode(start+seconds*rate);xf=UsdGeom.XformCache(tc);surfaces=[];covered=[];skipped=[]
        for prim in stage.Traverse():
            if not prim.IsA(UsdGeom.Gprim) or UsdGeom.Imageable(prim).ComputeVisibility(tc)==UsdGeom.Tokens.invisible:continue
            try:
                pts,faces=polygons(prim,tc);matrix=xf.GetLocalToWorldTransform(prim);world=[matrix.Transform(Gf.Vec3d(*p)) for p in pts]
                if up=='Y':world=[Gf.Vec3d(p[0],-p[2],p[1]) for p in world]
                if not all(math.isfinite(x) for p in world for x in p):raise ValueError('Non-finite geometry')
                colors=UsdGeom.Gprim(prim).GetDisplayColorAttr().Get(tc);color=list(colors[0]) if colors else [.52,.62,.7]
                material,_=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
                if material:
                    shader,_,_=material.ComputeSurfaceSource();value=shader.GetInput('diffuseColor').Get(tc) if shader else None
                    if value is not None:color=list(value)
                for face in faces:
                    poly=np.asarray([world[i] for i in face],dtype=float)
                    projected=np.column_stack(((poly[:,0]-poly[:,1])*.707,(poly[:,0]+poly[:,1])*.35-poly[:,2],poly[:,0]+poly[:,1]+poly[:,2]*.7))
                    if len(poly)<3:continue
                    normal=np.cross(poly[1]-poly[0],poly[2]-poly[0]);size=np.linalg.norm(normal)
                    shade=.7 if size<1e-12 else .55+.45*abs(np.dot(normal/size,np.asarray([.35,-.25,1.])/np.linalg.norm([.35,-.25,1.])))
                    rgb=np.asarray([round(max(0,min(1,float(x)))*255*shade) for x in color],dtype=np.uint8)
                    surfaces.append((projected,rgb))
                    if not any(s in prim.GetName().lower() for s in ('floor','ground','backdrop')):fit.extend(projected[:,:2])
                covered.append(str(prim.GetPath()))
            except Exception as exc:skipped.append(dict(path=str(prim.GetPath()),reason=str(exc)))
        frames.append(dict(elapsed_s=seconds,surfaces=surfaces,covered_geometry=covered,skipped_geometry=skipped))
    if not fit:raise ValueError('No framing geometry')
    fit=np.asarray(fit);low=fit.min(axis=0);high=fit.max(axis=0);scale=min(840/max(high[0]-low[0],.001),440/max(high[1]-low[1],.001))
    for frame in frames:
        pixels=np.full((H,W,3),(245,247,249),dtype=np.uint8);depth=np.full((H,W),-np.inf)
        for poly,color in frame.pop('surfaces'):
            v=poly.copy();v[:,0]=60+(poly[:,0]-low[0])*scale;v[:,1]=85+(poly[:,1]-low[1])*scale
            for i in range(1,len(v)-1):triangle(pixels,depth,[v[0],v[i],v[i+1]],color)
        im=Image.fromarray(pixels);draw=ImageDraw.Draw(im)
        draw.rectangle((0,0,W,67),fill=(245,247,249));draw.rectangle((0,H-40,W,H),fill=(245,247,249))
        draw.text((20,18),f"Saved USD diagnostic surface projection - {frame['elapsed_s']} s",fill=(20,30,45))
        draw.text((20,40),'Depth-tested, schematic shading. Texture mapping, scene lighting and physical behavior are not rendered.',fill=(60,70,80))
        draw.text((20,H-25),f"{len(frame['covered_geometry'])} geometry prims processed; {len(frame['skipped_geometry'])} skipped. Occluded parts may not be visible.",fill=(20,30,45))
        target=out/f"t{frame['elapsed_s']}.png";im.save(target);frame.update(image=target.name,sha256=sha(target))
    result=dict(candidate=artifact.identity,views=frames,renderer_sha256=sha(Path(__file__)),geometry_helper_sha256=sha(Path(__file__).with_name('diagnostic_views.py')),
                limitation='Orthographic diagnostic surfaces with a depth buffer and schematic face shading. No textures, actual lighting, material transparency or physics. Convex-face fan triangulation and cylinder/sphere tessellation are approximations. Original painter-sort previews retained separately.')
    save(out/'view-evidence.json',result);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root;control()
    path=root/'depth-views.json';rows=json.loads(path.read_text())['rows'] if path.exists() else []
    primary=json.loads((root/'assessments/results.json').read_text())['rows']
    for row in primary:
        if row['id'] in {r['id'] for r in rows} or not row.get('inventory'):continue
        bundle=root/'production'/row['id']/'delivery';manifest=json.loads((bundle.parent/'delivery-manifest.json').read_text())['files']
        assert all(sha(bundle/f)==h for f,h in manifest.items())
        result=render(bundle,root/'assessments'/row['id']/'views-depth-v2')
        assert all(sha(bundle/f)==h for f,h in manifest.items())
        rows.append(dict(id=row['id'],views=result));save(path,dict(control='Depth ordering control passed',rows=rows))
        print(json.dumps(dict(id=row['id'],geometry=[len(v['covered_geometry']) for v in result['views']])) ,flush=True)

if __name__=='__main__':main()
