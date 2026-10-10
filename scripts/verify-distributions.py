"""Verify an sdist retains exactly the reviewed manifest and generated metadata."""

from pathlib import Path
import argparse
import hashlib
import json
import tarfile
import zipfile


def verify(archive):
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        roots = {m.name.split("/")[0] for m in members}
        if len(roots) != 1:
            raise ValueError("Source archive must have one root")
        root = roots.pop()
        files = {}
        for entry in members:
            if entry.isdir():
                continue
            if not entry.isfile() or ".." in Path(entry.name).parts:
                raise ValueError("Unsupported archive member: " + entry.name)
            files[entry.name[len(root) + 1 :]] = source.extractfile(entry).read()
        manifest = json.loads(files["MANIFEST.json"])
        for name, digest in manifest["files"].items():
            if name not in files or hashlib.sha256(files[name]).hexdigest() != digest:
                raise ValueError(
                    "Missing or changed reviewed distribution file: " + name
                )
        extras = (
            set(files)
            - set(manifest["files"])
            - {"MANIFEST.json", "PKG-INFO", "setup.cfg"}
        )
        extras = {
            name
            for name in extras
            if not name.startswith("src/scene_acceptance.egg-info/")
        }
        if extras:
            raise ValueError("Unreviewed source files: " + ", ".join(sorted(extras)))
        print(
            json.dumps(
                {
                    "archive": Path(archive).name,
                    "reviewed_files": len(manifest["files"]),
                    "verified": True,
                }
            )
        )
        return manifest


def verify_wheel(archive, manifest):
    expected = {
        name.removeprefix("src/"): digest
        for name, digest in manifest["files"].items()
        if name.startswith("src/scene_acceptance/")
    }
    with zipfile.ZipFile(archive) as wheel:
        names = [name for name in wheel.namelist() if not name.endswith("/")]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate wheel member")
        actual = {name for name in names if ".dist-info/" not in name}
        if actual != expected.keys():
            raise ValueError("Wheel runtime file set differs from reviewed source")
        for name, digest in expected.items():
            if hashlib.sha256(wheel.read(name)).hexdigest() != digest:
                raise ValueError("Changed wheel runtime file: " + name)
    print(
        json.dumps(
            dict(archive=Path(archive).name, runtime_files=len(expected), verified=True)
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="+")
    archives = parser.parse_args().archive
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "MANIFEST.json").read_text()
    )
    for archive in archives:
        if not archive.endswith(".whl"):
            manifest = verify(archive)
    for archive in archives:
        if archive.endswith(".whl"):
            verify_wheel(archive, manifest)
