"""Frozen 24-slot model experiment. Reserve every slot; never repair a delivery."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from jsonschema import Draft202012Validator
from scene_acceptance.model import sha
from study import PALETTE, raster, save

def now():return datetime.now(timezone.utc).isoformat()

def run(case,inputs,out,cli):
    folder=out/case['id'];folder.mkdir(exist_ok=False)
    source=inputs/case['task']/'briefs'
    shutil.copyfile(source/f"{case['level']}.md",folder/'prompt.txt')
    shutil.copyfile(inputs/'producer-schema.json',folder/'schema.json')
    images=[source/'reference.png'] if case['level']=='detailed' else []
    argv=[cli,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--sandbox','read-only',
          '--model','gpt-6-astra','-c','model_reasoning_effort="high"','-c','features.shell_tool=false',
          '-c','features.apps=false','-c','features.plugins=false','-c','features.multi_agent=false','--json',
          '--output-schema',str(folder/'schema.json'),'-o',str(folder/'response.json')]
    for image in images:argv+=['-i',str(image)]
    argv+=['-'];start=time.monotonic();began=now();code=None;error=None;usage=None;delivered=False
    save(folder/'request.json',dict(**case,argv=argv,model_requested='gpt-6-astra',effort='high',
         prompt_sha256=sha(folder/'prompt.txt'),images={str(p):sha(p) for p in images},started_at_utc=began,
         isolation='Fresh ephemeral context; blank working directory; tools/apps/plugins disabled; no evaluator or prior output'))
    print('START '+case['id'],flush=True)
    try:
        with tempfile.TemporaryDirectory(prefix='brief-depth-') as cwd,(folder/'prompt.txt').open('rb') as stdin,(folder/'native-events.jsonl').open('wb') as stdout,(folder/'stderr.log').open('wb') as stderr:
            proc=subprocess.Popen(argv,stdin=stdin,stdout=stdout,stderr=stderr,cwd=cwd,start_new_session=True)
            paths=[folder/name for name in ('native-events.jsonl','stderr.log','response.json')]
            while proc.poll() is None:
                too_big=any(p.exists() and p.stat().st_size>8388608 for p in paths)
                if time.monotonic()-start>900 or too_big:
                    os.killpg(proc.pid,signal.SIGKILL);proc.wait();raise RuntimeError('Output budget exceeded' if too_big else '900-second model deadline exceeded')
                time.sleep(.2)
            code=proc.returncode
        if any(p.exists() and p.stat().st_size>8388608 for p in paths):raise RuntimeError('Output budget exceeded')
        if code!=0:raise RuntimeError(f'Model CLI exited {code}')
        response=json.loads((folder/'response.json').read_text());Draft202012Validator(json.loads((folder/'schema.json').read_text())).validate(response)
        rows=response['texture_rows']
        if len(rows)!=8 or any(len(row)!=8 or set(row)-PALETTE.keys() for row in rows):raise ValueError('Raster violates the common output interface')
        delivery=folder/'delivery';delivery.mkdir()
        (delivery/'scene.usda').write_text(response['scene_usda']);raster(delivery/'textures/label.png',rows)
        (folder/'producer-notes.txt').write_text(response['notes'])
        shutil.copytree(source,delivery/'briefs')
        save(folder/'delivery-manifest.json',dict(files={str(p.relative_to(delivery)):sha(p) for p in sorted(delivery.rglob('*')) if p.is_file()},
             adapter='USDA saved verbatim; model raster expanded to PNG; assessment briefs added after generation; no scene repairs'))
        delivered=True
    except Exception as exc:error=type(exc).__name__+': '+str(exc)
    events=[];event_errors=[]
    for line in (folder/'native-events.jsonl').read_text().splitlines():
        try:events.append(json.loads(line))
        except ValueError:event_errors.append(line[:300])
    for event in events:
        if event.get('type')=='turn.completed':usage=event.get('usage')
    unexpected=[e.get('item',{}).get('type') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')!='agent_message']
    record=dict(**case,status='DELIVERED' if delivered else 'NO_DELIVERY',error=error,exit_code=code,
                started_at_utc=began,completed_at_utc=now(),elapsed_seconds=round(time.monotonic()-start,3),usage=usage,
                model_requested='gpt-6-astra',resolved_model=None,thread_ids=[e['thread_id'] for e in events if e.get('type')=='thread.started'],
                unexpected_item_types=unexpected,native_event_parse_errors=event_errors)
    save(folder/'metrics.json',record);print(json.dumps(record),flush=True);return record

def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--cli',required=True);a=p.parse_args()
    a.inputs=a.inputs.resolve();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    schedule=json.loads((a.inputs/'schedule.json').read_text());assert len(schedule)==24
    frozen={str(p.relative_to(a.inputs)):sha(p) for p in a.inputs.rglob('*') if p.is_file()};save(a.out/'input-freeze.json',frozen)
    save(a.out/'dispatch.json',dict(workers=2,schedule=schedule,cli=a.cli,started_at_utc=now()))
    rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(run,case,a.inputs,a.out,a.cli):case for case in schedule}
        for future in as_completed(futures):
            rows.append(future.result());rows.sort(key=lambda r:next(i for i,c in enumerate(schedule) if c['id']==r['id']))
            save(a.out/'runs.json',rows)
    assert all(sha(a.inputs/f)==h for f,h in frozen.items())
    save(a.out/'input-integrity.json',dict(unchanged=True,files=frozen,completed_slots=len(rows)))

if __name__=='__main__':main()
