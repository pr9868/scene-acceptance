"""Caller-authored text/image briefs with explicit check maps, never inferred intent."""

from copy import deepcopy
import base64
import json
from pathlib import Path
import shutil
from jsonschema import Draft202012Validator
from .artifact import EvidenceBundle
from .model import ContractError, digest_json, schema, sha, strict_json
from .packs import default_registry
from .profiles import baseline_contract, discovery_failure_report
from .review import assess
from .review.schemas import PLAN, TEXT, obj, array
from .review.__main__ import write_report as write_review
from .report import E, write_report as write_artifact
from .pdf_briefs import LOCATION

BRIEF_SCHEMA = obj(
    {
        "schema_version": {"const": "1.0"},
        "id": TEXT,
        "title": TEXT,
        "intended_use": TEXT,
        "provenance": TEXT,
        "files": array(
            obj(
                {
                    "path": TEXT,
                    "role": {"enum": ["text", "reference_image"]},
                    "caption": TEXT,
                }
            ),
            1,
        ),
        "mapping_review": PLAN["properties"]["mapping_review"],
        "checks": array(schema("contract-v2")["properties"]["checks"]["items"]),
        "requirements": PLAN["properties"]["items"],
    }
)
BRIEF_SCHEMA["properties"]["files"]["items"]["properties"]["source_location"] = LOCATION


from .model import save_json as save


def load_brief(root, path, expected_sha256=None):
    bundle = EvidenceBundle(root, [])
    manifest = bundle.record(path)
    if manifest.stat().st_size > 262144:
        raise ContractError("Brief manifest exceeds 256 KiB")
    if expected_sha256 and sha(manifest) != expected_sha256:
        raise ContractError("Brief does not match caller-pinned hash")
    data = strict_json(manifest)
    Draft202012Validator(BRIEF_SCHEMA).validate(data)
    names = [x["path"] for x in data["files"]]
    if len(set(names)) != len(names) or len(names) > 64:
        raise ContractError("Compiled brief requires up to 64 unique source files")
    snapshots = []
    image_bytes = 0
    for item in data["files"]:
        p = bundle.record(item["path"])
        row = {**item, "sha256": sha(p)}
        if item["role"] == "text":
            if p.stat().st_size > 65536:
                raise ContractError("Brief text exceeds 64 KiB")
            try:
                row["text"] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ContractError("Brief text must be UTF-8") from exc
        else:
            from .image_evidence import inspect_visual_reference

            image_bytes += p.stat().st_size
            if image_bytes > 33554432:
                raise ContractError("Brief reference images exceed 32 MiB total")
            row.update(inspect_visual_reference(p))
        snapshots.append(row)
    ids = [x["id"] for x in data["requirements"]]
    if len(set(ids)) != len(ids):
        raise ContractError("Brief requirement IDs must be unique")
    if any(x["layer"] != "explicit" for x in data["requirements"]):
        raise ContractError(
            "Brief convenience mode accepts explicit obligations only; use a review plan for other layers"
        )
    if not bundle.unchanged():
        raise ContractError("Brief changed during loading")
    return data, dict(bundle.hashes), snapshots


def add_brief_to_report(report_dir, context, input_root):
    """Snapshot source text/images into the portable report, with escaped presentation."""
    report_dir = Path(report_dir)
    assets = report_dir / "brief-sources"
    assets.mkdir()
    context = deepcopy(context)
    parts = [
        f'<section id="supplied-brief"><h2>The brief used for this assessment</h2><p><strong>{E(context["title"])}</strong></p>',
        f'<p>{E(context["provenance"])}</p>',
        "<p>Text and images are source evidence. Selected checks come from the saved requirement mapping. Raw-brief interpretation is a separate preparation step; this evaluation does not reinterpret the sources.</p>",
    ]
    for i, item in enumerate(context["files"]):
        suffix = (
            ".txt"
            if item["role"] == "text"
            else ".png" if item["mime"] == "image/png" else ".jpg"
        )
        relative = f"brief-sources/{i:02d}{suffix}"
        source = Path(input_root) / item["path"]
        if sha(source) != item["sha256"]:
            raise ContractError("Brief source changed before report packaging")
        shutil.copyfile(source, report_dir / relative)
        item["report_path"] = relative
        parts.append(
            f'<h3>{E(item["caption"])}</h3><p><a href="{relative}">Source file</a> · <code>{E(item["path"])}</code><small>SHA-256 {E(item["sha256"])}</small></p>'
        )
        if item.get("source_location"):
            location = item["source_location"]
            parts.append(
                f'<p>PDF page {E(location["page"])} · region {E(location["region_pdf_points"])} · {E(location["coordinates"])}. {E(location["extraction"])}</p>'
            )
        if item["role"] == "text":
            parts.append("<pre>" + E(item["text"]) + "</pre>")
        else:
            parts.append(
                f'<img src="{relative}" alt="{E(item["caption"])}" style="max-width:100%;width:auto;max-height:420px;image-rendering:pixelated">'
            )
    parts.append(
        '<p><a href="brief-context.json">Brief, provenance and source hashes</a></p></section>'
    )
    save(report_dir / "brief-context.json", context)
    document = (report_dir / "report.html").read_text()
    # Keep the verdict first, then brief before the scene/result matrix.
    marker = '<section class="reader-overview">'
    if marker not in document:
        marker = "<!--READER_OVERVIEW-->"
    if marker in document:
        document = document.replace(marker, "".join(parts) + marker, 1)
    else:
        document = document.replace("</main>", "".join(parts) + "</main>", 1)
    (report_dir / "report.html").write_text(document)
    summary = report_dir / "summary.md"
    summary.write_text(
        summary.read_text()
        + "\n## Supplied brief\n\n"
        + context["title"]
        + "\n\n"
        + context["provenance"]
        + "\n\n"
        + "\n\n".join(
            x.get("text", f"Reference image: {x['caption']}") for x in context["files"]
        )
        + "\n"
    )
    save(
        report_dir / "manifest.json",
        {
            "files": {
                str(p.relative_to(report_dir)): sha(p)
                for p in sorted(report_dir.rglob("*"))
                if p.is_file() and p != report_dir / "manifest.json"
            }
        },
    )


def evaluate_brief(
    path,
    candidate,
    *,
    bundle_root,
    out,
    expected_sha256=None,
    approved_packs=(),
    max_dependency_files=64,
    review_record=None,
    runtime_dependency_policy="local-only",
    runtime_environment_sha256=None,
    runtime_dependency_evidence=None,
):
    root = Path(bundle_root).resolve()
    out = Path(out).resolve()
    if out.exists() or out.is_relative_to(root) or root.is_relative_to(out):
        raise ContractError(
            "Brief output must be a new directory outside the input bundle and its ancestors"
        )
    data, brief_hashes, files = load_brief(root, path, expected_sha256)
    context = dict(
        id=data["id"],
        title=data["title"],
        provenance=data["provenance"],
        files=files,
        manifest_sha256=sha(root / path),
        requirements=data["requirements"],
        mapping_review=data["mapping_review"],
    )
    try:
        contract, identity = baseline_contract(
            root, candidate, max_dependency_files=max_dependency_files
        )
    except Exception as exc:
        out.mkdir(parents=True)
        report = discovery_failure_report(exc, root, max_dependency_files, candidate)
        report["coverage"]["unchecked"].append(
            "Every supplied brief obligation: scene admission did not complete"
        )
        write_artifact(report, out / "report")
        add_brief_to_report(out / "report", context, root)
        save(
            out / "source-integrity.json",
            {"brief_files": brief_hashes, "candidate_admitted": False},
        )
        return dict(
            core_verdict=report["verdict"],
            assessment_verdict=(
                "NEEDS_REVIEW"
                if report["verdict"] == "INSUFFICIENT_EVIDENCE"
                else "EVALUATION_ERROR"
            ),
        )
    source = EvidenceBundle(root, [])
    for name in set(identity["files"]) | set(brief_hashes):
        source.record_optional(name)
    # No source tree copying and no producer code execution: only the admitted closure and explicit brief files.
    out.mkdir(parents=True)
    staged = out / "inputs"
    owner = out / "caller"
    staged.mkdir()
    owner.mkdir()
    for name, expected in source.hashes.items():
        if expected is None:
            continue
        destination = staged / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, destination)
        if sha(destination) != expected:
            raise ContractError("Input changed while making evaluation snapshot")
    if not source.unchanged():
        raise ContractError("Source changed during snapshot")
    contract_name = "__brief_contract__.json"
    if (staged / contract_name).exists():
        raise ContractError("Reserved compiled-contract filename already exists")
    contract["id"] = "brief-" + data["id"]
    contract["intended_use"] = data["intended_use"]
    contract["report_context"] = {"scene_name": data["title"]}
    contract["evidence_sources"] = list(brief_hashes)
    registry = default_registry(
        approved_packs, selected=[c["pack"] for c in data["checks"]]
    )
    for item in data["checks"]:
        if item["id"] in {x["id"] for x in contract["checks"]}:
            raise ContractError("Brief check duplicates a baseline check ID")
        pack = registry.get(item["pack"]).describe()
        contract["packs"][item["pack"]] = {
            "version": pack["version"],
            "sha256": pack["implementation_sha256"],
        }
        contract["checks"].append(item)
    save(staged / contract_name, contract)
    plan = dict(
        schema_version="1.0",
        id="brief-study",
        intended_use=data["intended_use"],
        contract=contract_name,
        contract_sha256=sha(staged / contract_name),
        candidate=candidate,
        baseline=None,
        mapping_review=data["mapping_review"],
        report_context=contract["report_context"],
        layers={
            key: dict(
                scope="included" if key == "explicit" else "excluded",
                reason="Convenience brief mode covers listed explicit requirements only",
            )
            for key in PLAN["properties"]["layers"]["properties"]
        },
        items=data["requirements"],
    )
    save(owner / "plan.json", plan)
    review_name = None
    review_inputs = None
    if review_record:
        from .review.assessment import Inputs
        from .review.schemas import REVIEW

        review_path = Path(review_record).resolve()
        review_inputs = Inputs(review_path.parent)
        reviewed = review_inputs.json(review_path.name, REVIEW)
        for item in reviewed["reviews"]:
            for e in item["evidence"]:
                actual = review_inputs.record(e["path"])
                if actual != e["sha256"]:
                    raise ContractError("Caller review evidence identity mismatch")
                # Copy into a dedicated directory; preserve relative evidence names and snapshot pin.
                dest = owner / "review-evidence" / e["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(review_inputs.path(e["path"]), dest)
                if sha(dest) != actual:
                    raise ContractError("Caller review evidence changed during copy")
                e["path"] = "review-evidence/" + e["path"]
        review_name = "reviews.json"
        save(owner / review_name, reviewed)
        review_inputs.unchanged()
    report = assess(
        "plan.json",
        review_root=owner,
        bundle_root=staged,
        expected_plan_sha256=sha(owner / "plan.json"),
        pack_registry=registry,
        max_dependency_files=max_dependency_files,
        review_record=review_name,
        runtime_dependency_policy=runtime_dependency_policy,
        runtime_environment_sha256=runtime_environment_sha256,
        runtime_dependency_evidence=runtime_dependency_evidence,
    )
    if review_inputs:
        review_inputs.unchanged()
    write_review(report, out / "report")
    add_brief_to_report(out / "report", context, staged)
    if not source.unchanged():
        raise ContractError("Original input changed during evaluation")
    save(
        out / "source-integrity.json",
        dict(
            original_root=str(root),
            files=source.hashes,
            unchanged=True,
            missing_files=sorted(source.missing),
            copied_without_modification=True,
        ),
    )
    return report
