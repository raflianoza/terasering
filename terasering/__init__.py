"""Partial-point judge for ICPC-style Codeforces problems."""

from .cf import ClaimResult, ClaimStatus, CodeforcesClient, CodeforcesError
from .checkers import ExactChecker, FloatChecker, build_checker
from .config import CPP, JudgeConfig, Toolchain
from .errors import (
    ProblemLoadError,
    SandboxError,
    TeraseringError,
    ToolchainError,
)
from .generator import GeneratedCase, generate
from .judge import Judge
from .loader import load_problem
from .models import (
    TOTAL_POINTS,
    Limits,
    Problem,
    SubmissionOutcome,
    Subtask,
    SubtaskOutcome,
    TestCase,
    TestOutcome,
    Verdict,
)
from .sandbox import RlimitSandbox
from .scoring import Mismatch, diagnose, effective_score

__version__ = "0.1.0"

__all__ = [
    "CPP",
    "ClaimResult",
    "ClaimStatus",
    "CodeforcesClient",
    "CodeforcesError",
    "TOTAL_POINTS",
    "ExactChecker",
    "FloatChecker",
    "GeneratedCase",
    "Judge",
    "JudgeConfig",
    "Limits",
    "Mismatch",
    "Problem",
    "ProblemLoadError",
    "RlimitSandbox",
    "SandboxError",
    "SubmissionOutcome",
    "Subtask",
    "SubtaskOutcome",
    "TeraseringError",
    "TestCase",
    "TestOutcome",
    "Toolchain",
    "ToolchainError",
    "Verdict",
    "build_checker",
    "diagnose",
    "effective_score",
    "generate",
    "load_problem",
]