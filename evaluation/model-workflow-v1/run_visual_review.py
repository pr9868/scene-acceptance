"""Opt-in model study. Caller renders; harness checks/reviews; all attempts retained."""

from pathlib import Path
import argparse
import json
import shutil
from types import SimpleNamespace
from create_visual_controls import create
from scene_acceptance.application import invoke
from scene_acceptance.profiles import discover_artifact
from scene_acceptance.review_context import save
from scene_acceptance.model import sha
from scene_acceptance.image_policy import compare


def run(out, config, repeats):
    out.mkdir(parents=True, exist_ok=False)
    create(out / "scenes")
    rubric = dict(
        schema_version="1.0",
        id="sign-direction",
        version="1.0.0",
        criteria=[
            dict(
                id="sign",
                statement="In the front rendered view, the sign must read KEEP AISLE CLEAR in normal left-to-right lettering and its arrow must point to the viewer's right. Is this supported by the visible evidence? If the face cannot be seen or no view was supplied, say unknown and ask for a clear front view.",
                area="textures",
                evidence_kind="textured_view",
                limitation="Only the supplied view; no physical or hidden-surface conclusion.",
            )
        ],
    )
    save(out / "rubric.json", rubric)
    expected = json.loads((out / "scenes/expected.json").read_text())
    records = []
    for case in expected:
        bundle = out / "scenes" / ("correct" if case == "missing" else case)
        reference = bundle / "reference.png"
        if not reference.exists():
            shutil.copyfile(out / "scenes/correct/sign.png", reference)
        artifact = discover_artifact(bundle, "scene.usda")
        measured = compare(
            SimpleNamespace(
                artifact=artifact, bundle=artifact.bundle, sources=["reference.png"]
            ),
            dict(
                asset_attribute="/World/Looks/Sign/Texture.inputs:file",
                reference_image="reference.png",
                actual_space="srgb",
                reference_space="srgb",
                orientation="stored",
                max_linear_channel_error=0,
            ),
        )
        views = None
        if case != "missing":
            views = bundle / "views.json"
            save(
                views,
                dict(
                    schema_version="1.0",
                    scene_sha256=artifact.artifact_set_sha256,
                    up_axis="Z",
                    meters_per_unit=1,
                    views=[
                        dict(
                            id="front",
                            path="front.png",
                            sha256=sha(bundle / "front.png"),
                            camera_id="fixed-front",
                            camera="Fixed front orthographic, eye (0,-4,0), width 3.8 m",
                            projection="orthographic",
                            time_seconds=0,
                            method="Caller CPU saved-USD rasterization with flat Lambert shading and z-buffer",
                            producer="constructed developer control",
                            capabilities=["geometry", "surface_materials"],
                            limitations=[
                                "Diagnostic render; not RTX or calibrated photorealism"
                            ],
                            covered_prims=["/World/Sign"],
                            view_roles=["front"],
                        )
                    ],
                ),
            )
        for repeat in range(1, repeats + 1):
            result = invoke(
                "check",
                bundle_root=bundle,
                candidate="scene.usda",
                out=out / "runs" / f"{case}-{repeat}",
                mode="both",
                judge_config=config,
                views=views,
                rubric=out / "rubric.json",
            )
            data = result.get("data") or {}
            judge = data.get("judge", {})
            findings = judge.get("findings", [])
            records.append(
                dict(
                    case=case,
                    repeat=repeat,
                    source_pixels=measured.status,
                    source_evidence=measured.evidence,
                    expected=expected[case],
                    observed=[r["assessment"] for r in findings],
                    model_invoked=judge.get("model_invoked", False),
                    errors=result["errors"],
                    report=result.get("report"),
                )
            )
            save(
                out / "summary.json",
                dict(
                    constructed_controls=True,
                    records=records,
                    limitation="Small developer-authored study; no general detection accuracy or reviewer-time estimate. Missing-view guards make no model call.",
                ),
            )
    return (
        0
        if all(r["observed"] == [r["expected"]] and not r["errors"] for r in records)
        else 1
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--repeats", type=int, choices=[1, 2, 3], default=2)
    args = parser.parse_args()
    raise SystemExit(run(args.out.resolve(), args.model_config.resolve(), args.repeats))
