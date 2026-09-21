"""Make presentation timing explicit and save a text-editable USD companion."""
from pxr import Usd, UsdGeom, Gf
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
stage=Usd.Stage.Open(str(ROOT/'output/crank_slider.usdc'))
stage.SetFramesPerSecond(60); stage.SetTimeCodesPerSecond(60)
stage.SetStartTimeCode(0); stage.SetEndTimeCode(240)
UsdGeom.SetStageMetersPerUnit(stage,1.0); UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
# Blender serializes decomposed Euler angles in [-180,180]. Interpolation across
# that wrap takes the long path in USD. Author the known continuous crank phase.
crank=next(p for p in stage.Traverse() if p.GetName()=='Crank_Rotation')
rotation=crank.GetAttribute('xformOp:rotateXYZ')
for frame in range(241):rotation.Set(Gf.Vec3f(0,0,frame*1.5),Usd.TimeCode(frame))
stage.GetRootLayer().customLayerData={
    'description':'Kinetic 01: synthetic tabletop crank-slider; loop frames 0–240 at 60 fps (4 seconds).',
    'crankRadiusMetres':.035,'rodPinToPinMetres':.110,'periodSeconds':4.0,
    'loopPlayback':'Repeat time codes 0 through 240; USD does not mandate player looping.',
    'referencePoints':'Crank_Center, Crank_Pin, Slider_Pin are named Xform origins at z=0.102 m.',
    'limitations':'Kinematic visualization only; no physical or manufacturing validation.'}
stage.GetRootLayer().Save()
stage.GetRootLayer().Export(str(ROOT/'output/crank_slider.usda'))
print('Finalized USD: Z up, metresPerUnit=1, fps=60, timeCodesPerSecond=60, 0–240 inclusive.')
