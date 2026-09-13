"""Scoring policy: how local results and the Codeforces verdict combine.

Everything here is a pure function, so the scoring rules can be changed and
tested without running any submitted code.
"""

from __future__ import annotations

from enum import Enum

from .models import TOTAL_POINTS, SubmissionOutcome, Verdict


def effective_score(local_score: int, cf_accepted: bool) -> int:
    """The score shown on the scoreboard.

    An AC on Codeforces acts as a final subtask with no constraints: passing
    there overrides the local result to full marks.

    Computed on read rather than stored. A Codeforces claim arrives after the
    local evaluation, so a stored value would inevitably go stale.
    """
    return TOTAL_POINTS if cf_accepted else local_score


class Mismatch(str, Enum):
    """Why a local score fell short even though Codeforces accepted the solution.

    Intended for the instructor's review page, not for participants.
    """

    COMPILE_ERROR = "CE"
    ALL_TESTS_FAILED = "ALL_FAIL"
    WRONG_ANSWER = "WA"
    RUNTIME_ERROR = "RE"
    OUT_OF_MEMORY = "MLE"
    OUTPUT_TOO_LARGE = "OLE"
    TOO_SLOW = "TLE"

    @property
    def hint(self) -> str:
        return _HINTS[self]


_HINTS = {
    Mismatch.COMPILE_ERROR: (
        "Failed to compile here but built fine on Codeforces. "
        "Check the compiler version and flags."
    ),
    Mismatch.ALL_TESTS_FAILED: (
        "Not a single test case passed. Almost always means this problem's "
        "input format is wrong."
    ),
    Mismatch.WRONG_ANSWER: (
        "Output differs from the answer key. Review the answer key by hand."
    ),
    Mismatch.RUNTIME_ERROR: (
        "The code died here. The local memory limit may be too tight."
    ),
    Mismatch.OUT_OF_MEMORY: "The local memory limit is stricter than Codeforces.",
    Mismatch.OUTPUT_TOO_LARGE: "Output exceeded the local size limit.",
    Mismatch.TOO_SLOW: (
        "Ran out of time here only. Usually just a slower machine rather than "
        "a problem with the setup."
    ),
}

#: Correctness problems are reported ahead of speed problems, because a local
#: TLE is nearly always just a difference in machine speed.
_PRIORITY = (
    (Verdict.WA, Mismatch.WRONG_ANSWER),
    (Verdict.RE, Mismatch.RUNTIME_ERROR),
    (Verdict.MLE, Mismatch.OUT_OF_MEMORY),
    (Verdict.OLE, Mismatch.OUTPUT_TOO_LARGE),
    (Verdict.TLE, Mismatch.TOO_SLOW),
)


def diagnose(outcome: SubmissionOutcome, cf_accepted: bool) -> Mismatch | None:
    """Explain why the local score fell short. None when nothing is wrong.

    Only meaningful once Codeforces has accepted the solution; without that, a
    low local score is a legitimate result rather than a symptom of a broken
    problem setup.
    """
    if not cf_accepted:
        return None
    if not outcome.compiled:
        return Mismatch.COMPILE_ERROR
    if outcome.local_score >= outcome.local_max:
        return None

    tests = outcome.tests()
    if not tests or all(not t.verdict.is_ok for t in tests):
        return Mismatch.ALL_TESTS_FAILED

    failed = {t.verdict for t in tests if not t.verdict.is_ok}
    return next(
        (mismatch for verdict, mismatch in _PRIORITY if verdict in failed), None
    )
