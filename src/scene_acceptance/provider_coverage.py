"""Observed prim callbacks for seven pinned NVIDIA 1.20.0 rules.

Eligibility follows the provider's gates. Unsupported rules retain unknown counts.
Wrapping calls never repairs inputs or changes reported provider issues.
"""
from pxr import Usd, UsdGeom, UsdShade
from .coverage import assessment

KNOWN = {'ValidateTopologyChecker','ExtentsChecker','NormalsValidChecker','NormalsExistChecker',
         'NormalsWindingsChecker','ZeroAreaFaceChecker','UsdDanglingMaterialBinding'}


def eligible(name, p, rule):
    if name=='ExtentsChecker':
        return (True, '') if p.IsA(UsdGeom.Boundable) else (None,'')
    if name=='UsdDanglingMaterialBinding':
        rel=p.GetRelationship(UsdShade.Tokens.materialBinding)
        return (True,'') if rel and rel.GetTargets() else (None,'')
    if not p.IsA(UsdGeom.Mesh): return None,''
    mesh=UsdGeom.Mesh(p)
    if name=='NormalsExistChecker': return True,''
    if name=='ValidateTopologyChecker':
        return (True,'') if next(rule._get_validate_topology_args(mesh),None) is not None else (False,'Provider has no common topology sample to validate')
    if name in ('ZeroAreaFaceChecker','NormalsWindingsChecker'):
        attrs=[mesh.GetPointsAttr(),mesh.GetFaceVertexIndicesAttr(),mesh.GetFaceVertexCountsAttr()]
        if any(not a.IsAuthored() or a.ValueMightBeTimeVarying() for a in attrs):
            return False,'Provider requires authored static points, indices and face counts'
        if name=='ZeroAreaFaceChecker':
            pts,indices,counts=[a.Get(Usd.TimeCode.EarliestTime()) for a in attrs]
            if not (pts and indices and counts) or not UsdGeom.Mesh.ValidateTopology(indices,counts,len(pts))[0]:
                return False,'Provider skips face area when topology is invalid'
            return True,''
    if name in ('NormalsValidChecker','NormalsWindingsChecker'):
        from usd_validation_nvidia.rules import _geometry as g
        src=g._get_normals_source(mesh,Usd.TimeCode.EarliestTime())
        if src is None: return False,'Provider found no normal values to evaluate'
        if name=='NormalsWindingsChecker':
            if mesh.GetOrientationAttr().ValueMightBeTimeVarying(): return False,'Provider requires static orientation'
            interp,normals,count,_,indexed,indices=src
            expected=g._get_expected_normals_count(mesh,interp)
            if expected is None or count!=expected: return False,'Provider skips incompatible normal interpolation/count'
            if indexed and not g._normal_indices_reference_existing_values(normals,indices):
                return False,'Provider skips invalid normal indices'
        return True,''
    return False,'Provider coverage is not instrumented'


from contextlib import contextmanager
from threading import RLock
_PROVIDER_LOCK = RLock()


@contextmanager
def observe_rule(rule, name):
    # The upstream registry keys issues by exact class identity. Keep that identity
    # and serialize the temporary callback instrumentation; always restore it.
    with _PROVIDER_LOCK:
        if name not in KNOWN:
            yield None
            return
        visited = {}
        original = rule.CheckPrim
        def observed(self, p):
            try: applies, reason = eligible(name, p, self)
            except Exception as exc: applies, reason = False, 'Coverage eligibility error: ' + type(exc).__name__
            before = len(self.GetIssues())
            original(self, p)
            if applies is None: return
            issues = self.GetIssues()[before:]
            severities = {x.severity.name for x in issues}
            status = ('ERROR' if 'ERROR' in severities else 'FAIL' if 'FAILURE' in severities else
                      'WARNING' if 'WARNING' in severities else 'PASS' if applies else 'SKIPPED')
            visited[str(p.GetPath())] = dict(subject=str(p.GetPath()), status=status, reason=reason,
                                             finding_count=len(issues), rule=name)
        rule.CheckPrim = observed
        try:
            yield visited
        finally:
            rule.CheckPrim = original


def measured_rules(rows):
    return assessment('prim-rule evaluations', rows,
        'Observed provider CheckPrim callbacks, with eligibility gates for NVIDIA 1.20.0. PASS means no finding for this rule on this subject, not visual or physical correctness. Skips are retained. Extents accepts provider-permitted implicit bounds; topology and normals have provider-specific time scope.')
