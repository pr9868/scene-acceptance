from pathlib import Path
import hashlib,json,sys
from PIL import Image
from pxr import Usd,UsdGeom,UsdShade
from scene_acceptance.engine import evaluate
from scene_acceptance.report import write_report
R=Path(__file__).resolve().parent/'content-probes'
O=Path(sys.argv[1]).resolve(); O.mkdir(parents=True,exist_ok=False)
frozen=json.loads((R/'frozen-inputs.json').read_text())
for p,h in frozen.items(): assert hashlib.sha256((R/p).read_bytes()).hexdigest()==h
protocol=json.loads((R/'protocol.json').read_text()); result={}
for name,expected in protocol['expected'].items():
 d=R/'fixtures'/name
 report=evaluate(d/'contract.json',d/'scene.usda',bundle_root=d); write_report(report,O/name)
 s=Usd.Stage.Open(str(d/'scene.usda'))
 item={'verdict':report['verdict'],'expected':expected,'scene_sha256':hashlib.sha256((d/'scene.usda').read_bytes()).hexdigest()}
 if 'png_decodes' in expected:
  try:
   with Image.open(d/'pixel.png') as image: image.load(); decoded=True
  except Exception as exc: decoded=False; item['decoder_error']=type(exc).__name__+': unreadable image'
  item['png_decodes']=decoded
  item['resolved_binding']=str(UsdShade.MaterialBindingAPI(s.GetPrimAtPath('/World/Panel')).ComputeBoundMaterial()[0].GetPath())
 else:
  item['authored_times']=s.GetPrimAtPath('/World/Panel').GetAttribute('xformOp:translate').GetTimeSamples()
  item['positions']=[{'time_code':t,'world_origin_m':list(UsdGeom.XformCache(Usd.TimeCode(t)).GetLocalToWorldTransform(s.GetPrimAtPath('/World/Panel')).ExtractTranslation())} for t in [i/20 for i in range(41)]]
 item['matched']=all(item[k]==v for k,v in expected.items()); result[name]=item
for p,h in frozen.items(): assert hashlib.sha256((R/p).read_bytes()).hexdigest()==h
(O/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({n:{k:v for k,v in r.items() if k!='positions'} for n,r in result.items()},indent=2))
