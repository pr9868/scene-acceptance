"""Evidence transport controls; these fixtures do not measure real model quality."""

import json
from pathlib import Path
import sys

import pytest
from jsonschema import ValidationError
from PIL import Image, ImageCms

from scene_acceptance.application import invoke
from scene_acceptance.assumption_audit import validate_response
from scene_acceptance.external_evidence import performance, engine_tests
from scene_acceptance.image_policy import linear_pixels
from scene_acceptance.isolation import invoke_isolated, supervise
from scene_acceptance.model import sha, strict_json, ContractError, MissingEvidence
from scene_acceptance.preparation import _read_raw, prepare_scene
from test_extensions_geometry import scene, context
from test_review import save


def pdf(path):
    # Minimal independent PDF fixture with embedded text and a visible rectangle.
    content = b"BT /F1 12 Tf 20 160 Td (Keep the service aisle clear.) Tj ET\n20 20 100 80 re S\n"
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 240 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(content)).encode()
        + b" >>\nstream\n"
        + content
        + b"endstream",
    ]
    data = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(bodies, 1):
        offsets.append(len(data))
        data += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    start = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    data += (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(start).encode()
        + b"\n%%EOF\n"
    )
    path.write_bytes(data)


def raw(root):
    pdf(root / "brief.pdf")
    value = dict(
        schema_version="1.0",
        id="drawing",
        title="Drawing brief",
        intended_use="Layout illustration",
        provenance="Synthetic PDF control",
        files=[
            dict(
                path="brief.pdf",
                role="pdf",
                caption="Aisle drawing",
                selections=[dict(page=1, region_pdf_points=[0, 0, 240, 200])],
            )
        ],
    )
    save(root / "raw.json", value)
    return value


def test_pdf_text_and_image_keep_exact_source_location(tmp_path):
    raw(tmp_path)
    _, rows, hashes = _read_raw(tmp_path, "raw.json")
    assert len(rows) == 2 and "service aisle" in rows[0]["text"]
    assert rows[1]["width"] == 480 and rows[1]["height"] == 400
    for row in rows:
        assert row["source_location"]["page"] == 1
        assert row["source_location"]["document_sha256"] == hashes["brief.pdf"]
        assert row["source_location"]["region_pdf_points"] == [0, 0, 240, 200]


@pytest.mark.parametrize(
    "selection",
    [{"page": 2}, {"page": True}, {"page": 1, "region_pdf_points": [-1, 0, 20, 20]}],
)
def test_pdf_rejects_wrong_page_or_region(tmp_path, selection):
    value = raw(tmp_path)
    value["files"][0]["selections"] = [selection]
    save(tmp_path / "raw.json", value)
    with pytest.raises((ContractError, ValueError, ValidationError)):
        _read_raw(tmp_path, "raw.json")


def model_adapter(tmp_path, role="audit", bad=False):
    script = tmp_path / f"{role}-adapter.py"
    script.write_text("""import json,sys
r=json.load(sys.stdin)
if sys.argv[1]=='audit':
 print(json.dumps(dict(schema_version='1.0',request_sha256=r['request_sha256'],questions=[dict(id='route-state',question='What should the indicator show while a parcel occupies the junction?',possible_consequence='A misleading indication could confuse a reviewer.',evidence_ids=['invented' if sys.argv[2]=='bad' else 'scene:inventory'],prim_paths=[],needed_evidence=['Indicator view during occupancy'])],limitations=['Synthetic adapter test, not a measured discovery result.'])))
else:
 s=next(s for s in r['sources'] if s['role']=='text')
 print(json.dumps(dict(request_sha256=r['request_sha256'],requirements=[dict(id='aisle',statement='Keep the service aisle clear.',source_ids=[s['id']],quotes=[dict(source_id=s['id'],quote='Keep the service aisle clear.')],route='unresolved',reason='Width and clearance height are not stated.',area='geometry',checks=[],visual=None)],limitations=['Synthetic interpretation control.'])))
""")
    config = tmp_path / f"{role}.json"
    save(
        config,
        dict(
            driver="json-cli",
            executable=sys.executable,
            args=[str(script), role, "bad" if bad else "good"],
            model="test-double",
            effort="none",
            timeout_seconds=3,
        ),
    )
    return config


def test_pdf_preparation_retains_original_and_citation(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    stage = scene(root)
    stage.GetRootLayer().Save()
    raw(root)
    out = tmp_path / "prepared"
    plan = prepare_scene(
        bundle_root=root,
        candidate="scene.usda",
        out=out,
        raw_brief="raw.json",
        interpreter_config=model_adapter(tmp_path, "interpreter"),
    )
    brief = strict_json(out / plan["bundle"] / plan["brief"])
    assert (
        brief["requirements"][0]["source_citations"][0]["source_location"]["page"] == 1
    )
    assert (out / plan["bundle"] / "__preparation__/original-00.pdf").read_bytes() == (
        root / "brief.pdf"
    ).read_bytes()
    assert plan["mapping_review"] == "pending"


@pytest.mark.parametrize("bad", [False, True])
def test_audit_questions_are_not_acceptance_or_findings(tmp_path, bad):
    root = tmp_path / "bundle"
    root.mkdir()
    stage = scene(root)
    stage.GetRootLayer().Save()
    raw(root)
    out = tmp_path / "audit"
    result = invoke(
        "audit",
        bundle_root=root,
        candidate="scene.usda",
        out=out,
        raw_brief="raw.json",
        audit_config=model_adapter(tmp_path, bad=bad),
    )
    assert result["exit_code"] == (4 if bad else 3), result
    assert result["data"]["acceptance_decision"] is None
    if not bad:
        assert result["data"]["question_count"] == 1
        assert result["metrics"]["model_calls"][0]["role"] == "audit"
        assert "not findings" in (out / "report.html").read_text()


def test_color_and_orientation_are_explicit(tmp_path):
    a = tmp_path / "linear.png"
    b = tmp_path / "srgb.png"
    Image.new("RGB", (1, 1), (128, 128, 128)).save(a)
    Image.new("RGB", (1, 1), (188, 188, 188)).save(b)
    _, x = linear_pixels(a, "linear-rgb8", "stored")
    _, y = linear_pixels(b, "srgb", "stored")
    assert abs(x[0][0] - y[0][0]) < 0.002
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    Image.new("RGB", (2, 1), (188, 188, 188)).save(
        b, icc_profile=profile, exif=Image.Exif()
    )
    with pytest.raises(MissingEvidence, match="embedded profile"):
        linear_pixels(b, "srgb", "stored")
    assert linear_pixels(b, "embedded-icc", "stored")[0] == (2, 1)
    image = Image.new("RGB", (2, 1))
    exif = Image.Exif()
    exif[274] = 6
    image.save(a, exif=exif)
    assert linear_pixels(a, "srgb", "exif")[0] == (1, 2)
    assert linear_pixels(a, "srgb", "stored")[0] == (2, 1)


def receipts(tmp_path):
    ctx = context(scene(tmp_path), tmp_path)
    (tmp_path / "camera.json").write_text('{"path":"orbit"}')
    (tmp_path / "native.json").write_text('{"synthetic":"native control"}')
    ctx.sources = ["receipt.json", "camera.json", "native.json"]
    viewer = dict(name="test-viewer", version="1.0", environment_sha256="a" * 64)
    camera = dict(
        path="camera.json",
        sha256=sha(tmp_path / "camera.json"),
        description="Synthetic path",
    )
    return ctx, viewer, camera


@pytest.mark.parametrize(
    "mode,expected", [("fast", "PASS"), ("slow", "FAIL"), ("callbacks", "UNKNOWN")]
)
@pytest.mark.parametrize("verified", [False, True])
def test_viewer_performance_requires_the_named_workload(
    tmp_path, mode, expected, verified
):
    ctx, viewer, camera = receipts(tmp_path)
    receipt = dict(
        schema_version="1.0",
        scene_sha256=ctx.artifact.artifact_set_sha256,
        viewer=viewer,
        measurement=(
            "draw_callback_duration"
            if mode == "callbacks"
            else "rendered_frame_duration"
        ),
        resolution=[1280, 720],
        camera_path=camera,
        warmup_seconds=5,
        frame_seconds=[0.01 if mode != "slow" else 0.22] * 100,
        method="Synthetic timing control",
        producer="pytest",
        limitations=["Not a real viewer measurement"],
    )
    save(tmp_path / "receipt.json", receipt)
    params = dict(
        receipt="receipt.json",
        viewer=viewer,
        resolution=[1280, 720],
        camera_path_sha256=camera["sha256"],
        min_frames=60,
        min_warmup_seconds=2,
        minimum_median_fps=30,
        maximum_p95_frame_seconds=0.05,
    )
    if verified:
        params["verification"] = dict(
            receipt_sha256=sha(tmp_path / "receipt.json"),
            basis="Synthetic caller-verified timing fixture",
        )
    assert performance(ctx, params).status == (expected if verified else "UNKNOWN")
    receipt["scene_sha256"] = "0" * 64
    save(tmp_path / "receipt.json", receipt)
    # A new invocation re-admits the new receipt; mutating an existing context
    # correctly triggers the stronger input-integrity error first.
    from scene_acceptance.artifact import EvidenceBundle

    ctx.bundle = EvidenceBundle(tmp_path, [])
    with pytest.raises(MissingEvidence, match="another scene"):
        performance(ctx, params)


@pytest.mark.parametrize(
    "state,expected", [("PASS", "PASS"), ("FAIL", "FAIL"), ("SKIPPED", "UNKNOWN")]
)
@pytest.mark.parametrize("verified", [False, True])
def test_external_engine_cannot_hide_skipped_runtime_test(
    tmp_path, state, expected, verified
):
    ctx, engine, _ = receipts(tmp_path)
    save(tmp_path / "native.json", dict(status=state))
    receipt = dict(
        schema_version="1.0",
        scene_sha256=ctx.artifact.artifact_set_sha256,
        engine=engine,
        provider="simready",
        profile_id="test-profile",
        profile_sha256="b" * 64,
        execution_status="completed",
        tests=[
            dict(
                id="runtime-control",
                phase="runtime",
                status=state,
                reason="Synthetic engine control",
                evidence_paths=["native.json"],
            )
        ],
        attachments=[
            dict(
                path="native.json",
                sha256=sha(tmp_path / "native.json"),
                description="Synthetic report",
            )
        ],
        producer="pytest",
        limitations=["No real engine executed"],
    )
    save(tmp_path / "receipt.json", receipt)
    params = dict(
        receipt="receipt.json",
        engine=engine,
        provider="simready",
        profile_id="test-profile",
        profile_sha256="b" * 64,
        required_tests=[dict(id="runtime-control", phase="runtime")],
    )
    if verified:
        params["verification"] = dict(
            receipt_sha256=sha(tmp_path / "receipt.json"),
            basis="Synthetic caller-verified engine fixture",
            native_report="native.json",
            tests=[
                dict(
                    id="runtime-control",
                    phase="runtime",
                    status_pointer="/status",
                    status_mapping={
                        "PASS": "PASS",
                        "FAIL": "FAIL",
                        "SKIPPED": "SKIPPED",
                    },
                )
            ],
        )
    assert engine_tests(ctx, params).status == (expected if verified else "UNKNOWN")


def test_native_worker_runs_and_kills_timeout(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    stage = scene(root)
    stage.GetRootLayer().Save()
    result = invoke_isolated(
        "check",
        bundle_root=root,
        candidate="scene.usda",
        out=tmp_path / "run",
        wall_seconds=20,
    )
    assert result["exit_code"] == 0, result
    assert result["isolation"]["limit_reason"] is None
    timed = supervise(
        [sys.executable, "-c", "import time;time.sleep(10)"],
        wall_seconds=0.15,
        memory_mib=512,
        cpu_seconds=5,
        max_output_bytes=1024,
    )
    assert timed["limit_reason"] == "wall_time_limit" and timed["elapsed_seconds"] < 5


def test_native_supervisor_enforces_memory_and_output():
    memory = supervise(
        [sys.executable, "-c", "import time;x=bytearray(120*1024*1024);time.sleep(10)"],
        wall_seconds=5,
        memory_mib=80,
        cpu_seconds=5,
        max_output_bytes=1024,
    )
    assert memory["limit_reason"] == "resident_memory_limit"
    output = supervise(
        [sys.executable, "-c", 'print("x"*100000)'],
        wall_seconds=5,
        memory_mib=512,
        cpu_seconds=5,
        max_output_bytes=1024,
    )
    assert output["limit_reason"] == "output_limit"


def test_isolated_execution_honors_cancel_and_invalid_limits(tmp_path):
    cancel = tmp_path / "cancel"
    cancel.touch()
    result = invoke_isolated("capabilities", cancel_file=str(cancel))
    assert result["status"] == "cancelled" and result["exit_code"] == 4
    result = invoke_isolated("capabilities", wall_seconds=-1)
    assert result["exit_code"] == 4 and result["errors"][0]["code"] == "ValueError"
