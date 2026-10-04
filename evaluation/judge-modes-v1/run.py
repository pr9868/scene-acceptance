"""Freeze then run advisory reviews over retained, unmodified scene deliveries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import subprocess
import time
import scene_acceptance
from scene_acceptance.engine import implementation_digest
from scene_acceptance.model import sha,digest_json
from scene_acceptance.review_context import GENERAL_RUBRIC


def save(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')

def prepare(old,root,cli,harness):
    root.mkdir(parents=True,exist_ok=False);(root/'views').mkdir();(root/'runs').mkdir()
    schedule=json.loads((old/'inputs/schedule.json').read_text());assert len(schedule)==24
    plan=[];repeat=[];families=set()
    for row in schedule:
        ident=row['id'];original=old/'production'/ident/'delivery';dest=root/'views'/ident;dest.mkdir()
        viewroot=old/'assessments'/ident/'views-depth-v2'
        receipt=json.loads((viewroot/'view-evidence.json').read_text())
        from scene_acceptance.profiles import discover_artifact
        artifact=discover_artifact(original,'scene.usda');assert artifact.identity==receipt['candidate']
        views=[]
        for i,v in enumerate(receipt['views']):
            assert sha(viewroot/v['image'])==v['sha256'];shutil.copyfile(viewroot/v['image'],dest/v['image'])
            views.append(dict(id=f'frame-{i}',path=v['image'],sha256=v['sha256'],camera_id='diagnostic-isometric',
                camera='Fixed orthographic diagnostic isometric projection; identical scene framing across all three timestamps',
                projection='orthographic',time_seconds=v['elapsed_s'],method='Retained per-pixel depth-tested geometric projection',
                producer='brief-depth-v1/depth_views.py; renderer SHA256 '+receipt['renderer_sha256'],capabilities=['geometry'],
                limitations=[receipt['limitation'],'Processed geometry can be occluded; membership is not a claim that every part is visible.'],covered_prims=v['covered_geometry']))
        save(dest/'views.json',dict(schema_version='1.0',scene_sha256=artifact.artifact_set_sha256,up_axis='Z',meters_per_unit=1,views=views))
        shutil.copyfile(viewroot/'view-evidence.json',dest/'original-renderer-receipt.json')
        job=dict(**row,scene_id=ident,phase='primary',bundle_root=str(original.resolve()),brief='briefs/detailed.json',
                 views=str((dest/'views.json').resolve()),exposure='withheld')
        plan.append(job)
        if row['level']=='detailed' and row['task'] not in families:
            repeat.append(dict(job,id=ident+'-repeat',phase='repeat'));families.add(row['task'])
    plan+=repeat
    target=next(j for j in plan if j['id']=='gantry-detailed-02')
    plan += [dict(target,id=target['id']+'-no-brief',phase='context',brief=None),
             dict(target,id=target['id']+'-script-aware',phase='context',exposure='script-aware')]
    save(root/'plan.json',plan)
    save(root/'judge-config.json',dict(driver='codex',executable=str(cli.resolve()),args=[],model='gpt-6-astra',effort='high',timeout_seconds=600))
    save(root/'rubric.json',GENERAL_RUBRIC)
    freeze=root/'frozen-study';freeze.mkdir()
    for name in ('PROTOCOL.md','run.py'):shutil.copyfile(Path(__file__).parent/name,freeze/name)
    runtime=Path(scene_acceptance.__file__).parent
    shutil.copytree(runtime,root/'frozen-runtime/scene_acceptance',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    originals={str(p.resolve()):sha(p) for job in plan[:24] for p in Path(job['bundle_root']).rglob('*') if p.is_file()}
    files={str(p.relative_to(root)):sha(p) for folder in ('views','frozen-study','frozen-runtime') for p in (root/folder).rglob('*') if p.is_file()}
    files.update({name:sha(root/name) for name in ('plan.json','judge-config.json','rubric.json')})
    save(root/'freeze.json',dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),checker_sha256=implementation_digest(),
        original_packet=str(old.resolve()),original_packet_seal_sha256=sha(old/'PACKET_MANIFEST.json'),original_files=originals,
        files=files,harness=str(harness.resolve()),cli_version=subprocess.check_output([str(cli),'--version'],text=True).strip(),
        primary=24,repeats=3,context_probes=2,model_calls_planned=29,judge_snapshot=None))
    print(json.dumps({'prepared':len(plan),'checker_sha256':implementation_digest()}),flush=True)


def run(root):
    frozen=json.loads((root/'freeze.json').read_text());assert implementation_digest()==frozen['checker_sha256']
    assert all(sha(root/p)==h for p,h in frozen['files'].items())
    assert all(sha(p)==h for p,h in frozen['original_files'].items())
    lock=root/'STARTED.json'
    with lock.open('x') as f:json.dump({'started_at_utc':datetime.now(timezone.utc).isoformat(),'automatic_retries':0},f)
    plan=json.loads((root/'plan.json').read_text())
    def one(job):
        folder=root/'runs'/job['id'];folder.mkdir(exist_ok=False);save(folder/'job.json',job)
        argv=[frozen['harness'],'--bundle-root',job['bundle_root'],'--candidate','scene.usda','--mode','both',
              '--judge-config',str(root/'judge-config.json'),'--views',job['views'],'--rubric',str(root/'rubric.json'),
              '--judge-exposure',job['exposure'],'--out',str(folder/'evaluation')]
        if job['brief'] is not None:argv+=['--brief',job['brief']]
        started=datetime.now(timezone.utc).isoformat();tick=time.monotonic()
        save(folder/'invocation.json',dict(argv=argv,started_at_utc=started))
        print(json.dumps({'started':job['id'],'phase':job['phase']}),flush=True)
        with (folder/'stdout.log').open('wb') as stdout,(folder/'stderr.log').open('wb') as stderr:
            proc=subprocess.run(argv,stdout=stdout,stderr=stderr,check=False)
        result_path=folder/'evaluation/evaluation.json';result=json.loads(result_path.read_text()) if result_path.exists() else None
        row=dict(id=job['id'],scene_id=job['scene_id'],phase=job['phase'],task=job['task'],level=job['level'],repetition=job['repetition'],
            returncode=proc.returncode,elapsed_seconds=round(time.monotonic()-tick,3),started_at_utc=started,
            judge_status=(result or {}).get('judge',{}).get('status','unassessed'),
            opinions=(result or {}).get('judge',{}).get('counts',{}),errors=(result or {}).get('errors',['No result'] if result is None else []))
        save(folder/'receipt.json',row);print(json.dumps(row),flush=True);return row
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,plan))
    assert all(sha(p)==h for p,h in frozen['original_files'].items())
    save(root/'results.json',dict(checker_sha256=implementation_digest(),rows=rows,originals_unchanged=True))


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    p.add_argument('--original',type=Path);p.add_argument('--cli',type=Path);p.add_argument('--harness',type=Path);a=p.parse_args()
    if a.prepare:
        if not all((a.original,a.cli,a.harness)):p.error('Preparation needs original packet, CLI and harness')
        prepare(a.original.resolve(),a.root.resolve(),a.cli,a.harness)
    else:run(a.root.resolve())
if __name__=='__main__':main()
