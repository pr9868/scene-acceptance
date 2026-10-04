"""Prepare sample briefs and reference diagrams before evaluating/generating scenes."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
from PIL import Image
from scene_acceptance.model import sha

ROOT=Path(__file__).resolve().parents[2]
SOURCE={'provided_by':'preset','reference':'Assistant-authored sample user-style brief; not an independently supplied human specification'}

def save(p,x): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')

def item(id,statement,checks,area,review=False):
    return dict(id=id,layer='explicit',statement=statement,basis='Explicit sample brief requirement; mapping authored before new generation',
                required=True,check_ids=checks,review_required=review,decision_id=None,inference_authorization=None,
                specification_source=SOURCE,areas=[area],coverage_declaration={'extent':'partial' if review else 'full',
                  'reason':'Separate qualitative or continuous-time evidence remains necessary' if review else 'Direct comparison of this narrowly stated requirement'})

def check(id,name,parameters,pack='brief.measurements'):
    return dict(id=id,pack=pack,check=name,required=True,parameters=parameters,specification_source=SOURCE)

def manifest(id,title,text,checks,requirements,images=()):
    return dict(schema_version='1.0',id=id,title=title,intended_use=title,
                provenance='Synthetic sample brief, authored by the assistant at the owner’s request. It demonstrates a user-provided brief format; it is not historical Astra input or human approval.',
                files=[dict(path=text,role='text',caption='Text instructions')]+[dict(path=p,role='reference_image',caption=c) for p,c in images],
                mapping_review={'status':'reviewed','reviewer':'Study coordinator (assistant)','reason':'Mapping prepared with the study; no independent human review claimed'},
                checks=checks,requirements=requirements)

def quadrants(path, colors,size):
    # New exact reference diagram; no source image is edited.
    im=Image.new('RGB',(size,size))
    for y in range(size):
        for x in range(size): im.putpixel((x,y),colors[(y>=size//2)*2+(x>=size//2)])
    path.parent.mkdir(parents=True,exist_ok=True);im.save(path)

def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    # Retained producer fixture, already used by earlier consolidation; copied byte-for-byte.
    panel=out/'panel';shutil.copytree(ROOT/'evaluation/consolidation-v1/fixtures/original-panel-png',panel)
    inputs=panel/'briefs';inputs.mkdir()
    quadrants(inputs/'reference-a.png',[(255,0,0),(0,255,0),(0,0,255),(255,255,255)],256)
    quadrants(inputs/'reference-b.png',[(0,255,0),(255,0,0),(255,255,255),(0,0,255)],256)
    dim=check('spec.panel-size','bounds',dict(path='/World/Panel',time_code=0,size_m=[.24,.16,0],tolerance_m=.001))
    size=item('panel-size','Panel world size 240 × 160 mm; thickness zero; tolerance 1 mm',['spec.panel-size'],'geometry')
    for mode in ('size','image-a','image-b','conflict'):
        text='Make a flat 240 × 160 mm panel. Dimensional tolerance: 1 mm. Its X/Y position is unrestricted.\n'
        checks=[deepcopy(dim)];requirements=[deepcopy(size)];images=[]
        if mode!='size':
            ref='b' if mode=='image-b' else 'a'
            images=[(f'briefs/reference-{ref}.png','Exact texture reference, stored top-to-bottom image orientation')]
            text+='Use the attached reference as the exact 256 × 256 RGB texture. Compare source pixels, not a screenshot.\n'
            checks.append(check('spec.panel-image','image_pixels',dict(asset_attribute='/World/Looks/Label/Texture.inputs:file',reference_image=images[0][0],max_channel_error=0)))
            requirements.append(item('panel-image','Delivered texture pixels equal the supplied reference',['spec.panel-image'],'textures'))
        if mode=='conflict':
            text+='Conflicting instruction: make the panel 300 mm wide. The first sentence says 240 mm. No precedence is given; seek clarification.\n'
            requirements.append(item('width-conflict','Resolve the contradictory 240 mm and 300 mm width instructions',[],'geometry',True))
        (inputs/f'{mode}.md').write_text(text)
        save(inputs/f'{mode}.json',manifest('panel-'+mode,'Same saved panel / '+mode,f'briefs/{mode}.md',checks,requirements,images))
    cell=out/'cell';(cell/'briefs').mkdir(parents=True)
    quadrants(cell/'briefs/warning-a.png',[(255,255,0),(0,0,0),(0,0,0),(255,255,0)],64)
    quadrants(cell/'briefs/warning-b.png',[(0,0,0),(255,255,0),(255,255,0),(0,0,0)],64)
    base='''Build a detailed inspection-conveyor illustration with deck, rollers, support legs, guards, a control cabinet, signal tower, sensor, animated carton and textured warning panel. Use a credible mechanical arrangement with readable components. This is an illustration, not a calibrated or safety-certified machine.

Use Z-up metre coordinates. Deck /World/Conveyor is a Cube or Mesh, world size (3.0, 0.8, 0.1) m, centre (0, 0, 0.8) m. Exactly 12 Cylinder prims must be direct children of /World/Rollers. /World/ControlCabinet is a Cube or Mesh on the positive-Y side: its nearest Y edge is at least 0.9 m from the deck's positive-Y edge. /World/Carton is a Cube or Mesh of size (0.3, 0.2, 0.2) m. All size/position/gap tolerances are 1 mm.

Author a 4-second stage at 24 time codes per second, starting at time code 0 and ending at 96. Carton origin moves uniformly from (-1.2, 0, 1.05) m at 0 seconds through (0,0,1.05) at 2 seconds to (1.2,0,1.05) at 4 seconds. It must follow that path throughout the interval. Diagnostic positions will be compared at 21 equally spaced times with 1 mm tolerance; finite samples do not alone prove the throughout condition. Clock tolerance is 1e-9 s.

Use a yellow/black 2x2 checker texture on the warning panel. Keep materials connected and texture mapping usable. The assembly should be visually readable and mechanically credible; this qualitative requirement needs review beyond saved numeric checks.
'''
    checks=[check('spec.deck','bounds',dict(path='/World/Conveyor',time_code=0,size_m=[3,.8,.1],center_m=[0,0,.8],tolerance_m=.001)),
            check('spec.rollers','children',dict(parent='/World/Rollers',type='Cylinder',count=12)),
            check('spec.aisle','axis_gap',dict(a='/World/Conveyor',b='/World/ControlCabinet',axis='y',time_code=0,minimum_m=.9,tolerance_m=.001)),
            check('spec.carton','bounds',dict(path='/World/Carton',time_code=0,size_m=[.3,.2,.2],tolerance_m=.001)),
            check('spec.clock','clock',dict(duration_s=4,tolerance_s=1e-9,time_codes_per_second=24),pack='motion.timing'),
            check('spec.motion','positions',dict(path='/World/Carton',tolerance_m=.001,samples=[dict(elapsed_s=i/5,world_origin_m=[-1.2+.12*i,0,1.05]) for i in range(21)]),pack='motion.timing')]
    requirements=[item('deck','Deck has specified world size and centre',['spec.deck'],'geometry'),
                  item('rollers','Exactly twelve direct Cylinder rollers',['spec.rollers'],'geometry'),
                  item('aisle','Cabinet-to-deck directed Y gap at least 0.9 m',['spec.aisle'],'geometry'),
                  item('carton','Carton has specified dimensions',['spec.carton'],'geometry'),
                  item('clock','Stage lasts 4 s at 24 time codes/s',['spec.clock'],'motion'),
                  item('sampled-motion','Carton reaches the 21 specified positions',['spec.motion'],'motion'),
                  item('continuous-motion','Carton follows the required linear path throughout the interval',['spec.motion'],'motion',True),
                  item('visual-quality','Assembly is visually readable and mechanically credible',[],'appearance',True),
                  item('panel-appearance','Warning texture is connected and visibly mapped on the panel',[],'appearance',True)]
    for mode in ('text','image','changed'):
        cs=deepcopy(checks);rs=deepcopy(requirements);text=base;images=[]
        if mode!='text':
            ref='b' if mode=='changed' else 'a';images=[(f'briefs/warning-{ref}.png','Exact 64 × 64 warning-texture reference; top row is image top')]
            text+='\nMatch the attached 64 × 64 RGB warning image exactly, including quadrant orientation. The image is normative for the source pixels.\n'
            cs.append(check('spec.warning-image','image_pixels',dict(asset_attribute='/World/Looks/Warning/Texture.inputs:file',reference_image=images[0][0],max_channel_error=0)))
            rs.append(item('warning-image','Delivered warning-image pixels match the supplied reference',['spec.warning-image'],'textures'))
        else:
            rs.append(item('warning-pattern','Yellow/black 2x2 source texture; orientation unspecified',[],'textures',True))
        if mode=='changed':
            text=text.replace('0.9 m','1.4 m');cs[2]['parameters']['minimum_m']=1.4
            rs[2]['statement']=rs[2]['statement'].replace('0.9 m','1.4 m')
            text+='\nThis is a counterfactual different assignment used only for assessment; it was not provided to either creation arm.\n'
        # Mapping audit added these targets after the original seven-check study was frozen.
        # Both values already existed in the unchanged producer/assessment text.
        cs += [check('spec.coordinates','metadata',dict(values={'upAxis':'Z','metersPerUnit':1},tolerance=1e-9)),
               check('spec.time-range','metadata',dict(values={'startTimeCode':0,'endTimeCode':96},tolerance=1e-9))]
        rs += [item('coordinates','Use authored Z-up metre coordinates',['spec.coordinates'],'geometry'),
               item('time-range','Author exact time codes 0 through 96',['spec.time-range'],'motion')]
        next(x for x in rs if x['id']=='visual-quality')['statement']='Required deck, rollers, supports, guards, cabinet, tower, sensor, carton and warning panel are present, visually readable and mechanically credible'
        (cell/f'briefs/{mode}.md').write_text(text)
        save(cell/f'briefs/{mode}.json',manifest('cell-'+mode,'Inspection conveyor / '+mode,f'briefs/{mode}.md',cs,rs,images))
    common='''Return JSON with complete scene_usda, texture_rows, and notes. Author a detailed multi-part USD scene directly, with at least 30 visible geometry prims. Do not use placeholders or claim to have executed code. You have no tools in this trial. A delivery adapter will save scene_usda verbatim as scene.usda and create warning.png from texture_rows. texture_rows must be eight strings of eight characters: Y=RGB(255,255,0), K=RGB(0,0,0). Each cell becomes an 8x8 block, making a 64x64 PNG. Choose the pattern yourself unless the brief specifies it. Use @warning.png@ for the texture asset. No other external assets.

Output conventions common to both arms: name the single deck geometry /World/Conveyor; put roller Cylinder prims directly under /World/Rollers; name the single cabinet geometry /World/ControlCabinet and the single animated carton geometry /World/Carton. Put the warning image asset attribute at /World/Looks/Warning/Texture.inputs:file and the panel at /World/WarningPanel. Other names and construction choices are yours. Use ordinary local USD with no payloads, variants or instanceable prims. Deliver material bindings, any required UVs, metadata and animation yourself. The adapter will not repair your authoring.\n\n'''
    (out/'simple-prompt.txt').write_text(common+'Create a detailed industrial inspection conveyor with rollers, legs, guards, a control cabinet, signal tower, sensor, warning panel and a carton moving along it. Choose reasonable dimensions, counts, spacing, materials and timing.\n')
    (out/'detailed-prompt.txt').write_text(common+(cell/'briefs/image.md').read_text())
    response_schema={'type':'object','properties':{'scene_usda':{'type':'string'},'texture_rows':{'type':'array','items':{'type':'string'}},'notes':{'type':'string'}},'required':['scene_usda','texture_rows','notes'],'additionalProperties':False}
    save(out/'producer-schema.json',response_schema)
    save(out/'prepared-inputs.json',{'files':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},
                                  'fixture_original':str(ROOT/'evaluation/consolidation-v1/fixtures/original-panel-png')})
    return out

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();prepare(args.out)
