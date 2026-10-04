"""Installed CLI integration from both host languages, using an explicit test double."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from scene_acceptance.model import sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--harness',required=True);p.add_argument('--node',required=True);a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    source=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('prepare',source/'evaluation/brief-study-v1/prepare.py');prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
    bundle=prepare.prepare(out/'inputs')/'panel'
    adapter=out/'adapter.py';adapter.write_text("import json,sys\nr=json.load(sys.stdin)\nprint(json.dumps(dict(request_sha256=r['request_sha256'],items=[dict(requirement_id=x['id'],assessment='unknown',explanation='Software test double; no model call.',evidence_ids=[]) for x in r['requirements']],limitations=['Deterministic software control only.'])))\n")
    config=out/'judge.json';config.write_text(json.dumps(dict(driver='json-cli',executable=sys.executable,args=[str(adapter)],model='software-test-double',effort='none',timeout_seconds=10)))
    before={str(p.relative_to(bundle)):sha(p) for p in bundle.rglob('*') if p.is_file()};receipts=[]
    for host in ('python','node'):
        for mode in (None,'checks','judge','both'):
            for brief in (None,'briefs/image-b.json'):
                ident=f'{host}-{mode or "legacy"}-'+('brief' if brief else 'general');directory=out/(ident+' report')
                request=dict(harness=a.harness,bundle_root=str(bundle),candidate='scene.usda',brief=brief,out=str(directory),timeout_seconds=120)
                if mode:request['mode']=mode
                if mode in ('judge','both'):request['judge_config']=str(config)
                req=out/(ident+'.json');req.write_text(json.dumps(request))
                cmd=[sys.executable,str(source/'examples/application-integration/python_app.py'),str(req)] if host=='python' else [a.node,str(source/'examples/application-integration/node_app.mjs'),str(req)]
                process=subprocess.run(cmd,capture_output=True,text=True);data=json.loads(process.stdout)
                (out/(ident+'-response.json')).write_text(process.stdout);(out/(ident+'-stderr.log')).write_text(process.stderr)
                expected=3 if mode=='judge' else 2 if brief else 3 if mode=='both' else 0
                assert data['status']=='reported' and data['process_exit_code']==expected and process.returncode==expected,(ident,data)
                receipts.append(dict(id=ident,exit_code=expected,artifact=data['artifact_verdict'],scope=data['declared_scope_verdict'],judge=data.get('judge_status')))
    assert before=={str(p.relative_to(bundle)):sha(p) for p in bundle.rglob('*') if p.is_file()}
    for i in range(8):assert {k:v for k,v in receipts[i].items() if k!='id'}=={k:v for k,v in receipts[i+8].items() if k!='id'}
    (out/'verification.json').write_text(json.dumps(dict(calls=16,model_calls=0,source_unchanged=True,host_outcomes_agree=True,receipts=receipts),indent=2)+'\n')
    print(json.dumps({'calls':16,'model_calls':0,'source_unchanged':True,'host_outcomes_agree':True}))
if __name__=='__main__':main()
