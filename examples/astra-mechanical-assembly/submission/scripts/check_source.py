import bpy,json,math
from pathlib import Path
root=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(root/'output/crank_slider.blend'))
s=bpy.context.scene
assert s.render.fps==60 and s.frame_start==0 and s.frame_end==240 and s.unit_settings.scale_length==1
max_r=max_l=0
for f in range(241):
 s.frame_set(f)
 c,p,q=[bpy.data.objects[n].matrix_world.translation for n in ('Crank_Center','Crank_Pin','Slider_Pin')]
 max_r=max(max_r,abs((p-c).length-.035));max_l=max(max_l,abs((q-p).length-.110))
assert max(max_r,max_l)<1e-7
assert s.camera and s.render.engine=='CYCLES'
report={'status':'PASS','blender':bpy.app.version_string,'source_reopened':True,'frames_checked':241,'max_radius_error_m':max_r,'max_rod_error_m':max_l,'render_exposure':s.view_settings.exposure,'camera':s.camera.name,'objects':len(s.objects),'mesh_objects':sum(o.type=='MESH' for o in s.objects)}
(root/'logs/source-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
