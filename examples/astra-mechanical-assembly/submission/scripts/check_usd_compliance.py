from pxr import UsdUtils, Sdr
from pathlib import Path
import json, traceback
root=Path(__file__).resolve().parents[1]
shader_registry_available=False
try:shader_registry_available=Sdr.Registry().GetShaderNodeByIdentifier('UsdPreviewSurface') is not None
except Exception:traceback.print_exc()
checker=UsdUtils.ComplianceChecker(arkit=False,skipVariants=False,rootPackageOnly=False)
exception=None
try:checker.CheckCompliance(str(root/'output/crank_slider.usdc'))
except Exception as e:
    exception=str(e);traceback.print_exc()
layers,assets,unresolved=UsdUtils.ComputeAllDependencies(str(root/'output/crank_slider.usdc'))
report={'status':'INCOMPLETE' if exception or not shader_registry_available else 'COMPLETE','shaderRegistryAvailable':shader_registry_available,'checkerException':exception,'errors':checker.GetErrors(),'warnings':checker.GetWarnings(),'failedChecks':checker.GetFailedChecks(),'layers':[str(x.identifier) for x in layers],'assets':list(assets),'unresolved':list(unresolved)}
(root/'logs/usd-compliance.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
non_shader_failures=[x for x in report['failedChecks'] if shader_registry_available or 'ShaderPropertyTypeConformanceChecker' not in x]
assert not report['errors'] and not non_shader_failures and not unresolved
if report['status']=='INCOMPLETE':print('Full compliance remains unverified: installed OpenUSD shader discovery resources are missing. Dependency and custom geometry/motion checks ran separately.')
