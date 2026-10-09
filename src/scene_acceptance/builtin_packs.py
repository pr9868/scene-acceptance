"""Adapters reuse upstream checks and add narrowly declared consuming requirements."""

from pathlib import Path
import math
from importlib.metadata import version
from pxr import Usd, UsdGeom, UsdShade, UsdValidation, Sdf, Tf
from .packs import Pack, CheckSpec, Outcome
from .model import MissingEvidence, ContractError, strict_json, validate_contract


def obj(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


TEXT = {"type": "string", "minLength": 1}
NAMES = {
    "type": "array",
    "items": TEXT,
    "minItems": 1,
    "maxItems": 128,
    "uniqueItems": True,
}
VEC3 = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}


def prim(stage, path):
    p = Sdf.Path(path)
    if not p.IsAbsolutePath() or not p.IsPrimPath():
        raise ContractError("Expected an absolute prim path: " + path)
    return stage.GetPrimAtPath(p)


def native(ctx, params):
    registry = UsdValidation.ValidationRegistry()
    executed, issues = [], []
    for name in params["validators"]:
        validator = registry.GetOrLoadValidatorByName(name)
        if validator is None:
            raise RuntimeError("OpenUSD validator unavailable: " + name)
        mark = Tf.Error.Mark()
        mark.SetMark()
        try:
            found = validator.Validate(ctx.artifact.stage)
            if not mark.IsClean():
                raise RuntimeError(
                    "Native validator emitted an execution error: "
                    + str(list(mark.GetErrors()))
                )
        finally:
            mark.Clear()
        executed.append(name)
        for err in found:
            severity = str(err.GetType()).split(".")[-1]
            deferred = False
            runtime_evidence = []
            # Preserve the upstream issue verbatim. Only a recognized MDL
            # source-asset dependency is a resolver coverage gap; an ordinary
            # missing texture/reference remains a failure.
            if (
                str(err.GetIdentifier())
                == "usdUtilsValidators:MissingReferenceValidator.UnresolvableDependency"
            ):
                layers = {
                    site.GetLayer().realPath
                    for site in err.GetSites()
                    if site.GetLayer()
                }
                message = err.GetMessage()
                prefix, suffix = "Found unresolvable external dependency '", "'."
                if (
                    layers
                    and layers <= {str(p) for p in ctx.artifact.layers}
                    and message.startswith(prefix)
                    and message.endswith(suffix)
                ):
                    identifier = message[len(prefix) : -len(suffix)]
                    # OpenUSD can attach a composed dependency issue to the root
                    # layer and report either an authored search identifier or a
                    # normalized absolute path. Match only recorded dependencies.
                    matches = {
                        path
                        for path, references in ctx.artifact.dependency_references.items()
                        if identifier == str(path)
                        or any(identifier == ref["identifier"] for ref in references)
                    }
                    # A bare identifier can refer to files in several layers.
                    # Any ordinary use or unresolved ambiguity remains a failure.
                    deferred = bool(matches) and all(
                        path in ctx.artifact.runtime_assets
                        and ctx.artifact.assets.get(path) is None
                        for path in matches
                    )
                    if deferred:
                        from .runtime_dependencies import evidence_for

                        runtime_evidence = [
                            evidence_for(ctx, path) for path in sorted(matches)
                        ]
                        if not all(runtime_evidence):
                            runtime_evidence = []
            issues.append(
                {
                    "validator": name,
                    "id": str(err.GetIdentifier()),
                    "severity": severity,
                    "message": err.GetMessage(),
                    **(
                        {
                            "assessment": "PASS",
                            "reason": "Caller-attested runtime dependency satisfies the selected policy; the upstream local-resolver error is retained.",
                            "runtime_dependency_evidence": runtime_evidence,
                        }
                        if runtime_evidence
                        else (
                            {
                                "assessment": "UNKNOWN",
                                "reason": "MDL source asset requires a bundled library or target-runtime resolver evidence; no external resolver was invoked.",
                            }
                            if deferred
                            else {}
                        )
                    ),
                }
            )
    failed = any(
        x.get("assessment") not in ("UNKNOWN", "PASS")
        and (
            x["severity"] == "Error"
            or (params["warnings_as_failures"] and x["severity"] == "Warn")
        )
        for x in issues
    )
    return Outcome(
        (
            "FAIL"
            if failed
            else (
                "UNKNOWN"
                if any(x.get("assessment") == "UNKNOWN" for x in issues)
                else "PASS"
            )
        ),
        "Selected native OpenUSD validators executed.",
        {
            "executed": executed,
            "issues": issues,
            "usd_version": list(Usd.GetVersion()),
            "coverage": "Provider-specific validation; no fixes applied.",
        },
    )


def geometry(ctx, params):
    """Compatibility adapter executes an unchanged v1 contract through its existing engine."""
    from .engine import _evaluate_v1

    path = params["contract_file"]
    if path not in ctx.sources:
        raise ContractError(
            "Legacy geometry contract must be a declared evidence_source"
        )
    c = strict_json(ctx.bundle.record(path, missing=True))
    validate_contract(c)
    if (
        not {ctx.bundle.path(p) for p in c["allowed_dependencies"]}
        <= ctx.bundle.allowed
    ):
        raise ContractError("Nested geometry dependencies exceed the outer contract")
    if not set(c["evidence_sources"]) <= set(ctx.sources):
        raise ContractError("Nested geometry evidence exceeds declared outer evidence")
    result = _evaluate_v1(
        path,
        ctx.artifact.root,
        bundle_root=ctx.bundle.root,
        baseline_path=ctx.baseline.root if ctx.baseline else None,
        max_dependency_files=ctx.bundle.max_dependency_files,
    )
    mapping = {
        "ACCEPT_FOR_USE": "PASS",
        "REJECT": "FAIL",
        "INSUFFICIENT_EVIDENCE": "UNKNOWN",
        "EVALUATION_ERROR": "ERROR",
    }
    return Outcome(
        mapping[result["verdict"]],
        "Existing static geometry contract evaluated through the compatibility adapter.",
        {
            "checks": result["checks"],
            "coverage": result["coverage"],
            "identity": result["identity"],
        },
    )


def materials(ctx, params):
    stage = ctx.artifact.stage
    findings = []
    for path, expected in params["bindings"].items():
        p = prim(stage, path)
        if not p:
            findings.append(
                {
                    "object": path,
                    "property": "material:binding",
                    "status": "FAIL",
                    "reason": "Required object absent",
                }
            )
            continue
        prim(stage, expected)  # Validate the caller's path even when it does not exist.
        material, relationship = UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial(
            params["purpose"]
        )
        actual = str(material.GetPath()) if material else None
        findings.append(
            {
                "object": path,
                "property": "material:binding",
                "expected": expected,
                "observed": actual,
                "relationship": str(relationship.GetPath()) if relationship else None,
                "status": "PASS" if actual == expected else "FAIL",
            }
        )
        if material and params["surface_shader_id"]:
            shader, _, _ = material.ComputeSurfaceSource(params["render_context"])
            implementation = shader.GetImplementationSource() if shader else None
            source_asset = None
            if shader and implementation == UsdShade.Tokens.sourceAsset:
                source_type = params["render_context"]
                source_asset = shader.GetSourceAsset(source_type)
                actual_id = shader.GetSourceAssetSubIdentifier(source_type)
                shader_status = (
                    "UNKNOWN"
                    if not source_asset or not actual_id
                    else "PASS" if actual_id == params["surface_shader_id"] else "FAIL"
                )
            elif shader and implementation == UsdShade.Tokens.sourceCode:
                actual_id = None
                shader_status = "UNKNOWN"
            else:
                actual_id = shader.GetIdAttr().Get() if shader else None
                shader_status = (
                    "PASS" if actual_id == params["surface_shader_id"] else "FAIL"
                )
            findings.append(
                {
                    "object": str(material.GetPath()),
                    "property": "surface_shader_id",
                    "expected": params["surface_shader_id"],
                    "observed": actual_id,
                    "status": shader_status,
                    "implementation_source": implementation,
                    "source_asset": source_asset.path if source_asset else None,
                    "reason": "Compared declared surface implementation identity; no shader compilation or rendered appearance assessment.",
                }
            )
    for path, digest in sorted(ctx.artifact.assets.items()):
        from .runtime_dependencies import evidence_for

        runtime_evidence = evidence_for(ctx, path) if not digest else None
        findings.append(
            {
                "object": str(path.relative_to(ctx.bundle.root)),
                "property": "external_asset_exists",
                "expected": True,
                "observed": digest is not None,
                "status": (
                    "PASS"
                    if digest or runtime_evidence
                    else "UNKNOWN" if path in ctx.artifact.runtime_assets else "FAIL"
                ),
                **(
                    {
                        "reason": "Dependency availability accepted from caller attestation; no local file was supplied.",
                        "runtime_dependency_evidence": runtime_evidence,
                    }
                    if runtime_evidence
                    else (
                        {
                            "reason": "MDL library unresolved in the local bundle; supply target-runtime evidence or bundle the dependency."
                        }
                        if not digest and path in ctx.artifact.runtime_assets
                        else {}
                    )
                ),
                "sha256": digest,
            }
        )
    return Outcome(
        (
            "FAIL"
            if any(f["status"] == "FAIL" for f in findings)
            else (
                "UNKNOWN" if any(f["status"] == "UNKNOWN" for f in findings) else "PASS"
            )
        ),
        "Resolved bindings, selected surface shader IDs and declared external file existence checked.",
        {
            "findings": findings,
            "coverage": "Bindings and surface shader IDs at default time; external file existence across authored asset values. No image decode, UV fidelity, rendered appearance or friction inference.",
        },
    )


def motion(ctx, params):
    stage = ctx.artifact.stage
    p = prim(stage, params["path"])
    if not p or not p.IsA(UsdGeom.Xformable):
        return Outcome(
            "FAIL",
            "Required transformable object is absent.",
            {"object": params["path"]},
        )
    if not stage.HasAuthoredMetadata("metersPerUnit"):
        raise MissingEvidence("World-position comparisons require authored stage units")
    units = UsdGeom.GetStageMetersPerUnit(stage)
    if not math.isfinite(units) or units <= 0:
        raise MissingEvidence("Invalid stage units")
    times = [s["time_code"] for s in params["samples"]]
    if any(a >= b for a, b in zip(times, times[1:])):
        raise ContractError("Motion samples must be strictly increasing")
    if not stage.HasAuthoredTimeCodeRange() or any(
        t < stage.GetStartTimeCode() or t > stage.GetEndTimeCode() for t in times
    ):
        raise MissingEvidence(
            "Motion samples need an authored stage time range covering the requested time codes"
        )
    findings = []
    for sample in params["samples"]:
        t = sample["time_code"]
        matrix = UsdGeom.XformCache(Usd.TimeCode(t)).GetLocalToWorldTransform(p)
        actual = [float(v) * units for v in matrix.ExtractTranslation()]
        if not all(math.isfinite(v) for v in actual):
            raise MissingEvidence("Non-finite transform at time code " + str(t))
        expected = sample["world_origin_m"]
        findings.append(
            {
                "object": params["path"],
                "property": "world_transform_origin_m",
                "time_code": t,
                "observed": actual,
                "expected": expected,
                "tolerance_m": params["tolerance_m"],
                "error_metric": "maximum_absolute_coordinate_error",
                "maximum_coordinate_error_m": max(
                    abs(a - b) for a, b in zip(actual, expected)
                ),
                "euclidean_error_m": math.dist(actual, expected),
                "status": (
                    "PASS"
                    if all(
                        abs(a - b) <= params["tolerance_m"]
                        for a, b in zip(actual, expected)
                    )
                    else "FAIL"
                ),
            }
        )
    return Outcome(
        "FAIL" if any(f["status"] == "FAIL" for f in findings) else "PASS",
        "World transform origins compared per coordinate in metres at the explicitly requested time codes.",
        {
            "findings": findings,
            "time_codes": times,
            "time_codes_per_second": stage.GetTimeCodesPerSecond(),
            "interpolation": str(stage.GetInterpolationType()),
            "tolerance_metric": "per_coordinate_metres",
            "coverage": "Named sampled positions with a per-coordinate metre tolerance; Euclidean error is reported but is not the acceptance metric. Orientation, collisions, unsampled intervals and physical feasibility are untested.",
        },
    )


def nvidia(ctx, params):
    import contextlib
    import sys

    # Keep provider initialization/progress output separate from a caller's JSON stdout.
    with contextlib.redirect_stdout(sys.stderr):
        return _nvidia(ctx, params)


def _nvidia(ctx, params):
    # Optional package imported only when a selected check executes.
    if version("usd-validation-nvidia") != "1.20.0":
        raise RuntimeError("This adapter requires tested usd-validation-nvidia==1.20.0")
    import usd_validation_nvidia as nv

    registry = nv.CategoryRuleRegistry()
    issues, executed, measured = [], [], []
    for name in params["rules"]:
        rule = registry.find_rule(name)
        if rule is None:
            raise RuntimeError("NVIDIA rule unavailable: " + name)
        from .provider_coverage import observe_rule

        engine = nv.ValidationEngine(init_rules=False, variants=False)
        engine.enable_rule(rule)
        if engine.rules != [rule]:
            raise RuntimeError(
                "NVIDIA engine rule selection did not match the contract"
            )
        with observe_rule(rule, name) as visits:
            result = engine.validate(ctx.artifact.stage)
        if visits is not None:
            measured.extend(visits.values())
        executed.append(name)
        for issue in result:
            issues.append(
                {
                    "rule": issue.rule.__name__ if issue.rule else name,
                    "severity": issue.severity.name,
                    "message": issue.message,
                    "at": str(issue.at) if issue.at is not None else None,
                }
            )
    if any(x["severity"] == "ERROR" for x in issues):
        status = "ERROR"
    elif any(
        x["severity"] == "FAILURE"
        or (params["warnings_as_failures"] and x["severity"] == "WARNING")
        for x in issues
    ):
        status = "FAIL"
    else:
        status = "PASS"
    from .provider_coverage import KNOWN, measured_rules

    coverage_evidence = (
        {"assessment": measured_rules(measured)}
        if all(n in KNOWN for n in executed)
        else {}
    )
    return Outcome(
        status,
        "Selected NVIDIA Asset Validator rules executed without invoking fixers.",
        {
            "executed": executed,
            "issues": issues,
            "upstream_version": "1.20.0",
            **coverage_evidence,
            "coverage": "Only selected upstream rules; no SimReady profile certification or simulator run.",
        },
    )


def builtin_packs():
    source = (
        str(Path(__file__)),
        str(Path(__file__).with_name("provider_coverage.py")),
        str(Path(__file__).with_name("coverage.py")),
    )
    limitations = ("Local USD admission limits apply.",)
    return [
        Pack(
            "openusd",
            "1.1.0",
            "Named native OpenUSD validators",
            {
                "validators": CheckSpec(
                    native,
                    obj(
                        {
                            "validators": NAMES,
                            "warnings_as_failures": {"type": "boolean"},
                        }
                    ),
                    "Run explicit native validators",
                    "Named native validator scope",
                    limitations,
                )
            },
            source,
            ("usd-core",),
        ),
        Pack(
            "geometry",
            "1.0.0",
            "Existing bounded static geometry and edit contracts",
            {
                "contract": CheckSpec(
                    geometry,
                    obj({"contract_file": TEXT}),
                    "Evaluate an existing v1 contract",
                    "Existing cube/polygon/edit/evidence scope",
                    (
                        "Fixed topology/indexing for shape preservation; no collision or rendering",
                    ),
                )
            },
            source
            + tuple(
                str(Path(__file__).with_name(f))
                for f in (
                    "engine.py",
                    "checks.py",
                    "mesh.py",
                    "usd_reader.py",
                    "model.py",
                )
            ),
            ("usd-core", "jsonschema"),
        ),
        Pack(
            "materials",
            "1.1.0",
            "Material structure and delivery requirements",
            {
                "delivery": CheckSpec(
                    materials,
                    obj(
                        {
                            "bindings": {
                                "type": "object",
                                "minProperties": 1,
                                "maxProperties": 256,
                                "additionalProperties": TEXT,
                            },
                            "purpose": {"enum": ["", "allPurpose", "preview", "full"]},
                            "render_context": {"type": "string"},
                            "surface_shader_id": {"type": "string"},
                        }
                    ),
                    "Check resolved bindings, shader IDs and external files",
                    "Named material structure and dependency existence",
                    (
                        "No rendered appearance, image decoding, UV correctness or physical parameters",
                    ),
                )
            },
            source,
            ("usd-core",),
        ),
        Pack(
            "motion",
            "1.1.0",
            "Bounded authored-motion position samples",
            {
                "positions": CheckSpec(
                    motion,
                    obj(
                        {
                            "path": TEXT,
                            "tolerance_m": {"type": "number", "minimum": 0},
                            "samples": {
                                "type": "array",
                                "minItems": 1,
                                "maxItems": 1000,
                                "items": obj(
                                    {
                                        "time_code": {"type": "number"},
                                        "world_origin_m": VEC3,
                                    }
                                ),
                            },
                        }
                    ),
                    "Compare world origins at explicit time codes",
                    "Only named positions at supplied times",
                    (
                        "No continuous-time guarantee, collision, orientation or physics",
                    ),
                )
            },
            source,
            ("usd-core",),
        ),
        Pack(
            "nvidia.asset-validator",
            "1.1.0",
            "Optional NVIDIA Asset Validator adapter",
            {
                "rules": CheckSpec(
                    nvidia,
                    obj({"rules": NAMES, "warnings_as_failures": {"type": "boolean"}}),
                    "Run explicit NVIDIA rules without fixes",
                    "Named upstream rules only",
                    ("No simulator execution or SimReady profile certification",),
                )
            },
            source,
            ("usd-core", "usd-validation-nvidia"),
        ),
    ]
