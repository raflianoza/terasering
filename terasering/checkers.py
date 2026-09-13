"""Comparing a submission's output against the answer key.

Every checker ignores whitespace entirely, so trailing newlines and doubled
spaces never cause a spurious WA.

To add a checker: write a class with an `accepts` method and register it in
`CHECKERS`. Problems select one via `checker = "..."` in meta.toml.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .errors import ProblemLoadError
from .models import Checker


@dataclass(frozen=True)
class ExactChecker:
    """Accepts when every token matches. The default for unique-answer problems."""

    def accepts(self, expected: str, actual: str) -> bool:
        return expected.split() == actual.split()


@dataclass(frozen=True)
class FloatChecker:
    """Accepts when each token matches exactly, or is close enough as a number.

    The tolerance applies both absolutely and relatively, following testlib's
    convention: larger values may drift further in absolute terms.
    """

    eps: float = 1e-6

    def accepts(self, expected: str, actual: str) -> bool:
        expected_tokens = expected.split()
        actual_tokens = actual.split()
        if len(expected_tokens) != len(actual_tokens):
            return False
        return all(
            self._token_ok(e, a) for e, a in zip(expected_tokens, actual_tokens)
        )

    def _token_ok(self, expected: str, actual: str) -> bool:
        if expected == actual:
            return True
        try:
            a, b = float(expected), float(actual)
        except ValueError:
            return False
        if a != a or b != b:  # NaN is never close to anything
            return False
        diff = abs(a - b)
        return diff <= self.eps or diff <= self.eps * max(abs(a), abs(b))


CHECKERS: dict[str, Callable[..., Checker]] = {
    "exact": ExactChecker,
    "float": FloatChecker,
}


def build_checker(kind: str, options: dict[str, Any] | None = None) -> Checker:
    """Build a checker from the name and options written in meta.toml."""
    try:
        factory = CHECKERS[kind]
    except KeyError:
        known = ", ".join(sorted(CHECKERS))
        raise ProblemLoadError(
            f"unknown checker {kind!r} (available: {known})"
        ) from None
    try:
        return factory(**(options or {}))
    except TypeError as exc:
        raise ProblemLoadError(f"invalid options for checker {kind!r}: {exc}") from None
