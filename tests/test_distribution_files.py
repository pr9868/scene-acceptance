"""Missing or changed runtime assets must fail wheel verification."""

import hashlib
import importlib.util
from pathlib import Path
import zipfile
import pytest

spec = importlib.util.spec_from_file_location(
    "verify_distributions",
    Path(__file__).parents[1] / "scripts/verify-distributions.py",
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


@pytest.mark.parametrize("fault", [None, "missing", "changed", "extra"])
def test_wheel_contains_exact_reviewed_runtime(tmp_path, fault):
    content = b"reviewed skill or schema"
    manifest = dict(
        files={
            "src/scene_acceptance/skills/demo/SKILL.md": hashlib.sha256(
                content
            ).hexdigest()
        }
    )
    wheel = tmp_path / "control.whl"
    with zipfile.ZipFile(wheel, "w") as output:
        output.writestr("scene_acceptance-1.0.dist-info/METADATA", "generated")
        if fault != "missing":
            output.writestr(
                "scene_acceptance/skills/demo/SKILL.md",
                b"changed" if fault == "changed" else content,
            )
        if fault == "extra":
            output.writestr("scene_acceptance/local-config.json", "unreviewed")
    if fault:
        with pytest.raises(ValueError):
            verifier.verify_wheel(wheel, manifest)
    else:
        verifier.verify_wheel(wheel, manifest)
