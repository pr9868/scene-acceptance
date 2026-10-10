"""Explicit proposals for upgrading known pack pins; evaluation never migrates them."""

from copy import deepcopy
import argparse
import json
from pathlib import Path
import shutil
from .model import ContractError, digest_json, sha, strict_json

# Only reviewed historical revisions are eligible. Unknown future versions and
# digest pins remain untouched, so negative controls cannot become valid by migration.
PREVIOUS_VERSIONS = {
    "openusd": ("1.0.0",),
    "materials": ("1.0.0", "1.1.0"),
    "motion": ("1.0.0",),
    "nvidia.asset-validator": ("1.0.0",),
    "motion.timing": ("1.0.0",),
    "scene.audit": ("1.0.0", "1.1.0"),
    "brief.measurements": ("1.0.0", "1.1.0", "1.2.0", "1.3.0"),
    "geometry.clearance": ("1.0.0", "1.0.1"),
    "process.connections": ("1.0.0",),
    "textures.decode": ("0.1.0", "0.2.0"),
    "brief.four-job": ("1.0.0",),
    "physics.incline-worker": ("0.1.0",),
}


def propose_upgrade(contract, registry=None):
    """Return an unapproved version-only proposal and an inspectable change record.

    No tolerance, requirement, implementation digest pin or unknown version is
    changed. An existing digest pin may still block execution after this proposal;
    replacing that approval is an explicit, separate caller decision.
    """
    from .packs import default_registry

    if not isinstance(contract, dict) or contract.get("schema_version") != "2.0":
        raise ContractError("Pack upgrade requires a version 2 contract")
    if not isinstance(contract.get("packs"), dict) or any(
        not isinstance(pin, dict) or not isinstance(pin.get("version"), str)
        for pin in contract["packs"].values()
    ):
        raise ContractError("Pack upgrade requires well-formed pack declarations")
    registry = registry or default_registry(selected=contract["packs"])
    upgraded = deepcopy(contract)
    changes = []
    for name, pin in upgraded.get("packs", {}).items():
        if pin.get("version") not in PREVIOUS_VERSIONS.get(name, ()):
            continue
        current = registry.get(name).version
        if pin["version"] != current:
            changes.append(
                dict(
                    pack=name,
                    before=pin["version"],
                    after=current,
                    implementation_pin_preserved="sha256" in pin,
                )
            )
            pin["version"] = current
    return upgraded, dict(
        schema_version="1.0",
        kind="pack-version-upgrade-proposal",
        original_sha256=digest_json(contract),
        proposed_sha256=digest_json(upgraded),
        changes=changes,
        requires_review=bool(changes),
        limitation="Version pins only. This proposal does not approve changed check behavior or replace implementation pins.",
    )


def upgrade_copied_contracts(bundle):
    """Upgrade contracts in a caller-owned copy; retain a record for every proposal."""
    root = Path(bundle)
    records = []
    for path in sorted(root.rglob("*.json")):
        if path.name == "contract-upgrades.json":
            continue
        try:
            value = strict_json(path)
        except (ValueError, ContractError):
            continue  # Malformed retained inputs must reach the evaluator unchanged.
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != "2.0"
            or "packs" not in value
        ):
            continue
        try:
            proposal, record = propose_upgrade(value)
        except ContractError:
            continue  # Preserve malformed control contracts for the evaluator.
        if record["changes"]:
            record["path"] = str(path.relative_to(root))
            record["original_file_sha256"] = sha(path)
            path.write_text(json.dumps(proposal, indent=2) + "\n")
            records.append(record)
    if records:
        (root / "contract-upgrades.json").write_text(
            json.dumps(records, indent=2) + "\n"
        )
    return records


def copy_replay_bundle(source, target):
    """Copy retained controls before proposing current pins; never edit the original."""
    source, target = Path(source).resolve(), Path(target).resolve()
    if (
        source == target
        or target.is_relative_to(source)
        or source.is_relative_to(target)
    ):
        raise ContractError("Replay copy must be separate from its source")
    if any(p.is_symlink() for p in source.rglob("*")):
        raise ContractError("Replay inputs must not contain symlinks")
    shutil.copytree(source, target)
    upgrade_copied_contracts(target)
    return target


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(4, "Usage error: " + message + "\n")

    parser = Parser(
        description="Propose known pack-version upgrades without approving them"
    )
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--contract", type=Path)
    inputs.add_argument(
        "--bundle-root",
        type=Path,
        help="Copy a retained bundle before proposing version pins",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="New proposal directory"
    )
    args = parser.parse_args(argv)
    if args.bundle_root is not None:
        bundle = copy_replay_bundle(args.bundle_root, args.out)
        print(
            json.dumps(
                {
                    "copied_bundle": str(bundle),
                    "review_record": "contract-upgrades.json",
                    "approval": "Not granted by this command",
                },
                indent=2,
            )
        )
        return 0
    proposal, record = propose_upgrade(strict_json(args.contract))
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "contract.json").write_text(json.dumps(proposal, indent=2) + "\n")
    (args.out / "upgrade.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ContractError) as exc:
        import sys

        print("Upgrade proposal failed: " + str(exc), file=sys.stderr)
        raise SystemExit(4)
