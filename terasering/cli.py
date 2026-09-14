"""Command line interface.

    teras run problems/1234B solution.cpp
    teras run problems/1234B solution.cpp --cf-ac --all-tests
    teras gen problems/1234B model.cpp
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .cf import ClaimResult, CodeforcesClient
from .config import JudgeConfig
from .errors import TeraseringError
from .generator import GeneratedCase, generate
from .judge import Judge
from .loader import load_problem
from .models import TOTAL_POINTS, Limits, Problem, SubmissionOutcome
from .scoring import diagnose, effective_score


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except TeraseringError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # Raised when output is piped into `head` or `less` and then closed.
        sys.stdout.close()
        return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teras", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="score one source file against a problem")
    run.add_argument("problem", type=Path, help="problem directory, e.g. problems/1234B")
    run.add_argument("source", type=Path, help="submitted source file")
    run.add_argument(
        "--cf-ac",
        action="store_true",
        help="assert the Codeforces verdict instead of checking it",
    )
    run.add_argument(
        "--cf-handle",
        metavar="HANDLE",
        help="look up this handle's accepted submission for the problem",
    )
    run.add_argument(
        "--cf-submission",
        type=int,
        metavar="ID",
        help="check one specific submission instead of searching for it",
    )
    run.add_argument(
        "--all-tests",
        action="store_true",
        help="run every test case even after a subtask has failed",
    )
    run.add_argument(
        "--time-limit",
        type=int,
        metavar="MS",
        help="override the time limit from meta.toml",
    )
    run.add_argument(
        "--time-factor",
        type=float,
        default=1.0,
        metavar="X",
        help="multiply time limits to suit this machine's speed",
    )
    run.add_argument(
        "--show-warnings",
        action="store_true",
        help="print compiler warnings",
    )
    run.set_defaults(handler=_run)

    gen = subparsers.add_parser(
        "gen", help="generate answer keys from a model solution"
    )
    gen.add_argument("problem", type=Path, help="problem directory")
    gen.add_argument("model", type=Path, help="model solution source file")
    gen.add_argument(
        "--force",
        action="store_true",
        help="overwrite answer keys that already exist",
    )
    gen.add_argument(
        "--subtask",
        metavar="LABEL",
        help="restrict generation to one subtask",
    )
    gen.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen without writing anything",
    )
    gen.add_argument(
        "--time-factor",
        type=float,
        default=1.0,
        metavar="X",
        help="multiply time limits to suit this machine's speed",
    )
    gen.set_defaults(handler=_gen)

    return parser


def _run(args: argparse.Namespace) -> int:
    problem = load_problem(args.problem)
    judge = Judge(config=JudgeConfig(time_limit_factor=args.time_factor))

    override = None
    if args.time_limit is not None:
        override = Limits(args.time_limit, problem.limits.memory_mb)

    claim = _check_claim(problem, args)
    cf_accepted = claim.accepted if claim else args.cf_ac

    outcome = judge.evaluate(
        problem,
        args.source.read_text(),
        stop_on_failure=not args.all_tests,
        limits=override,
    )

    _print_header(problem, args.time_limit)
    if not outcome.compiled:
        print("COMPILE ERROR\n")
        print(outcome.compile_error)
        return 1

    if outcome.compile_diagnostics and args.show_warnings:
        print(f"compiler warnings:\n{outcome.compile_diagnostics}\n")

    _print_subtasks(outcome)
    _print_summary(outcome, cf_accepted, claim)
    return 0


def _check_claim(problem: Problem, args: argparse.Namespace) -> ClaimResult | None:
    """Resolve the Codeforces side of the score, if a handle was given."""
    if not args.cf_handle:
        if args.cf_submission is not None:
            raise TeraseringError("--cf-submission also needs --cf-handle")
        return None

    client = CodeforcesClient()
    if args.cf_submission is None:
        # No id given, so find the accepted submission ourselves.
        return client.verify_latest(args.cf_handle, problem)
    return client.verify(args.cf_handle, args.cf_submission, problem)


def _gen(args: argparse.Namespace) -> int:
    # The keys are what this command produces, so their absence is expected.
    problem = load_problem(args.problem, require_answers=False)
    cases = generate(
        problem,
        args.model.read_text(),
        config=JudgeConfig(time_limit_factor=args.time_factor),
        force=args.force,
        subtask=args.subtask,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("dry run: nothing was written\n")

    for case in cases:
        print(f"  {_gen_mark(case)}  {case.test.expected_path}")
    print()
    _print_gen_summary(cases)

    # A non-zero exit lets this be chained in a script.
    return 1 if any(case.blocked for case in cases) else 0


def _gen_mark(case: GeneratedCase) -> str:
    if case.written:
        return "written"
    if case.blocked:
        return "BLOCKED"
    return "kept   "


def _print_gen_summary(cases: list[GeneratedCase]) -> None:
    written = sum(case.written for case in cases)
    blocked = [case for case in cases if case.blocked]
    kept = len(cases) - written - len(blocked)

    print(f"{written} written, {kept} kept, {len(blocked)} blocked")
    if kept:
        print("re-run with --force to overwrite the keys that were kept")
    for case in blocked:
        print(f"  {case.test.name}: {case.reason}")


def _print_header(problem: Problem, time_limit_override: int | None) -> None:
    time_limit = time_limit_override or problem.limits.time_ms
    print(f"problem    : {problem.id}")
    if problem.cf_url:
        print(f"codeforces : {problem.cf_url}")
    print(f"limits     : {time_limit} ms, {problem.limits.memory_mb} MB")
    print()


def _print_subtasks(outcome: SubmissionOutcome) -> None:
    for subtask in outcome.subtasks:
        status = "PASS" if subtask.passed else "FAIL"
        print(
            f"[{status}] {subtask.label}"
            f"  {subtask.points_earned}/{subtask.points_possible}"
        )
        for test in subtask.tests:
            print(
                f"         {test.name:<8} {test.verdict.value:<4}"
                f"{test.cpu_time_ms:>6} ms{test.memory_kb // 1024:>6} MB"
            )
        if subtask.skipped:
            print(f"         ({subtask.skipped} remaining test cases skipped)")
        print()


def _print_summary(
    outcome: SubmissionOutcome,
    cf_accepted: bool,
    claim: ClaimResult | None = None,
) -> None:
    score = effective_score(outcome.local_score, cf_accepted)
    print(f"local score : {outcome.local_score}/{outcome.local_max}")
    print(f"peak time   : {outcome.slowest_ms} ms")
    if claim is not None:
        print(f"codeforces  : {claim.status.value} - {claim.detail}")
    else:
        print(f"codeforces  : {'AC' if cf_accepted else 'unclaimed'}")
    print(f"final score : {score}/{TOTAL_POINTS}")

    mismatch = diagnose(outcome, cf_accepted)
    if mismatch is not None:
        print()
        print(f"[instructor review] {mismatch.value}: {mismatch.hint}")


if __name__ == "__main__":
    raise SystemExit(main())