"""Read-only evaluator CLI. Reports go to a new directory outside the input bundle."""

from pathlib import Path
import argparse, json, sys
from .engine import evaluate
from .report import write_report

EXIT_CODES = {
    "ACCEPT_FOR_USE": 0,
    "REJECT": 2,
    "INSUFFICIENT_EVIDENCE": 3,
    "EVALUATION_ERROR": 4,
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a saved USD layout against explicit acceptance requirements."
    )
    parser.add_argument("--contract", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--baseline")
    parser.add_argument("--claims")
    parser.add_argument("--receipt")
    parser.add_argument("--expected-contract-sha256")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--allow-pack",
        action="append",
        default=[],
        help="Explicitly load an installed scene_acceptance.packs entry point",
    )
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    bundle = Path(args.bundle_root).resolve()
    if out.exists() or out.is_relative_to(bundle) or bundle.is_relative_to(out):
        parser.error(
            "--out must be a new directory outside the input bundle and its ancestors"
        )
    report = evaluate(
        args.contract,
        args.candidate,
        bundle_root=args.bundle_root,
        baseline_path=args.baseline,
        claims_path=args.claims,
        receipt_path=args.receipt,
        expected_contract_sha256=args.expected_contract_sha256,
        approved_packs=args.allow_pack,
    )
    try:
        write_report(report, out)
    except (OSError, ValueError) as exc:
        print("Cannot save a complete report: " + str(exc), file=sys.stderr)
        return 4
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "complete": report["complete"],
                "report": str(out / "report.html"),
            }
        )
    )
    return EXIT_CODES[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
