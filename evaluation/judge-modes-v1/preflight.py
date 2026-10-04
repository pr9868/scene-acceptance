"""Replay every admitted study input with a software adapter before model calls."""
import argparse,json,sys
from pathlib import Path
from scene_acceptance.evaluation import evaluate_scene
from scene_acceptance.model import sha

def main():
 p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True);p.add_argument('--original',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 adapter=out/'adapter.py';adapter.write_text("import json,sys\nr=json.load(sys.stdin)\nitems=[]\nfor x in r['requirements']:\n ids=r['evidence_coverage'][x['id']]['suitable_evidence_ids']\n items.append(dict(requirement_id=x['id'],assessment='consistent' if ids else 'unknown',explanation='Software input preflight only, not a model opinion.',evidence_ids=ids[:1]))\nprint(json.dumps(dict(request_sha256=r['request_sha256'],items=items,limitations=['No model call or semantic validation.'])))\n")
 config=out/'config.json';config.write_text(json.dumps(dict(driver='json-cli',executable=sys.executable,args=[str(adapter)],model='software-preflight',effort='none',timeout_seconds=10)))
 plan=json.loads((a.study/'plan.json').read_text());rows=[]
 for job in plan:
  result=evaluate_scene(bundle_root=job['bundle_root'],candidate='scene.usda',out=out/job['id'],mode='both',brief=job['brief'],judge_config=config,views=job['views'],judge_exposure=job['exposure'])
  assert not result['errors'],(job['id'],result['errors'])
  report=out/job['id']/'script';report=report/'report' if job['brief'] else report
  core=json.loads((report/('core-result.json' if job['brief'] else 'result.json')).read_text())
  original=a.original/'assessments'/job['scene_id'];original=original/'full/report/core-result.json' if job['brief'] else original/'default/result.json'
  before=json.loads(original.read_text())
  assert core['verdict']==before['verdict'] and {c['id']:c['status'] for c in core['checks']}=={c['id']:c['status'] for c in before['checks']},job['id']
  assert result['source_unchanged']
  row=dict(id=job['id'],status=result['execution_status'],opinions=result['judge']['counts'],script_parity=True,source_unchanged=True);rows.append(row);print(json.dumps(row),flush=True)
 (out/'verification.json').write_text(json.dumps(dict(cases=len(rows),model_calls=0,all_original_script_outcomes_match=True,rows=rows),indent=2)+'\n')
if __name__=='__main__':main()
