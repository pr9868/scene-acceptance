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


class UsageParser(argparse.ArgumentParser):
    """Reserve exit 2 for a completed scene rejection, never a malformed call."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(4, f"{self.prog}: error: {message}\n")


def main(argv=None):
    parser = UsageParser(
        description="Check a saved USD bundle. Runs general diagnostics by default; add --brief or --contract for explicit requirements."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--contract")
    selection.add_argument("--brief", help="Text/image brief manifest with explicit check mappings, relative to --bundle-root")
    parser.add_argument("--expected-brief-sha256", help="Optional caller pin for the brief manifest")
    selection.add_argument("--review-plan", help="Caller-owned declared-scope plan, relative to --review-root")
    selection.add_argument("--profile", choices=["usd-delivery-baseline"],
                           help="Select the shipped generic diagnostic baseline and discover local dependencies")
    parser.add_argument("--candidate")
    parser.add_argument("--bundle-root")
    parser.add_argument("--mode", choices=['checks','judge','both'], help="Explicit unified invocation; omit to preserve legacy report/stdout layout")
    parser.add_argument("--judge-config", help="Trusted caller model CLI configuration")
    parser.add_argument("--views", help="Hashed view manifest; image paths relative to its folder")
    parser.add_argument("--rubric", help="Optional versioned advisory rubric JSON")
    parser.add_argument("--judge-exposure", choices=['withheld','script-aware'], default='withheld')
    parser.add_argument("--capabilities", action='store_true', help="Print versioned invocation capabilities without evaluating a scene")
    parser.add_argument("--list-tests", action='store_true', help="Print every baseline rule, configurable check and advisory rubric")
    parser.add_argument("--baseline")
    parser.add_argument("--claims")
    parser.add_argument("--receipt")
    parser.add_argument("--expected-contract-sha256")
    parser.add_argument("--review-root")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--decisions", help="Producer decision JSON relative to bundle root")
    parser.add_argument("--reviews", help="Caller-selected reviewer JSON relative to review root")
    parser.add_argument(
        "--max-dependency-files",
        type=int,
        default=64,
        help="Caller resource budget per USD dependency closure, including its root (1-1024; default: 64)",
    )
    parser.add_argument("--out")
    parser.add_argument(
        "--allow-pack",
        action="append",
        default=[],
        help="Explicitly load an installed scene_acceptance.packs entry point",
    )
    args = parser.parse_args(argv)
    if args.capabilities or args.list_tests:
        if args.capabilities and args.list_tests: parser.error('Select capabilities or test catalog')
        if any(v is not None for v in (args.bundle_root,args.candidate,args.out,args.mode,args.brief,args.contract,args.review_plan,args.profile,args.judge_config,args.views,args.rubric,args.expected_brief_sha256,args.baseline,args.claims,args.receipt,args.expected_contract_sha256,args.review_root,args.plan_sha256,args.decisions,args.reviews)) or args.allow_pack or args.judge_exposure!='withheld' or args.max_dependency_files!=64:
            parser.error('Discovery cannot be combined with an evaluation')
        from .test_catalog import capabilities, test_catalog
        print(json.dumps(capabilities() if args.capabilities else test_catalog(),indent=2));return 0
    if not args.bundle_root or not args.out: parser.error('--bundle-root and --out are required')
    selections = (args.contract, args.brief, args.review_plan, args.profile)
    if any(value == "" for value in selections):
        parser.error("Brief, contract and review-plan paths must not be empty")
    implicit_profile = all(value is None for value in selections)
    if implicit_profile:
        args.profile = "usd-delivery-baseline"
    if not 1 <= args.max_dependency_files <= 1024:
        parser.error("--max-dependency-files must be from 1 to 1024")
    if args.mode:
        if args.mode=='judge' and not implicit_profile and args.profile:
            parser.error('Judge-only mode cannot select a scripted profile')
        if any(v is not None for v in (args.contract,args.review_plan,args.baseline,args.claims,args.receipt,args.expected_contract_sha256,args.review_root,args.plan_sha256,args.decisions,args.reviews)):
            parser.error('Unified modes accept a scene and optional brief; advanced contract/review-plan calls retain their existing interface without --mode')
        from .evaluation import evaluate_scene
        try:
            result=evaluate_scene(bundle_root=args.bundle_root,candidate=args.candidate,out=args.out,mode=args.mode,
                brief=args.brief,expected_brief_sha256=args.expected_brief_sha256,judge_config=args.judge_config,
                views=args.views,rubric=args.rubric,judge_exposure=args.judge_exposure,
                approved_packs=args.allow_pack,max_dependency_files=args.max_dependency_files)
        except Exception as exc:
            print('Cannot start evaluation: '+str(exc),file=sys.stderr);return 4
        print(json.dumps({'schema_version':'1.0','mode':result['mode'],'execution_status':result['execution_status'],
                          'decision':result['decision'],'result':str(Path(args.out)/'evaluation.json'),
                          'report':str(Path(args.out)/'report.html')}))
        return result['exit_code']
    if any(v is not None for v in (args.judge_config,args.views,args.rubric)) or args.judge_exposure!='withheld':
        parser.error('Model review options require explicit --mode judge or --mode both')
    if args.brief:
        if not args.candidate: parser.error('--brief requires --candidate')
        if any((args.baseline,args.claims,args.receipt,args.expected_contract_sha256,args.review_root,args.plan_sha256,args.decisions,args.reviews)):
            parser.error('Brief mode owns its compiled contract and review plan; overrides are not allowed')
        from .briefs import evaluate_brief
        try:
            report=evaluate_brief(args.brief,args.candidate,bundle_root=args.bundle_root,out=args.out,
                                  expected_sha256=args.expected_brief_sha256,approved_packs=args.allow_pack,
                                  max_dependency_files=args.max_dependency_files)
        except Exception as exc:
            print('Cannot complete brief assessment: '+str(exc),file=sys.stderr);return 4
        print(json.dumps({'core_verdict':report['core_verdict'],'assessment_verdict':report['assessment_verdict'],
                          'report':str(Path(args.out)/'report/report.html')}))
        return {'ACCEPT_FOR_DECLARED_SCOPE':0,'REJECT':2,'NEEDS_REVIEW':3,'EVALUATION_ERROR':4}.get(report['assessment_verdict'],4)
    if args.expected_brief_sha256: parser.error('--expected-brief-sha256 requires --brief')
    if args.review_plan:
        if not args.review_root or not args.plan_sha256:
            parser.error('--review-plan requires --review-root and --plan-sha256')
        if any((args.candidate,args.baseline,args.claims,args.receipt,args.expected_contract_sha256)):
            parser.error('The pinned review plan owns candidate, baseline and contract; overrides are not allowed')
        from .review.__main__ import main as review_main
        review_args = [args.review_plan, '--review-root', args.review_root, '--bundle-root', args.bundle_root,
                       '--plan-sha256', args.plan_sha256, '--out', args.out,
                       '--max-dependency-files', str(args.max_dependency_files)]
        for flag, value in (('--decisions', args.decisions), ('--reviews', args.reviews)):
            if value: review_args += [flag, value]
        for pack in args.allow_pack: review_args += ['--approve-pack', pack]
        # Preserve check-3d exit meanings across modes; assess-3d keeps its historical codes.
        try:
            review_exit = review_main(review_args)
        except SystemExit as exc:
            # The delegated legacy parser still uses argparse's usage exit 2.
            raise SystemExit(4 if exc.code else 0) from None
        return {0: 0, 1: 2, 2: 3, 3: 4}[review_exit]
    if not args.candidate:
        parser.error('--candidate is required for contract or baseline mode')
    if any((args.review_root,args.plan_sha256,args.decisions,args.reviews)):
        parser.error('Review arguments require --review-plan')
    out = Path(args.out).resolve()
    bundle = Path(args.bundle_root).resolve()
    if out.exists() or out.is_relative_to(bundle) or bundle.is_relative_to(out):
        parser.error(
            "--out must be a new directory outside the input bundle and its ancestors"
        )
    if args.profile:
        if any((args.baseline,args.claims,args.receipt,args.expected_contract_sha256,args.allow_pack)):
            parser.error("Use --contract for task-specific overrides or external providers")
        from .profiles import evaluate_baseline
        report = evaluate_baseline(bundle,args.candidate,max_dependency_files=args.max_dependency_files,implicit=implicit_profile)
    else:
        report = evaluate(
            args.contract,
            args.candidate,
            bundle_root=args.bundle_root,
            baseline_path=args.baseline,
            claims_path=args.claims,
            receipt_path=args.receipt,
            expected_contract_sha256=args.expected_contract_sha256,
            approved_packs=args.allow_pack,
            max_dependency_files=args.max_dependency_files,
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
