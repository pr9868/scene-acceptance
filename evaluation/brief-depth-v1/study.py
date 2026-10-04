"""Frozen synthetic tasks and explicitly mapped brief levels."""
from copy import deepcopy
import json
import math
from pathlib import Path
import random
from PIL import Image

LEVELS=['simple','light','medium','detailed']
PALETTE={'R':(210,40,40),'G':(20,150,80),'B':(40,90,210),'W':(240,240,240)}
SOURCE={'provided_by':'preset','reference':'Assistant-authored brief-depth study; original prompt is retained; no independent human approval claimed'}
TASKS=[
 dict(id='gantry',title='Gantry inspection cell',description='a gantry inspection cell with a structural base, two uprights, bridge, guide rails, a moving carriage with inspection head, workholding locators, guards, cabinet, cable details and a textured status panel',
      size=[3.2,1.8,.18],center=[0,0,.09],repeated='/World/Locators',count=6,part='workholding locators',mover='/World/Carriage',mover_size=[.4,.3,.18],gap=.8,duration=4,
      knots=[(0,[-.8,0,1.1]),(1,[-.8,0,1.6]),(3,[.8,0,1.6]),(4,[.8,0,1.1])],
      trajectory='Lift vertically during the first second, translate across at constant height from 1 to 3 seconds, and lower vertically during the last second. Use linear interpolation within each segment.',
      pixels=['RRRRWWWW']*4+['BBBBGGGG']*4),
 dict(id='rotary',title='Rotary indexing bench',description='a rotary indexing bench with a structural base, central turntable, fixture pins, drive housing, rotating workpiece, sensor stands, guards, cabinet, fasteners and a textured status panel',
      size=[2.6,1.6,.18],center=[0,0,.55],repeated='/World/Fixtures',count=8,part='fixture pins',mover='/World/Workpiece',mover_size=[.24,.18,.16],gap=.7,duration=4,
      trajectory='The workpiece origin follows the positive-Y semicircle x=0.65*cos(pi*t/4), y=0.65*sin(pi*t/4), z=1.05, for elapsed seconds t from 0 through 4. Keep its world axis-aligned size at t=0 as specified; orientation throughout is not a measured target.',
      pixels=['BBBBRRRR']*4+['WWWWGGGG']*4),
 dict(id='skid',title='Pump and valve skid',description='a pump and valve skid illustration with a structural base, filter cylinders, pump and motor housings, piping elbows, support clamps, a moving valve actuator, gauges, service cabinet, bolts and a textured status panel',
      size=[4,2,.18],center=[0,0,.09],repeated='/World/Filters',count=4,part='filter cylinders',mover='/World/Actuator',mover_size=[.16,.16,.22],gap=.85,duration=6,
      knots=[(0,[1.2,0,.95]),(1.5,[1.2,0,1.15]),(3,[1.2,0,1.15]),(4.5,[1.2,0,1.02]),(6,[1.2,0,1.15])],
      trajectory='The actuator rises to z=1.15 by 1.5 seconds, holds there until 3 seconds, lowers to z=1.02 by 4.5 seconds, then rises to z=1.15 by 6 seconds. x=1.2 and y=0 throughout. Interpolate linearly between those timed positions.',
      pixels=['WWRRWWWW','WWRRWWWW','WWRRWWWW','GGGGGGGG','GGGGGGGG','WWRRWWWW','WWRRWWBB','WWRRWWBB']),
]

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')

def position(task,t):
    if task['id']=='rotary':return [round(.65*math.cos(math.pi*t/4),6),round(.65*math.sin(math.pi*t/4),6),1.05]
    for (a,x),(b,y) in zip(task['knots'],task['knots'][1:]):
        if a<=t<=b:return [round(u+(v-u)*(t-a)/(b-a),6) for u,v in zip(x,y)]
    raise ValueError(t)

def samples(task):
    return [dict(elapsed_s=round(i*task['duration']/20,6),world_origin_m=position(task,i*task['duration']/20)) for i in range(21)]

def raster(path,rows):
    image=Image.new('RGB',(64,64))
    image.putdata([PALETTE[rows[y//8][x//8]] for y in range(64) for x in range(64)])
    path.parent.mkdir(parents=True,exist_ok=True);image.save(path)

def check(id,name,parameters,pack='brief.measurements'):
    return dict(id='spec.'+id,pack=pack,check=name,required=True,parameters=parameters,specification_source=SOURCE)

def requirement(id,statement,checks,area,review=False):
    return dict(id=id,layer='explicit',statement=statement,basis='Frozen study prompt and explicit sample check map',required=True,
                check_ids=checks,review_required=review,decision_id=None,inference_authorization=None,
                specification_source=SOURCE,areas=[area],coverage_declaration={'extent':'partial' if review else 'full',
                'reason':'Separate qualitative/continuous evidence remains necessary' if review else 'Direct comparison of this narrowly stated requirement'})

def checks(task):
    return [
      check('coordinates','metadata',dict(values={'upAxis':'Z','metersPerUnit':1},tolerance=1e-9)),
      check('base','bounds',dict(path='/World/Base',time_code=0,size_m=task['size'],center_m=task['center'],tolerance_m=.001)),
      check('count','children',dict(parent=task['repeated'],type='Cylinder',count=task['count'])),
      check('gap','axis_gap',dict(a='/World/Base',b='/World/Cabinet',axis='y',time_code=0,minimum_m=task['gap'],tolerance_m=.001)),
      check('mover-size','bounds',dict(path=task['mover'],time_code=0,size_m=task['mover_size'],tolerance_m=.001)),
      check('clock','clock',dict(duration_s=task['duration'],time_codes_per_second=24,tolerance_s=1e-9),'motion.timing'),
      check('time-range','metadata',dict(values={'startTimeCode':0,'endTimeCode':task['duration']*24},tolerance=1e-9)),
      check('endpoints','positions',dict(path=task['mover'],tolerance_m=.001,samples=[samples(task)[0],samples(task)[-1]]),'motion.timing'),
      check('trajectory','positions',dict(path=task['mover'],tolerance_m=.001,samples=samples(task)),'motion.timing'),
      check('image','image_pixels',dict(asset_attribute='/World/Looks/Label/Texture.inputs:file',reference_image='briefs/reference.png',max_channel_error=0)),
    ]

def common(task):
    return f'''Create a complete saved USD illustration directly. Return JSON containing scene_usda (complete USDA text), texture_rows (eight strings of eight characters each) and notes. You have no tools; do not claim to have executed validation. Aim for 40–70 visible geometry prims with meaningful components and detail, at least 40. This is an illustration, not a calibrated machine. Other geometry and construction choices are yours.

Shared output conventions for all prompt levels: author Z-up metre coordinates; use one /World default root with ordinary Cube, Cylinder, Sphere and Mesh geometry. No variants, instances, payloads, value clips, inherits or external USD layers. /World/Base, /World/Cabinet and {task['mover']} must each be a single Cube or Mesh (not only a group). Place the repeated {task['part']} as direct Cylinder children under {task['repeated']}; choose their count unless specified below. Use /World/Panel for the textured panel and /World/Looks/Label/Texture.inputs:file for its UsdUVTexture asset attribute. The only external file is @textures/label.png@. Deliver your material bindings, UVs, metadata and motion yourself.

The delivery adapter saves your USDA verbatim and expands each texture_rows cell into an 8×8 block, making a 64×64 RGB PNG at textures/label.png. Palette: R=(210,40,40), G=(20,150,80), B=(40,90,210), W=(240,240,240). Choose a pattern unless a reference is supplied. No other assets or repair code are provided. All explicitly specified lengths and positions have 1 mm tolerance; specified clock duration tolerance is 1e-9 s. A specified image comparison uses exact decoded source pixels, not a screenshot.

'''

def prompt(task,level):
    text=common(task)+f"Build {task['description']}. Make the arrangement visually readable and mechanically credible. Include motion of {task['mover']}.\n"
    if level=='simple':return text+'Choose reasonable sizes, repeated-part count, service spacing, timing and path.\n'
    text+=f"\nThe /World/Base world size is {task['size']} m and centre is {task['center']} m. Exactly {task['count']} direct Cylinder children belong under {task['repeated']}.\n"
    if level=='light':return text+'Choose reasonable cabinet spacing, moving-part size, timing and path.\n'
    text+=f"\nCabinet must lie on positive Y: its nearest Y edge is at least {task['gap']} m beyond the base's positive-Y edge. This is an axis gap, not an access/safety guarantee. {task['mover']} has world size {task['mover_size']} m at stage start. Author duration {task['duration']} seconds at 24 time codes per second, with time codes 0 through {task['duration']*24}. Its world origin starts at {position(task,0)} m and ends at {position(task,task['duration'])} m.\n"
    if level=='medium':return text+'The path between these two endpoints and the exact colour pattern are your choices.\n'
    text+='\nDetailed trajectory: '+task['trajectory']+'\nThe following 21 elapsed-second positions are measurable checkpoints (metres, tolerance 1 mm):\n'
    text+='\n'.join(f"{s['elapsed_s']:g} s: {s['world_origin_m']}" for s in samples(task))
    text+='\nFollow the stated path throughout the interval; the listed samples alone cannot prove the continuous requirement.\nMatch the attached 64×64 RGB reference image exactly in stored top-to-bottom row order. Keep the panel texture connected and visibly mapped. The source-pixel requirement is separate from visible appearance.\n'
    return text

def manifest(task,level):
    selected=checks(task)[:{'simple':1,'light':3,'medium':8,'detailed':10}[level]]
    statements={
      'coordinates':'Authored Z-up metre coordinates', 'base':'Specified base world size and centre',
      'count':f"Exactly {task['count']} direct Cylinder {task['part']}", 'gap':f"Directed Y cabinet gap at least {task['gap']} m",
      'mover-size':'Specified moving-part world size at time code 0', 'clock':'Specified authored duration and 24 time codes per second',
      'time-range':f"Authored time codes 0 through {task['duration']*24}", 'endpoints':'Specified moving-part start and end world origins',
      'trajectory':'Specified moving-part world origins at all 21 listed checkpoints', 'image':'Decoded RGB source pixels equal the supplied reference',
    }
    req=[]
    for c in selected:
        key=c['id'][5:];area='textures' if key=='image' else 'motion' if key in ('clock','time-range','endpoints','trajectory') else 'geometry'
        req.append(requirement(key,statements[key],[c['id']],area))
    req += [requirement('assembly-quality','Required components, at least 40 visible geometry prims, credible arrangement and readable detail',[],'appearance',True),
            requirement('panel-appearance','Materials/UVs are usable and the panel texture is visibly mapped',[],'appearance',True)]
    if level=='detailed':req.append(requirement('continuous-motion','Moving part follows the stated path throughout the interval',['spec.trajectory'],'motion',True))
    return dict(schema_version='1.0',id=task['id']+'-'+level,title=task['title']+' / '+level,
                intended_use='Illustration checked within explicitly supplied study targets',
                provenance='Assistant-authored synthetic brief at the owner’s request; not an independently supplied human specification or approval.',
                files=[dict(path=f'briefs/{level}.md',role='text',caption=f'Exact {level} creation prompt, including common output conventions')]+
                      ([dict(path='briefs/reference.png',role='reference_image',caption='Exact supplied source-pixel reference')] if level=='detailed' else []),
                mapping_review={'status':'reviewed','reviewer':'Study coordinator (assistant)','reason':'Map and controls checked before generation; no independent human review claimed'},
                checks=selected,requirements=req)

def prepare(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    save(out/'tasks.json',TASKS)
    schema={'type':'object','properties':{'scene_usda':{'type':'string'},'texture_rows':{'type':'array','items':{'type':'string'}},'notes':{'type':'string'}},'required':['scene_usda','texture_rows','notes'],'additionalProperties':False}
    save(out/'producer-schema.json',schema)
    for task in TASKS:
        folder=out/task['id']/'briefs';folder.mkdir(parents=True)
        raster(folder/'reference.png',task['pixels'])
        for level in LEVELS:
            (folder/f'{level}.md').write_text(prompt(task,level));save(folder/f'{level}.json',manifest(task,level))
    rng=random.Random(20261003);blocks=[(t['id'],r) for t in TASKS for r in (1,2)];rng.shuffle(blocks);order=[]
    for task,rep in blocks:
        levels=LEVELS.copy();rng.shuffle(levels)
        for level in levels:order.append(dict(id=f'{task}-{level}-{rep:02d}',task=task,level=level,repetition=rep))
    save(out/'schedule.json',order)
    return out

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();prepare(a.out)
