"""Model-free caller helpers; the same implementations back CLI and library use."""

from pathlib import Path
import shutil
from .model import ContractError, sha, strict_json
from .profiles import discover_artifact
from .review_context import save


def _output(out, protected):
    out = Path(out).resolve()
    if out.exists() or any(
        out.is_relative_to(Path(p).resolve()) or Path(p).resolve().is_relative_to(out)
        for p in protected
    ):
        raise ContractError("Helper output must be new and outside inputs")
    out.mkdir(parents=True)
    return out


def identify(*, bundle_root, candidate, out, max_dependency_files=64, max_prims=10000):
    artifact = discover_artifact(
        bundle_root,
        candidate,
        max_dependency_files=max_dependency_files,
        max_prims=max_prims,
    )
    data = dict(
        schema_version="1.0",
        scene_sha256=artifact.artifact_set_sha256,
        identity=artifact.identity,
        note="Content identity includes admitted files and missing dependencies; no acceptance claim.",
    )
    out = _output(out, [bundle_root])
    save(out / "identity.json", data)
    return data


def preflight(
    *,
    bundle_root,
    candidate,
    out,
    checks_file,
    max_dependency_files=64,
    max_prims=10000,
    approved_packs=(),
):
    from .preflight import checks
    from .packs import default_registry

    path = Path(checks_file)
    if path.stat().st_size > 8388608:
        raise ContractError("Check selection exceeds 8 MiB")
    selected = strict_json(path)
    if not isinstance(selected, list) or len(selected) > 512:
        raise ContractError("Provide a list of at most 512 selected checks")
    registry = default_registry(approved_packs, selected={c["pack"] for c in selected})
    artifact = discover_artifact(
        bundle_root,
        candidate,
        max_dependency_files=max_dependency_files,
        max_prims=max_prims,
    )
    report = checks(artifact, selected, registry)
    report.update(
        scene_sha256=artifact.artifact_set_sha256,
        selection_sha256=sha(path),
        exit_code=3 if report["status"] != "ready" else 0,
    )
    out = _output(out, [bundle_root, path])
    save(out / "preflight.json", report)
    return report


def package_evidence(*, preparation, view_spec, out, expected_plan_sha256):
    """Package caller assertions and pixels. Validation cannot prove rendering provenance."""
    from .preparation import load_preparation
    from .review_context import VIEWS_SCHEMA, read_view_image
    from .prepared_run import validate_prepared_evidence
    from jsonschema import Draft202012Validator

    root, plan = load_preparation(preparation)
    if plan["plan_sha256"] != expected_plan_sha256:
        raise ContractError("Evidence helper must pin the prepared plan")
    path = Path(view_spec).resolve()
    if path.stat().st_size > 1048576:
        raise ContractError("View specification exceeds 1 MiB")
    spec = strict_json(path)
    if (
        set(spec) != {"views", "requests"}
        or not isinstance(spec["views"], list)
        or len(spec["views"]) > 12
    ):
        raise ContractError(
            "View specification needs views (at most 12) and request-ID to view-ID lists"
        )
    if not isinstance(spec["requests"], dict):
        raise ContractError("requests must map request IDs to view ID lists")
    output = _output(out, [root, path])
    views = []
    for i, view in enumerate(spec["views"]):
        source = (path.parent / view["path"]).resolve()
        if not source.is_relative_to(path.parent) or not source.is_file():
            raise ContractError("View path escapes its specification folder")
        read_view_image(source)
        dest = output / f"view-{i:02d}{source.suffix.lower()}"
        shutil.copyfile(source, dest)
        if sha(source) != sha(dest):
            raise ContractError("Image changed during packaging")
        views.append(dict(view, path=dest.name, sha256=sha(dest)))
    context = strict_json(root / "admission/context.json")
    structure = context["scene"]["inventory"]["scene_structure"]
    manifest = dict(
        schema_version="1.0",
        scene_sha256=plan["scene_sha256"],
        up_axis=structure["up_axis"],
        meters_per_unit=structure["meters_per_unit"],
        views=views,
    )
    Draft202012Validator(VIEWS_SCHEMA).validate(manifest)
    captures = strict_json(root / "capture-plan.json")["requests"]
    known = {c["id"] for c in captures}
    if set(spec["requests"]) - known:
        raise ContractError("Unknown capture request ID")
    requests = []
    for c in captures:
        ids = spec["requests"].get(c["id"], [])
        if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
            raise ContractError("Request mapping must contain view ID lists")
        requests.append(
            dict(
                request_id=c["id"],
                status="supplied" if ids else "unavailable",
                view_ids=ids,
                reason=(
                    "Caller supplied listed views"
                    if ids
                    else "Caller has not supplied this evidence"
                ),
            )
        )
    receipt = dict(
        schema_version="1.0",
        plan_sha256=plan["plan_sha256"],
        scene_sha256=plan["scene_sha256"],
        requests=requests,
    )
    save(output / "views.json", manifest)
    save(output / "receipt.json", receipt)
    result = validate_prepared_evidence(
        preparation=root,
        out=output / "validation",
        views=output / "views.json",
        receipt=output / "receipt.json",
        expected_plan_sha256=plan["plan_sha256"],
    )
    return dict(
        scene_sha256=plan["scene_sha256"],
        views=str(output / "views.json"),
        receipt=str(output / "receipt.json"),
        validation=result,
        exit_code=result.get("exit_code", 0),
        limitations=[
            "Caller assertions describe cameras, time and visibility; packaging does not authenticate renderer provenance or prove target visibility."
        ],
    )
