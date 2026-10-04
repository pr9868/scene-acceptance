"""Post-review source measurement of one nominated visual concern; not a new primary check."""
import argparse
import json
import math
from pathlib import Path
from pxr import Gf, Usd, UsdGeom
from scene_acceptance.model import sha


def analyze(scene, out):
    before=sha(scene);stage=Usd.Stage.Open(str(scene));mesh=UsdGeom.Mesh(stage.GetPrimAtPath('/World/Cables/TravelCable'))
    counts=list(mesh.GetFaceVertexCountsAttr().Get());indices=list(mesh.GetFaceVertexIndicesAttr().Get());faces=[];cursor=0
    for n in counts:faces.append(indices[cursor:cursor+n]);cursor+=n
    neighbors={i:[] for i in range(len(faces))}
    for i,f in enumerate(faces):
        edges={frozenset((f[k],f[(k+1)%len(f)])) for k in range(len(f))}
        for j,g in enumerate(faces[:i]):
            other={frozenset((g[k],g[(k+1)%len(g)])) for k in range(len(g))}
            if edges&other:neighbors[i].append(j);neighbors[j].append(i)
    seen=set();components=[]
    for i in neighbors:
        if i in seen:continue
        stack=[i];component=[]
        while stack:
            k=stack.pop()
            if k in seen:continue
            seen.add(k);component.append(k);stack.extend(neighbors[k])
        components.append(component)
    times=sorted(set([0,48,96]+mesh.GetPointsAttr().GetTimeSamples()));samples=[]
    for t in times:
        tc=Usd.TimeCode(t);cache=UsdGeom.XformCache(tc);m=cache.GetLocalToWorldTransform(mesh.GetPrim());points=mesh.GetPointsAttr().Get(tc)
        endpoints=[m.Transform((Gf.Vec3d(points[a])+Gf.Vec3d(points[b]))/2) for a,b in ((0,1),(8,9))]
        for end,path in zip(endpoints,('/World/Carriage/CableLead','/World/Cables/UprightConduit')):
            cylinder=UsdGeom.Cylinder(stage.GetPrimAtPath(path));assert cylinder.GetAxisAttr().Get()=='Z'
            local=cache.GetLocalToWorldTransform(cylinder.GetPrim()).GetInverse().Transform(end)
            radius=cylinder.GetRadiusAttr().Get(tc);height=cylinder.GetHeightAttr().Get(tc)
            radial_excess=max(0,math.hypot(local[0],local[1])-radius);axial_excess=max(0,abs(local[2])-height/2)
            samples.append(dict(time_code=t,elapsed_seconds=(t-stage.GetStartTimeCode())/stage.GetTimeCodesPerSecond(),
                                cylinder=path,edge_midpoint_world_m=list(end),edge_midpoint_local_m=list(local),
                                radius_m=radius,height_m=height,distance_to_closed_cylinder_m=math.hypot(radial_excess,axial_excess)))
    assert sha(scene)==before
    result=dict(kind='Post-review corroboration, outside frozen primary outcome',source=str(scene),source_sha256=before,source_unchanged=True,
                method='Mesh faces connected through shared authored edges; cable terminal edge midpoints transformed into nominated cylinder local coordinates.',
                face_counts=counts,face_indices=indices,connected_face_components=components,samples=samples,
                max_sampled_endpoint_distance_m=max(s['distance_to_closed_cylinder_m'] for s in samples),
                limitation='Connections and endpoint identities are selected after the concern. This checks authored topology and endpoint positions at seven times only, not full continuous motion, cable mechanics or all geometric intersections. The saved schematic view can show a raster gap despite connected source geometry.')
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('samples','face_indices')}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scene',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();analyze(a.scene,a.out)
