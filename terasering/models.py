"""Shared data types: verdicts, problem definitions, and scoring results.

This module deliberately imports nothing else from terasering so it can be
used from anywhere without circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

TOTAL_POINTS = 100


class Verdict(str, Enum):
    OK = "OK"
    WA = "WA"
    TLE = "TLE"
    MLE = "MLE"
    RE = "RE"
    OLE = "OLE"
    CE = "CE"

    @property
    def is_ok(self) -> bool:
        return self is Verdict.OK


class Checker(Protocol):
    """Decides whether a submission's output is acceptable.

    Implementations live in checkers.py. Problems with multiple valid answers
    can be supported by adding one, without touching any other module.
    """

    def accepts(self, expected: str, actual: str) -> bool: ...


@dataclass(frozen=True)
class Limits:
    time_ms: int
    memory_mb: int
    output_mb: int = 64

    def scaled(self, factor: float) -> Limits:
        """Return a copy with the time limit multiplied by `factor`."""
        return Limits(int(self.time_ms * factor), self.memory_mb, self.output_mb)


@dataclass(frozen=True)
class TestCase:
    #: The name starts with "Test", so pytest would try to collect this as a
    #: test class unless it is marked.
    __test__ = False

    name: str
    input_path: Path
    expected_path: Path

    def expected(self) -> str:
        return self.expected_path.read_text()


@dataclass(frozen=True)
class Subtask:
    label: str
    points: int
    tests: tuple[TestCase, ...]


@dataclass(frozen=True)
class Problem:
    id: str
    limits: Limits
    subtasks: tuple[Subtask, ...]
    checker: Checker
    root: Path
    cf_contest_id: int | None = None
    cf_index: str | None = None

    @property
    def local_max(self) -> int:
        """Highest score reachable from local test cases alone."""
        return sum(subtask.points for subtask in self.subtasks)

    @property
    def cf_url(self) -> str | None:
        if self.cf_contest_id is None or self.cf_index is None:
            return None
        return (
            f"https://codeforces.com/contest/{self.cf_contest_id}"
            f"/problem/{self.cf_index}"
        )


@dataclass(frozen=True)
class CompileResult:
    succeeded: bool
    binary: Path | None
    diagnostics: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class Execution:
    """Raw result of a single run, before the output is compared."""

    verdict: Verdict
    cpu_time_ms: int
    memory_kb: int
    stdout_path: Path
    stderr_path: Path
    exit_code: int | None = None
    signal: int | None = None

    def stdout(self) -> str:
        return _read(self.stdout_path)

    def stderr(self) -> str:
        return _read(self.stderr_path)


@dataclass(frozen=True)
class TestOutcome:
    __test__ = False

    name: str
    verdict: Verdict
    cpu_time_ms: int
    memory_kb: int


@dataclass
class SubtaskOutcome:
    label: str
    points_possible: int
    points_earned: int = 0
    tests_total: int = 0
    tests: list[TestOutcome] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.points_earned == self.points_possible

    @property
    def skipped(self) -> int:
        """Test cases left unrun because the subtask had already failed."""
        return max(0, self.tests_total - len(self.tests))

    @property
    def first_failure(self) -> TestOutcome | None:
        return next((t for t in self.tests if not t.verdict.is_ok), None)


@dataclass
class SubmissionOutcome:
    local_score: int
    local_max: int
    subtasks: list[SubtaskOutcome] = field(default_factory=list)
    compile_error: str | None = None
    compile_diagnostics: str | None = None

    @property
    def compiled(self) -> bool:
        return self.compile_error is None

    def tests(self) -> list[TestOutcome]:
        return [t for subtask in self.subtasks for t in subtask.tests]

    @property
    def slowest_ms(self) -> int:
        return max((t.cpu_time_ms for t in self.tests()), default=0)

    @property
    def peak_memory_kb(self) -> int:
        return max((t.memory_kb for t in self.tests()), default=0)


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(errors="replace")
