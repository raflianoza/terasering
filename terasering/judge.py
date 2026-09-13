"""The orchestrator: compile once, run every test case, total up subtask points.

    from terasering import Judge, load_problem

    judge = Judge()
    outcome = judge.evaluate(load_problem("problems/1234B"), source)

Swapping the sandbox, toolchain, or limits is a constructor argument; nothing
else needs to change.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .compiler import Compiler
from .config import CPP, JudgeConfig, Toolchain
from .models import (
    Limits,
    Problem,
    SubmissionOutcome,
    Subtask,
    SubtaskOutcome,
    TestOutcome,
    Verdict,
)
from .sandbox import RlimitSandbox, Sandbox


@dataclass
class Judge:
    """Scores one submission against one problem.

    Safe to reuse across submissions; each evaluation gets its own working
    directory, removed afterwards. Not safe to share across threads, and it
    should not need to be: evaluations belong in a queue of one, so that
    timing measurements do not interfere with each other.
    """

    config: JudgeConfig = field(default_factory=JudgeConfig)
    toolchain: Toolchain = CPP
    sandbox: Sandbox | None = None
    workdir_root: Path | None = None

    def __post_init__(self) -> None:
        if self.sandbox is None:
            self.sandbox = RlimitSandbox(self.config)
        self._compiler = Compiler(self.toolchain, self.config)

    def evaluate(
        self,
        problem: Problem,
        source: str,
        stop_on_failure: bool = True,
        limits: Limits | None = None,
    ) -> SubmissionOutcome:
        """Score `source` against every subtask of `problem`.

        Args:
            stop_on_failure: skip the remaining test cases in a subtask that
                has already failed. Turn it off when rejudging as an
                instructor, to see every test case that misbehaves.
            limits: override the limits from meta.toml, for instance while
                searching for a time limit that suits this machine.
        """
        effective_limits = self._resolve_limits(problem, limits)
        workdir = Path(tempfile.mkdtemp(prefix="teras-", dir=self.workdir_root))
        try:
            compiled = self._compiler.compile(source, workdir / "build")
            if not compiled.succeeded:
                return SubmissionOutcome(
                    local_score=0,
                    local_max=problem.local_max,
                    compile_error=compiled.diagnostics or "compilation failed",
                )

            outcome = SubmissionOutcome(
                local_score=0,
                local_max=problem.local_max,
                compile_diagnostics=compiled.diagnostics or None,
            )
            for subtask in problem.subtasks:
                outcome.subtasks.append(
                    self._evaluate_subtask(
                        subtask=subtask,
                        problem=problem,
                        binary=compiled.binary,
                        limits=effective_limits,
                        workdir=workdir,
                        stop_on_failure=stop_on_failure,
                    )
                )
            outcome.local_score = sum(s.points_earned for s in outcome.subtasks)
            return outcome
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # -- internals -------------------------------------------------------

    def _resolve_limits(self, problem: Problem, override: Limits | None) -> Limits:
        base = override or problem.limits
        limits = base.scaled(self.config.time_limit_factor)
        if override is None:
            limits = Limits(
                limits.time_ms, limits.memory_mb, self.config.output_limit_mb
            )
        return limits

    def _evaluate_subtask(
        self,
        *,
        subtask: Subtask,
        problem: Problem,
        binary: Path,
        limits: Limits,
        workdir: Path,
        stop_on_failure: bool,
    ) -> SubtaskOutcome:
        result = SubtaskOutcome(
            label=subtask.label,
            points_possible=subtask.points,
            tests_total=len(subtask.tests),
        )

        for test in subtask.tests:
            execution = self.sandbox.execute(
                binary=binary,
                input_path=test.input_path,
                limits=limits,
                workdir=workdir / "run" / subtask.label / test.name,
            )

            verdict = execution.verdict
            if verdict.is_ok and not problem.checker.accepts(
                test.expected(), execution.stdout()
            ):
                verdict = Verdict.WA

            result.tests.append(
                TestOutcome(
                    name=test.name,
                    verdict=verdict,
                    cpu_time_ms=execution.cpu_time_ms,
                    memory_kb=execution.memory_kb,
                )
            )
            if not verdict.is_ok and stop_on_failure:
                break

        # All-or-nothing per subtask, following IOI convention: one failed test
        # case forfeits the whole subtask.
        if all(t.verdict.is_ok for t in result.tests) and not result.skipped:
            result.points_earned = subtask.points
        return result
