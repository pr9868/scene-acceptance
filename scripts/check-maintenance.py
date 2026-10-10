"""Check current metadata and guide links without changing files or using the network."""

import json
from pathlib import Path
import re
import tomllib
from urllib.parse import unquote

from scene_acceptance import __version__
from scene_acceptance.application_schemas import SCHEMAS
from scene_acceptance.packs import default_registry, EXAMPLE_PACKS
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def check():
    errors = []
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    if project["version"] != __version__:
        errors.append("Installed runtime and pyproject versions differ")
    locked = {}
    for name in ("requirements-test.lock", "requirements-articles.txt"):
        for line in (ROOT / name).read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                requirement = Requirement(line)
                locked[requirement.name.lower()] = requirement
    requirements = project["dependencies"] + [
        r for group in project["optional-dependencies"].values() for r in group
    ]
    for text in requirements:
        requirement = Requirement(text)
        lock = locked.get(requirement.name.lower())
        if lock is None or lock.specifier != requirement.specifier:
            errors.append("Dependency lock mismatch: " + text)
    package = ROOT / "src/scene_acceptance"
    for name, schema in SCHEMAS.items():
        if (
            json.loads((package / "schemas" / (name + ".schema.json")).read_text())
            != schema
        ):
            errors.append("Stale public schema: " + name)
    catalog = json.loads((package / "profiles/test-catalog.json").read_text())
    expected = dict(pack_versions={}, configurable_checks=[], example_checks=[])
    for pack in default_registry(include_examples=True).catalog():
        expected["pack_versions"][pack["id"]] = pack["version"]
        for name, spec in pack["checks"].items():
            key = (
                "example_checks"
                if pack["id"] in EXAMPLE_PACKS
                else "configurable_checks"
            )
            expected[key].append(
                dict(id=pack["id"] + "." + name, pack=pack["id"], check=name, **spec)
            )
    for key, value in expected.items():
        if catalog[key] != value:
            errors.append("Stale test catalog: " + key)
    docs = [
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
        *(ROOT / "docs").glob("*.md"),
        *(package / "skills").rglob("*.md"),
    ]
    for path in docs:
        for link in re.findall(r"\]\(([^\s)]+)(?:\s+[^)]*)?\)", path.read_text()):
            target = unquote(link.strip("<>").split("#")[0])
            if not target or re.match(r"[a-zA-Z]+:", target) or target.startswith("/"):
                continue
            if not (path.parent / target).exists():
                errors.append(f"Broken local link: {path.relative_to(ROOT)} -> {link}")
    result = dict(
        version=__version__,
        guides_checked=len(docs),
        schemas_checked=len(SCHEMAS),
        errors=errors,
    )
    print(json.dumps(result, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(check())
