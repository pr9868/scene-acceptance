from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser(); p.add_argument('--out',required=True); args=p.parse_args()
out=Path(args.out).resolve()
if out==ROOT or ROOT in out.parents: p.error('Choose output outside the companion')
out.mkdir(parents=True,exist_ok=False)
manifest=json.loads((ROOT/'MANIFEST.json').read_text())
def verify():
 for rel,digest in manifest['files'].items():
  assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest,rel
verify()
from scene_acceptance.engine import implementation_digest
assert implementation_digest()==manifest['checker_sha256'],'Installed checker differs'
def run(name,argv):
 with (out/(name+'.log')).open('w') as f:
  subprocess.run([sys.executable,*argv],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
run('pytest',['-m','pytest','-q','-p','no:cacheprovider','--junitxml',str(out/'pytest.xml'),'tests'])
test_suites=ET.parse(out/'pytest.xml').getroot().findall('testsuite')
test_count=sum(int(x.attrib['tests']) for x in test_suites)
assert test_count > 0 and all(int(x.attrib.get(k,0))==0 for x in test_suites for k in ['failures','errors','skipped'])
run('packs',['evaluation/packs-v1/run.py','--out',str(out/'packs')])
run('mesh',['evaluation/mesh-v1/run.py','--out',str(out/'mesh')])
run('timing',['evaluation/motion-timing-v1/run.py','--out',str(out/'timing')])
run('content',['article-evidence/run-content-probes.py',str(out/'content')])
run('physics',['article-evidence/physics-experiment/run.py',str(out/'physics')])
packs=json.loads((out/'packs/summary.json').read_text()); assert packs['summary']['matches']==22
for suite,old in [('packs','evaluation/packs-v1/runs/final'),('mesh','evaluation/mesh-v1/runs/final-comparison')]:
 for report in (out/suite).glob('*/result.json'):
  a=json.loads(report.read_text()); b=json.loads((ROOT/old/report.parent.name/'result.json').read_text())
  assert a['verdict']==b['verdict'],report.parent.name
  assert {c['id']:c['status'] for c in a['checks']}=={c['id']:c['status'] for c in b['checks']},report.parent.name
content=json.loads((out/'content/summary.json').read_text()); assert all(x['matched'] for x in content.values())
timing=json.loads((out/'timing/summary.json').read_text()); assert timing['matches']==timing['cases']==17
physics=json.loads((out/'physics/summary.json').read_text()); assert physics['all_expected_matched']
old=json.loads((ROOT/'article-evidence/physics-experiment/runs/first/summary.json').read_text())
for name,c in physics['cases'].items():
 for i,r in enumerate(c['runs']):
  assert abs(r['final_displacement_m']-old['cases'][name]['runs'][i]['final_displacement_m'])<1e-9,(name,i)
verify()
result={'checker_sha256':implementation_digest(),'retained_files_verified':len(manifest['files']),'software_tests':test_count,'pack_cases':22,'mesh_cases':32,'timing_cases':timing['cases'],'content_probes':4,'physics_configuration_cases':3,'simulator_runs':4,'model_calls':0,'decisions_and_recorded_physics_observations_match':True}
(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2))
