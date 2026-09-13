"""Generating answer keys from a model solution.

Writing `.out` files by hand is the largest source of error in this system:
a wrong answer key silently marks correct submissions as wrong. Given a model
solution that is known to be correct, the keys can be produced instead.

    teras gen problems/1234B model.cpp

The model runs under the same sandbox and limits as a real submission. If it
times out or crashes on a large test case, that is worth discovering now
rather than after a participant complains about their score.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .compiler import Compiler
from .config import CPP, JudgeConfig, Toolchain
from .errors import TeraseringError
from .models import Limits, Problem, Subtask, TestCase, Verdict
from .sandbox import RlimitSandbox, Sandbox

#: Reported when an answer key is already present and --force was not given.
ALREADY_EXISTS = "already exists"


@dataclass(frozen=True)
class GeneratedCase:
    test: TestCase
    verdict: Verdict
    written: bool
    reason: str | None = None

    @property
    def blocked(self) -> bool:
        """True when the model failed, as opposed to the key being left alone."""
        return not self.written and self.reason != ALREADY_EXISTS


def generate(
    problem: Problem,
    model_source: str,
    *,
    config: JudgeConfig = JudgeConfig(),
    sandbox: Sandbox | None = None,
    toolchain: Toolchain = CPP,
    force: bool = False,
    subtask: str | None = None,
    dry_run: bool = False,
) -> list[GeneratedCase]:
    """Run `model_source` over every input and write the outputs it produces.

    Args:
        force: overwrite answer keys that already exist. Off by default so a
            hand-written key is never lost by accident.
        subtask: restrict generation to one subtask label.
        dry_run: report what would happen without touching the disk.

    Raises:
        TeraseringError: the model does not compile, or the subtask label does
            not exist. Both are operator mistakes rather than results, so they
            stop the run instead of being reported per test case.
    """
    subtasks = _select_subtasks(problem, subtask)
    limits = _resolve_limits(problem, config)
    sandbox = sandbox or RlimitSandbox(config)

    workdir = Path(tempfile.mkdtemp(prefix="teras-gen-"))
    try:
        compiled = Compiler(toolchain, config).compile(model_source, workdir / "build")
        if not compiled.succeeded:
            raise TeraseringError(
                f"model solution failed to compile:\n{compiled.diagnostics}"
            )

        results = []
        for group in subtasks:
            for test in group.tests:
                results.append(
                    _generate_one(
                        test=test,
                        binary=compiled.binary,
                        sandbox=sandbox,
                        limits=limits,
                        workdir=workdir / "run" / group.label / test.name,
                        force=force,
                        dry_run=dry_run,
                    )
                )
        return results
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _generate_one(
    *,
    test: TestCase,
    binary: Path,
    sandbox: Sandbox,
    limits: Limits,
    workdir: Path,
    force: bool,
    dry_run: bool,
) -> GeneratedCase:
    if test.expected_path.exists() and not force:
        return GeneratedCase(test, Verdict.OK, written=False, reason=ALREADY_EXISTS)

    execution = sandbox.execute(
        binary=binary,
        input_path=test.input_path,
        limits=limits,
        workdir=workdir,
    )

    # A key is only as good as the run that produced it. Anything short of a
    # clean exit leaves the previous file untouched.
    if not execution.verdict.is_ok:
        return GeneratedCase(
            test,
            execution.verdict,
            written=False,
            reason=f"model finished with {execution.verdict.value}",
        )

    if not dry_run:
        test.expected_path.write_text(_normalise(execution.stdout()))

    return GeneratedCase(test, Verdict.OK, written=True)


def _select_subtasks(problem: Problem, label: str | None) -> tuple[Subtask, ...]:
    if label is None:
        return problem.subtasks

    selected = tuple(s for s in problem.subtasks if s.label == label)
    if not selected:
        available = ", ".join(s.label for s in problem.subtasks)
        raise TeraseringError(
            f"no subtask named {label!r} (available: {available})"
        )
    return selected


def _resolve_limits(problem: Problem, config: JudgeConfig) -> Limits:
    scaled = problem.limits.scaled(config.time_limit_factor)
    return Limits(scaled.time_ms, scaled.memory_mb, config.output_limit_mb)


def _normalise(output: str) -> str:
    """End on exactly one newline.

    Checkers ignore whitespace, but tidy files diff cleanly in git.
    """
    return output.rstrip("\n") + "\n" if output.strip() else ""