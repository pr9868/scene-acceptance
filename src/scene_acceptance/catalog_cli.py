"""Describe available packs without automatically importing installed extensions."""

import argparse
import json
from .packs import default_registry, installed_pack_names


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect pack schemas, coverage, versions and dependencies"
    )
    parser.add_argument("--allow-pack", action="append", default=[])
    parser.add_argument("--upstream", choices=["openusd", "nvidia"])
    args = parser.parse_args(argv)
    if args.upstream == "openusd":
        from pxr import UsdValidation, Usd

        r = UsdValidation.ValidationRegistry()
        data = {
            "provider": "OpenUSD",
            "version": list(Usd.GetVersion()),
            "validators": sorted(m.name for m in r.GetAllValidatorMetadata()),
        }
    elif args.upstream == "nvidia":
        import contextlib
        import sys

        with contextlib.redirect_stdout(sys.stderr):
            import usd_validation_nvidia as nv
        from importlib.metadata import version

        r = nv.CategoryRuleRegistry()
        data = {
            "provider": "NVIDIA Asset Validator",
            "version": version("usd-validation-nvidia"),
            "rules": {
                c: sorted(x.__name__ for x in r.get_rules(c)) for c in r.categories
            },
        }
    else:
        data = {
            "pack_api": "1.0",
            "packs": default_registry(args.allow_pack).catalog(),
            "installed_entry_points_not_automatically_loaded": installed_pack_names(),
        }
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
