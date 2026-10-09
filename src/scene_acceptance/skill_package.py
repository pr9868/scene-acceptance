"""Discover/export bundled adopter skills without enabling or installing them."""

import argparse
from importlib.resources import files
import json
from pathlib import Path
from .model import ContractError, sha
from .review_context import save

NAMES = ("scene-harness-handoff", "scene-harness-judge-authoring")


def export_skills(destination):
    out = Path(destination).resolve()
    if out.exists():
        raise ContractError(
            "Skill export destination must be new; edit an exported copy to customize"
        )
    out.mkdir(parents=True)

    def copy_tree(source, target):
        target.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            if item.is_dir():
                copy_tree(item, target / item.name)
            else:
                (target / item.name).write_bytes(item.read_bytes())

    for name in NAMES:
        copy_tree(files("scene_acceptance").joinpath("skills", name), out / name)
    manifest = {
        "schema_version": "1.0",
        "skills": list(NAMES),
        "files": {
            str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()
        },
        "note": "Exported only. Caller chooses skill installation and activation. Customizations should have their own version and tests.",
    }
    save(out / "manifest.json", manifest)
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(
        description="List or export adopter skills; never automatically install"
    )
    p.add_argument("--out")
    a = p.parse_args(argv)
    try:
        result = (
            export_skills(a.out)
            if a.out
            else {"skills": list(NAMES), "installed": False}
        )
    except Exception as e:
        print(str(e))
        return 4
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
