"""Reusable delivery checks with automatic discovery and explicit measured coverage."""

from scene_acceptance.usd_composition import prims as composed_prims
from pathlib import Path
import math
import warnings
from pxr import Usd, UsdGeom
from .packs import Pack, CheckSpec, Outcome
from .builtin_packs import obj
from .coverage import assessment
from .motion_timing import read_clock
from .model import MissingEvidence

IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".exr",
    ".hdr",
    ".dds",
    ".ktx",
    ".ktx2",
    ".tga",
}


def finish(rows, unit, scope, reason):
    statuses = {r["status"] for r in rows}
    status = (
        "ERROR"
        if "ERROR" in statuses
        else (
            "FAIL"
            if "FAIL" in statuses
            else "UNKNOWN" if "UNKNOWN" in statuses or "SKIPPED" in statuses else "PASS"
        )
    )
    return Outcome(status, reason, {"assessment": assessment(unit, rows, scope)})


def files(ctx, params):
    rows = []
    for path, digest in sorted(ctx.artifact.assets.items()):
        runtime_library = path in ctx.artifact.runtime_assets
        defer_library = (
            runtime_library and params.get("runtime_libraries", "unknown") == "unknown"
        )
        from .runtime_dependencies import evidence_for

        runtime_evidence = (
            evidence_for(ctx, path) if defer_library and not digest else None
        )
        status = (
            "PASS"
            if digest or runtime_evidence
            else "UNKNOWN" if defer_library else "FAIL"
        )
        reason = (
            "File present"
            if digest
            else (
                "Caller-attested dependency availability in the pinned runtime"
                if runtime_evidence
                else (
                    "MDL library requires a bundled dependency or target-runtime resolver evidence"
                    if defer_library
                    else "Referenced local file is missing under the selected delivery policy"
                )
            )
        )
        rows.append(
            dict(
                subject=str(path.relative_to(ctx.bundle.root)),
                status=status,
                sha256=digest,
                reason=reason,
                **(
                    {"runtime_dependency_evidence": runtime_evidence}
                    if runtime_evidence
                    else {}
                ),
                dependency_role="mdl_source_asset" if runtime_library else "local_file",
            )
        )
    return finish(
        rows,
        "unique external files",
        "Local dependency closure. Renderer-provided libraries must be resolved in the target runtime.",
        (
            "Checked external file availability."
            if rows
            else "No external asset files in the admitted closure."
        ),
    )


def textures(ctx, params):
    from PIL import Image, UnidentifiedImageError

    rows = []
    for p, digest in sorted(ctx.artifact.assets.items()):
        if p.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        row = dict(
            subject=str(p.relative_to(ctx.bundle.root)), sha256=digest, status="UNKNOWN"
        )
        rows.append(row)
        if not digest:
            row.update(status="FAIL", reason="Referenced image file is missing")
            continue
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            row.update(
                reason="This decoder supports single-frame PNG/JPEG; another decoder is required"
            )
            continue
        if p.stat().st_size > params["max_bytes"]:
            row.update(reason="Decoding byte budget exceeded")
            continue
        try:
            from .image_policy import load_image

            im = load_image(
                p, max_bytes=params["max_bytes"], max_pixels=params["max_pixels"]
            )
            row.update(format=im.format, width=im.width, height=im.height, frames=1)
            row.update(status="PASS", reason="Verified and fully decoded")
        except MissingEvidence as exc:
            row.update(reason=str(exc))
        except (Image.DecompressionBombWarning, Image.DecompressionBombError):
            row.update(reason="Decoder safety budget exceeded")
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            row.update(
                status="FAIL",
                reason="Image cannot be fully decoded: " + type(exc).__name__,
            )
    result = finish(
        rows,
        "unique image files",
        "Image-suffixed dependencies in the admitted closure, irrespective of shader type; unsupported formats remain unknown. No semantic, UV or render comparison.",
        (
            "Checked discovered image dependencies."
            if rows
            else "No recognized image-file dependencies discovered."
        ),
    )
    from importlib.metadata import version

    result.evidence["decoder_version"] = version("Pillow")
    return result


def authored_motion(ctx, params):
    stage = ctx.artifact.stage
    candidates = []
    for p in composed_prims(stage):
        if p.IsA(UsdGeom.Xformable) and any(
            op.GetAttr().GetNumTimeSamples()
            for op in UsdGeom.Xformable(p).GetOrderedXformOps()
        ):
            candidates.append(p)
    if not candidates:
        return finish(
            [],
            "animated transform prims",
            "Authored animation only; does not cover runtime-driven motion.",
            "No time-sampled transform operations discovered.",
        )
    try:
        clock = read_clock(stage)
    except Exception as exc:
        return finish(
            [
                dict(subject=str(p.GetPath()), status="UNKNOWN", reason=str(exc))
                for p in candidates
            ],
            "animated transform prims",
            "Finite authored samples; no motion-intent acceptance.",
            "An authored valid clock/range is needed.",
        )
    rows = []
    remaining = params["max_total_samples"]
    start, end = clock["start_time_code"], clock["end_time_code"]
    for p in candidates:
        keys = set()
        q = p
        while q and not q.IsPseudoRoot():
            if q.IsA(UsdGeom.Xformable):
                xf = UsdGeom.Xformable(q)
                for op in xf.GetOrderedXformOps():
                    keys.update(op.GetAttr().GetTimeSamples())
                if xf.GetResetXformStack():
                    break
            q = q.GetParent()
        # Playback bounds do not forbid other authored samples. Check their
        # finiteness too, but use only the playback interval for midpoint probes.
        interval = {start, end} | {t for t in keys if start <= t <= end}
        ordered = sorted(interval)
        interval.update(a + (b - a) / 2 for a, b in zip(ordered, ordered[1:]))
        times = keys | interval
        row = dict(
            subject=str(p.GetPath()),
            status="UNKNOWN",
            samples_requested=len(times),
            authored_keys_outside_playback=sorted(
                t for t in keys if t < start or t > end
            ),
            interval_sample_time_codes=sorted(interval),
        )
        rows.append(row)
        if any(not math.isfinite(t) for t in times):
            row.update(
                status="FAIL",
                reason="Non-finite authored sample time",
                samples_checked=0,
            )
            continue
        if len(times) > params["max_samples_per_prim"] or len(times) > remaining:
            row["reason"] = "Transform sample budget exceeded"
            continue
        remaining -= len(times)
        bad = []
        for t in sorted(times):
            matrix = UsdGeom.XformCache(Usd.TimeCode(t)).GetLocalToWorldTransform(p)
            if not all(math.isfinite(v) for r in matrix for v in r):
                bad.append(t)
        row.update(
            status="FAIL" if bad else "PASS",
            samples_checked=len(times),
            sample_time_codes=sorted(times),
            failed_time_codes=bad,
            reason=(
                "Non-finite world transform"
                if bad
                else "World matrices finite at authored keys and playback boundaries/midpoints"
            ),
        )
    result = finish(
        rows,
        "animated transform prims",
        "Authored local motion candidates, composed with ancestors. Finite authored keys (including keys outside playback), playback boundaries and interval midpoints; no target, connectedness, speed, collisions, simulation or continuous guarantee.",
        "Checked authored motion data and sample coverage.",
    )
    result.evidence["clock"] = clock
    return result


def audit_pack():
    return Pack(
        "scene.audit",
        "1.2.0",
        "Reusable file, image and authored-motion diagnostics",
        {
            "files": CheckSpec(
                files,
                obj(
                    {"runtime_libraries": {"enum": ["unknown", "require_local"]}},
                    required=[],
                ),
                "Check discovered external files",
                "Admitted external dependencies; missing MDL source assets are unknown unless local delivery is explicitly required",
            ),
            "textures": CheckSpec(
                textures,
                obj(
                    {
                        "max_bytes": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 33554432,
                        },
                        "max_pixels": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 16000000,
                        },
                    }
                ),
                "Decode discovered PNG/JPEG dependencies",
                "Discovered image files; other formats remain unknown",
            ),
            "authored_motion": CheckSpec(
                authored_motion,
                obj(
                    {
                        "max_samples_per_prim": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 4097,
                        },
                        "max_total_samples": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100000,
                        },
                    }
                ),
                "Check finite authored world transforms",
                "Explicitly bounded samples; no motion intent",
            ),
        },
        tuple(
            str(Path(__file__).with_name(n))
            for n in ("scene_audit.py", "image_policy.py", "usd_composition.py")
        ),
        ("usd-core",),
    )
