"""Coordinator checks of the submitted USD and separately loaded GLB poses.

The nine times and 0.5 mm threshold were fixed in PROTOCOL.md before production.
This compares saved transforms, not collision geometry or simulated dynamics.
"""
from pathlib import Path
import hashlib, json, math
from pxr import Usd, UsdGeom, Gf

root = Path(__file__).resolve().parents[1]
scene = root / 'submission/output/crank_slider.usdc'
stage = Usd.Stage.Open(str(scene))
base = '/root/CRANK_SLIDER_ASSEMBLY/'
paths = {
    'Crank_Center': base + 'Crank_Center',
    'Crank_Pin': base + 'Crank_Rotation/Crank_Pin',
    'Slider_Pin': base + 'Slider_Translation/Slider_Pin',
}
scale = UsdGeom.GetStageMetersPerUnit(stage)
rate, start = stage.GetTimeCodesPerSecond(), stage.GetStartTimeCode()
times = [0, .5, 1, 1.5, 2, 2.5, 3, 3.5, 4]
distance = lambda a, b: math.dist(a, b)
rows = []
for t in times:
    cache = UsdGeom.XformCache(Usd.TimeCode(start + t * rate))
    pins = {n: [float(x)*scale for x in cache.GetLocalToWorldTransform(stage.GetPrimAtPath(p)).ExtractTranslation()] for n,p in paths.items()}
    c, p, q = [pins[n] for n in paths]
    rod = cache.GetLocalToWorldTransform(stage.GetPrimAtPath(base + 'Connecting_Rod_Pose'))
    ends = [[float(x)*scale for x in rod.Transform(Gf.Vec3d(*v))] for v in [(0,0,0),(.110,0,0)]]
    theta = 2*math.pi*t/4
    expected_pin = [c[0]+.035*math.cos(theta), c[1]+.035*math.sin(theta), c[2]]
    rows.append({'elapsed_s':t, 'pins_usd_m':pins, 'radius_error_m':abs(distance(c,p)-.035), 'pin_spacing_error_m':abs(distance(p,q)-.110), 'slider_line_error_m':math.hypot(q[1]-c[1], q[2]-c[2]), 'phase_position_error_m':distance(p,expected_pin), 'rod_endpoint_error_m':max(distance(ends[0],p),distance(ends[1],q))})
metrics = {key:max(row[key] for row in rows) for key in rows[0] if key.endswith('_error_m')}
metrics['loop_pin_error_m'] = max(distance(rows[0]['pins_usd_m'][n],rows[-1]['pins_usd_m'][n]) for n in paths)
browser = json.loads((root/'evidence/coordinator-browser-review.json').read_text())
comparisons=[]
for device in browser['results']:
    for t, row, glb in zip(times,rows,device['samples'], strict=True):
        assert abs(glb['time']-t)<1e-6
        for name, xyz in row['pins_usd_m'].items():
            # Blender's Z-up USD to glTF's Y-up export conversion.
            expected=[xyz[0],xyz[2],-xyz[1]]
            comparisons.append({'device':device['device'],'elapsed_s':t,'pin':name,'error_m':distance(expected,glb['pins'][name])})
metrics['usd_glb_pin_error_m']=max(row['error_m'] for row in comparisons)
tolerance=.0005
report={'method':'Coordinator measurements from frozen USD plus the GLB actually loaded by the browser; separate from producer self-checks. Same coordinated exercise, not independent validation.', 'usd_sha256':hashlib.sha256(scene.read_bytes()).hexdigest(),'preselected_seconds':times,'tolerance_m':tolerance,'metrics':metrics,'passed':all(v<=tolerance for v in metrics.values()),'samples':rows,'format_comparisons':comparisons,'limits':'Finite saved-transform samples. No whole-interval guarantee, contact/collision check, physical calibration, manufacturing suitability or material render equivalence. The preselected half-second samples would not have caught the intermediate Euler-wrap defect.'}
(root/'evidence/coordinator-kinematics.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['passed','metrics','tolerance_m','usd_sha256']}))
assert report['passed']
