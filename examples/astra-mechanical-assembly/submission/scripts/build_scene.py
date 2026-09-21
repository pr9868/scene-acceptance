"""Procedural, metre-scale crank-slider. Run with the supplied bpy Python."""
import bpy, math, json, os, sys
from mathutils import Vector
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
OUT.mkdir(exist_ok=True)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
for datablocks in (bpy.data.materials, bpy.data.curves, bpy.data.meshes):
    for block in list(datablocks):
        if block.users == 0: datablocks.remove(block)
s = bpy.context.scene
s.unit_settings.system = 'METRIC'; s.unit_settings.scale_length = 1
s.render.fps = 60; s.frame_start = 0; s.frame_end = 240
s['description'] = 'Synthetic tabletop crank-slider; visual kinematic demonstration, not engineering validation.'
s['crank_radius_m'] = .035; s['rod_pin_distance_m'] = .110; s['period_seconds'] = 4.0

def mat(name, color, metal=0, rough=.35):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF'); p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Metallic'].default_value=metal; p.inputs['Roughness'].default_value=rough
    return m
blue=mat('Structure | cobalt enamel',(.025,.16,.36),.55,.27)
silver=mat('Linkage | satin steel',(.52,.61,.68),.84,.26)
bright=mat('Hardware | polished alloy',(.72,.8,.85),.92,.19)
orange=mat('Slider | signal orange',(.96,.22,.032),.34,.28)
dark=mat('Hardware | graphite',(.025,.038,.05),.58,.3)
rubber=mat('Feet | dark rubber',(.014,.02,.027),0,.8)
ink=mat('Lettering | ivory',(.8,.89,.92),.15,.45)
floor_mat=mat('Studio | slate',(.035,.053,.076),.05,.7)

def finish(o,name,material,parent=None,bevel=0):
    o.name=name; o.data.materials.append(material)
    if parent: o.parent=parent
    if bevel:
        mod=o.modifiers.new('Machined edge radius','BEVEL'); mod.width=bevel; mod.segments=3
        mod=o.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
    return o
def box(name,loc,size,material,parent=None,bevel=.001):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=bpy.context.object
    o.dimensions=size; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return finish(o,name,material,parent,bevel)
def cyl(name,loc,r,depth,material,parent=None,axis='Z'):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=r,depth=depth,location=loc)
    o=bpy.context.object
    if axis=='X': o.rotation_euler.y=math.pi/2
    if axis=='Y': o.rotation_euler.x=math.pi/2
    for p in o.data.polygons: p.use_smooth=len(p.vertices)==4
    return finish(o,name,material,parent,.00035)
def empty(name):
    o=bpy.data.objects.new(name,None); s.collection.objects.link(o); o.empty_display_size=.012
    return o
def capsule(name,length,width,depth,z,material,parent):
    r=width/2; outline=[]
    for center,start in ((length,-math.pi/2),(0,math.pi/2)):
        for i in range(25):
            a=start+math.pi*i/24; outline.append((center+r*math.cos(a),r*math.sin(a)))
    n=len(outline); verts=[(x,y,z+dz) for dz in (-depth/2,depth/2) for x,y in outline]
    faces=[tuple(reversed(range(n))),tuple(range(n,n*2))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    mesh=bpy.data.meshes.new(name); mesh.from_pydata(verts,[],faces); mesh.update()
    o=bpy.data.objects.new(name,mesh); s.collection.objects.link(o)
    return finish(o,name,material,parent,.0006)
def bolt(name,x,y,z,parent=None,r=.003):
    cyl(name+' washer',(x,y,z),r*1.4,.001,bright,parent)
    o=cyl(name+' socket head',(x,y,z+.0017),r,.0025,dark,parent)
    bpy.ops.mesh.primitive_cylinder_add(vertices=6,radius=r*.48,depth=.00015,location=(x,y,z+.003))
    finish(bpy.context.object,name+' hex recess',rubber,parent)
def label(name,body,loc,size,material,parent=None):
    curve=bpy.data.curves.new(name,'FONT'); curve.body=body; curve.size=size; curve.extrude=.000025
    curve.align_x='CENTER'; o=bpy.data.objects.new(name,curve); s.collection.objects.link(o); o.location=loc
    o.data.materials.append(material)
    if parent:o.parent=parent
    bpy.context.view_layer.objects.active=o; o.select_set(True)
    bpy.ops.object.convert(target='MESH'); o.select_set(False)
    return o

assembly=empty('CRANK_SLIDER_ASSEMBLY')
box('Base | cobalt plinth',(0,0,.019),(.315,.17,.022),blue,assembly,.008)
box('Deck | brushed insert',(0,0,.031),(.292,.148,.003),silver,assembly,.005)
for x in (-.129,.129):
    for y in (-.06,.06):
        cyl('Rubber isolator', (x,y,.006),.012,.012,rubber,assembly)
        bolt('Deck fastener',x,y,.034,assembly)
# Stationary spindle bearing on the left.
cx=-.09
box('Spindle pedestal',(cx,0,.045),(.046,.061,.026),blue,assembly,.004)
cyl('Spindle bearing housing',(cx,0,.062),.02,.015,blue,assembly)
cyl('Spindle bearing race',(cx,0,.070),.0135,.003,bright,assembly)
cyl('Spindle bearing seal',(cx,0,.072),.0105,.002,dark,assembly)
cyl('Main vertical shaft',(cx,0,.079),.006,.024,bright,assembly)

# Two straight rails, supported at both ends.
for x in (-.046,.107):
    box('Guide end support',(x,0,.049),(.015,.082,.034),blue,assembly,.003)
    for y in (-.027,.027):
        cyl('Guide support collar',(x,y,.072),.008,.016,dark,assembly,'X')
        bolt('Support mount',x,y*1.18,.067,assembly,r=.0023)
for y in (-.027,.027):
    cyl('Linear guide rail',( .0305,y,.073),.0045,.172,bright,assembly,'X')
box('Travel scale',(.031,-.047,.034),(.161,.012,.0015),dark,assembly,.001)
for i in range(15):
    x=-.039+i*.01
    box('Scale tick %02d'%i,(x,-.047,.035),(.0006,.007 if i%5==0 else .0035,.0003),ink,assembly,.0001)
label('Deck title','KINETIC / 01',(-.08,-.064,.033),.009,blue,assembly)
label('Deck subtitle','CRANK - SLIDER',(.06,-.064,.033),.0048,dark,assembly)
label('Guide label','LINEAR GUIDE',(.03,.052,.033),.0045,dark,assembly)

crank=empty('Crank_Rotation'); crank.parent=assembly; crank.location=(cx,0,0)
crank['radius_m']=.035; crank['axis']='Z'; crank['center_m']=[cx,0,.102]
cyl('Crank balance disk',(0,0,.078),.029,.006,dark,crank)
for a in range(0,360,60):
    angle=math.radians(a)
    cyl('Disk silver pocket',(.021*math.cos(angle),.021*math.sin(angle),.0812),.0033,.0006,silver,crank)
capsule('Crank arm',.035,.018,.007,.087,blue,crank)
bolt('Spindle cap',0,0,.092,crank,r=.0045)
cyl('Crank pin shaft',(.035,0,.095),.0045,.022,bright,crank)
cyl('Crank pin lower spacer',(.035,0,.094),.0065,.006,dark,crank)

slider=empty('Slider_Translation'); slider.parent=assembly
box('Orange slider carriage',(0,0,.076),(.036,.071,.025),orange,slider,.004)
for y in (-.027,.027):
    cyl('Slider bushing barrel',(0,y,.073),.0075,.039,dark,slider,'X')
    for x in (-.020,.020):cyl('Slider bushing end ring',(x,y,.073),.0077,.0015,bright,slider,'X')
box('Slider pin saddle',(0,0,.092),(.024,.023,.009),dark,slider,.002)
cyl('Slider pin shaft',(0,0,.099),.0045,.017,bright,slider)
for x in (-.012,.012):
    for y in (-.017,.017):bolt('Carriage screw',x,y,.089,slider,r=.0018)
label('Carriage mark','01',(0,-.022,.089),.006,ink,slider)

rod=empty('Connecting_Rod_Pose'); rod.parent=assembly; rod['pin_to_pin_m']=.110
capsule('Connecting rod',.110,.014,.006,0,silver,rod)
box('Rod recessed spine',(.055,0,.0032),(.078,.004,.0007),dark,rod,.0018)
for x in (0,.110):
    cyl('Rod bearing bronze seat',(x,0,.0035),.0068,.0015,orange,rod)
    bolt('Rod pivot',x,0,.0045,rod,r=.0038)

# Empty prims are precise reference datums in the saved scene, not hardware surfaces.
center=empty('Crank_Center'); center.parent=assembly; center.location=(cx,0,.102)
cp=empty('Crank_Pin'); cp.parent=crank; cp.location=(.035,0,.102)
sp=empty('Slider_Pin'); sp.parent=slider; sp.location=(0,0,.102)
for o in (center,cp,sp):o['role']='Kinematic reference point, metres'
for frame in range(241):
    theta=2*math.pi*frame/240
    px=cx+.035*math.cos(theta); py=.035*math.sin(theta)
    sx=px+math.sqrt(.110**2-py**2)
    crank.rotation_euler.z=theta; crank.keyframe_insert(data_path='rotation_euler',frame=frame)
    slider.location=(sx,0,0); slider.keyframe_insert(data_path='location',frame=frame)
    rod.location=(px,py,.102); rod.rotation_euler.z=math.atan2(-py,sx-px)
    rod.keyframe_insert(data_path='location',frame=frame); rod.keyframe_insert(data_path='rotation_euler',frame=frame)
for action in bpy.data.actions:
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fcurve in bag.fcurves:
                    for k in fcurve.keyframe_points:k.interpolation='LINEAR'

# Render studio remains in the editable source; exports contain only the assembly.
box('Studio ground',(0,0,-.004),(200,200,.007),floor_mat,bevel=0)
world=bpy.data.worlds.new('Slate studio environment'); s.world=world; world.use_nodes=True
world.node_tree.nodes['Background'].inputs[0].default_value=(.18,.23,.32,1)
world.node_tree.nodes['Background'].inputs[1].default_value=.4
def area(name,loc,power,size,color):
    d=bpy.data.lights.new(name,'AREA'); d.energy=power; d.shape='DISK'; d.size=size; d.color=color
    o=bpy.data.objects.new(name,d); s.collection.objects.link(o); o.location=loc
    o.rotation_euler=(Vector((0,0,.04))-o.location).to_track_quat('-Z','Y').to_euler()
area('Key softbox',(-.18,-.22,.42),12,.32,(.8,.9,1))
area('Warm rim',(.18,.19,.27),9,.24,(1,.76,.5))
area('Front fill',(.12,-.1,.19),3,.18,(.65,.8,1))
d=bpy.data.cameras.new('Overview camera'); cam=bpy.data.objects.new('Overview camera',d); s.collection.objects.link(cam)
cam.location=(.29,-.39,.38); target=Vector((-.008,0,.045))
cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler(); d.type='ORTHO'; d.ortho_scale=.43; s.camera=cam
s.render.engine='CYCLES'; s.cycles.samples=64; s.cycles.use_denoising=True
s.render.resolution_x=1800; s.render.resolution_y=1400; s.render.resolution_percentage=100
s.view_settings.view_transform='AgX'; s.view_settings.exposure=-1.25; s.render.image_settings.file_format='PNG'
s.frame_set(35)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'crank_slider.blend'))

bpy.ops.object.select_all(action='DESELECT')
def select_tree(o):
    o.select_set(True)
    for child in o.children:select_tree(child)
select_tree(assembly)
usd_props={p.identifier for p in bpy.ops.wm.usd_export.get_rna_type().properties}
gltf_props={p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
(ROOT/'logs'/'exporter-properties.json').write_text(json.dumps({'usd':sorted(usd_props),'gltf':sorted(gltf_props)},indent=2))
usd_args=dict(filepath=str(OUT/'crank_slider.usdc'),selected_objects_only=True,export_animation=True,export_materials=True,export_textures=False)
bpy.ops.wm.usd_export(**{k:v for k,v in usd_args.items() if k in usd_props})
gltf_args=dict(filepath=str(OUT/'crank_slider.glb'),export_format='GLB',use_selection=True,export_animations=True,export_frame_range=True,export_force_sampling=True,export_animation_mode='ACTIVE_ACTIONS',export_apply=True,export_extras=True)
bpy.ops.export_scene.gltf(**{k:v for k,v in gltf_args.items() if k in gltf_props})
s.frame_set(35); s.render.filepath=str(OUT/'overview.png'); bpy.ops.render.render(write_still=True)
(OUT/'build-info.json').write_text(json.dumps({'blender':bpy.app.version_string,'fps':60,'start_frame':0,'end_frame':240,'duration_s':4,'crank_radius_m':.035,'rod_length_m':.110,'overview_frame':35},indent=2))
print('BUILD COMPLETE', flush=True)
