"""Six fresh model outputs; no feedback, repair, tools or evaluator access."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from PIL import Image
from jsonschema import Draft202012Validator
from scene_acceptance.model import sha

def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cli',required=True);args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    inputs=args.inputs.resolve();schema=json.loads((inputs/'producer-schema.json').read_text());rows=[]
    freeze={str(p.relative_to(inputs)):sha(p) for p in inputs.rglob('*') if p.is_file()}
    save(args.out/'input-freeze.json',freeze)
    for rep in range(1,4):
        for arm in ('simple','detailed'):
            case=args.out/f'{arm}-{rep:02d}';case.mkdir();prompt=(inputs/f'{arm}-prompt.txt').read_text()
            (case/'prompt.txt').write_text(prompt);shutil.copyfile(inputs/'producer-schema.json',case/'schema.json')
            images=[inputs/'cell/briefs/warning-a.png'] if arm=='detailed' else []
            argv=[args.cli,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--sandbox','read-only',
                  '--model','gpt-6-astra','-c','model_reasoning_effort="high"','-c','features.shell_tool=false',
                  '-c','features.apps=false','-c','features.plugins=false','-c','features.multi_agent=false','--json',
                  '--output-schema',str(case/'schema.json'),'-o',str(case/'response.json')]
            for image in images:argv+=['-i',str(image)]
            argv+=['-'];started=time.monotonic();error=None;usage=None;code=None;delivery=None
            save(case/'request.json',dict(argv=argv,model_requested='gpt-6-astra',effort='high',prompt_sha256=sha(case/'prompt.txt'),
                 images={str(x):sha(x) for x in images},created_at_utc=datetime.now(timezone.utc).isoformat(),
                 independence='Fresh ephemeral context, no prior output or evaluator feedback; same model family and task'))
            print('START '+case.name,flush=True)
            try:
                with tempfile.TemporaryDirectory(prefix='brief-producer-') as cwd,(case/'prompt.txt').open('rb') as stdin,(case/'native-events.jsonl').open('wb') as stdout,(case/'stderr.log').open('wb') as stderr:
                    proc=subprocess.Popen(argv,stdin=stdin,stdout=stdout,stderr=stderr,cwd=cwd,start_new_session=True)
                    while proc.poll() is None:
                        too_big=any(p.exists() and p.stat().st_size>8388608 for p in (case/'native-events.jsonl',case/'stderr.log',case/'response.json'))
                        if time.monotonic()-started>900 or too_big:
                            os.killpg(proc.pid,signal.SIGKILL);proc.wait();raise RuntimeError('Output budget exceeded' if too_big else 'Trial timed out at 900 seconds')
                        time.sleep(.2)
                    code=proc.returncode
                if code: raise RuntimeError(f'CLI failed with exit {code}')
                response=json.loads((case/'response.json').read_text());Draft202012Validator(schema).validate(response)
                if len(response['texture_rows'])!=8 or any(len(x)!=8 or set(x)-set('YK') for x in response['texture_rows']):
                    raise ValueError('Model raster does not satisfy the common output interface')
                delivery=case/'delivery';delivery.mkdir()
                (delivery/'scene.usda').write_text(response['scene_usda'])
                image=Image.new('RGB',(64,64));colors={'Y':(255,255,0),'K':(0,0,0)}
                for y in range(64):
                    for x in range(64):image.putpixel((x,y),colors[response['texture_rows'][y//8][x//8]])
                image.save(delivery/'warning.png')
                (case/'producer-notes.txt').write_text(response['notes'])
                shutil.copytree(inputs/'cell/briefs',delivery/'briefs')
                save(case/'delivery-manifest.json',{'files':{str(p.relative_to(delivery)):sha(p) for p in delivery.rglob('*') if p.is_file()},
                                                    'adapter':'USD text verbatim; palette raster expanded to PNG; no USD or requirement repairs'})
            except Exception as exc:error=type(exc).__name__+': '+str(exc)
            for line in (case/'native-events.jsonl').read_text().splitlines():
                try:
                    event=json.loads(line)
                    if event.get('type')=='turn.completed':usage=event.get('usage')
                except (ValueError,TypeError):pass
            row=dict(id=case.name,arm=arm,repetition=rep,status='DELIVERED' if delivery else 'NO_DELIVERY',error=error,
                     elapsed_seconds=round(time.monotonic()-started,3),exit_code=code,usage=usage,model_requested='gpt-6-astra',resolved_model=None)
            save(case/'metrics.json',row);rows.append(row);save(args.out/'runs.json',rows);print(json.dumps(row),flush=True)
    assert all(sha(inputs/p)==h for p,h in freeze.items())
    save(args.out/'input-integrity.json',{'unchanged':True,'files':freeze})

if __name__=='__main__': main()
