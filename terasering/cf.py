"""Verifying a claimed Codeforces submission.

Participants submit to Codeforces themselves and report the submission id.
This module checks that claim against the public API, so no credentials are
stored and nothing here breaks when Codeforces changes its page layout.

    https://codeforces.com/api/user.status?handle=...&from=1&count=200

Four things have to line up before a claim counts: the submission id exists,
it belongs to the claimed handle, it targets the expected problem, and its
verdict is OK. Checking only the verdict would let anyone paste any accepted
submission id.

The API is anonymous and rate limited to roughly one call every two seconds,
which `CodeforcesClient.min_interval_s` respects. Verified claims should be
cached by the caller; re-checking a settled claim wastes the budget.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .errors import TeraseringError
from .models import Problem

API_URL = "https://codeforces.com/api/user.status"
USER_AGENT = "terasering/0.1 (+https://github.com/)"

#: Verdicts that mean the submission is still being judged. A claim in this
#: state is not a failure; it just needs to be checked again later.
PENDING_VERDICTS = frozenset({None, "TESTING", "SUBMITTED"})


class CodeforcesError(TeraseringError):
    """The Codeforces API could not be reached or returned an error."""


@dataclass(frozen=True)
class CodeforcesSubmission:
    id: int
    handles: tuple[str, ...]
    contest_id: int | None
    index: str | None
    verdict: str | None
    passed_test_count: int
    time_ms: int
    memory_kb: int

    @property
    def accepted(self) -> bool:
        return self.verdict == "OK"

    @property
    def pending(self) -> bool:
        return self.verdict in PENDING_VERDICTS

    def belongs_to(self, handle: str) -> bool:
        """Team submissions carry several handles, so membership is the test."""
        return handle.casefold() in {h.casefold() for h in self.handles}

    def solves(self, contest_id: int, index: str) -> bool:
        return self.contest_id == contest_id and self.index == index


class ClaimStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"           # found, but the verdict is not OK
    PENDING = "PENDING"             # still being judged
    WRONG_PROBLEM = "WRONG_PROBLEM"  # a real submission, to something else
    NOT_FOUND = "NOT_FOUND"         # no such submission under that handle


@dataclass(frozen=True)
class ClaimResult:
    status: ClaimStatus
    detail: str
    submission: CodeforcesSubmission | None = None

    @property
    def accepted(self) -> bool:
        return self.status is ClaimStatus.ACCEPTED


def fetch_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    """Default transport. Injectable so the rest can be tested offline."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise CodeforcesError(f"Codeforces returned HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise CodeforcesError(f"could not reach Codeforces: {exc.reason}") from None
    except json.JSONDecodeError:
        raise CodeforcesError("Codeforces returned a malformed response") from None


@dataclass
class CodeforcesClient:
    """Reads submission metadata from the public Codeforces API.

    Args:
        fetch: transport, replaceable in tests.
        min_interval_s: smallest gap between calls. Codeforces rejects bursts.
        page_size: submissions per call; the API caps this well above 200.
        max_pages: how far back to look before giving up on an id.
    """

    fetch: Callable[[str], dict[str, Any]] = fetch_json
    min_interval_s: float = 2.0
    page_size: int = 200
    max_pages: int = 5
    _last_call: float = field(default=0.0, repr=False)

    def recent(self, handle: str, start: int = 1, count: int | None = None):
        """Return one page of a user's submissions, newest first."""
        query = urllib.parse.urlencode(
            {"handle": handle, "from": start, "count": count or self.page_size}
        )
        payload = self._call(f"{API_URL}?{query}")
        return [_parse_submission(item) for item in payload]

    def find(self, handle: str, submission_id: int) -> CodeforcesSubmission | None:
        """Page backwards through a user's history looking for one submission.

        Returns None once the history runs out or `max_pages` is reached.
        """
        for page in range(self.max_pages):
            start = page * self.page_size + 1
            batch = self.recent(handle, start=start)
            if not batch:
                return None
            for submission in batch:
                if submission.id == submission_id:
                    return submission
        return None

    def verify(
        self, handle: str, submission_id: int, problem: Problem
    ) -> ClaimResult:
        """Check a claimed submission against the problem it should solve."""
        if problem.cf_contest_id is None or problem.cf_index is None:
            raise CodeforcesError(
                f"problem {problem.id!r} has no cf_contest_id and cf_index in "
                f"meta.toml, so a claim cannot be checked against it"
            )

        submission = self.find(handle, submission_id)
        if submission is None:
            return ClaimResult(
                ClaimStatus.NOT_FOUND,
                f"no submission {submission_id} found under handle {handle!r}",
            )

        # Checked separately from ownership: the API only returns this user's
        # submissions, but team entries list several handles.
        if not submission.belongs_to(handle):
            return ClaimResult(
                ClaimStatus.NOT_FOUND,
                f"submission {submission_id} is not authored by {handle!r}",
                submission,
            )

        if not submission.solves(problem.cf_contest_id, problem.cf_index):
            return ClaimResult(
                ClaimStatus.WRONG_PROBLEM,
                f"submission {submission_id} targets "
                f"{submission.contest_id}{submission.index}, expected "
                f"{problem.cf_contest_id}{problem.cf_index}",
                submission,
            )

        if submission.pending:
            return ClaimResult(
                ClaimStatus.PENDING,
                f"submission {submission_id} is still being judged",
                submission,
            )

        if not submission.accepted:
            return ClaimResult(
                ClaimStatus.REJECTED,
                f"submission {submission_id} finished with "
                f"{submission.verdict} on test {submission.passed_test_count + 1}",
                submission,
            )

        return ClaimResult(
            ClaimStatus.ACCEPTED,
            f"submission {submission_id} is accepted "
            f"({submission.time_ms} ms, {submission.memory_kb // 1024} MB)",
            submission,
        )

    # -- internals -------------------------------------------------------

    def _call(self, url: str) -> list[dict[str, Any]]:
        self._wait_for_slot()
        payload = self.fetch(url)
        self._last_call = time.monotonic()

        if payload.get("status") != "OK":
            comment = payload.get("comment", "no reason given")
            raise CodeforcesError(f"Codeforces rejected the request: {comment}")

        result = payload.get("result")
        if not isinstance(result, list):
            raise CodeforcesError("Codeforces returned an unexpected payload")
        return result

    def _wait_for_slot(self) -> None:
        if not self._last_call:
            return
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)


def _parse_submission(item: dict[str, Any]) -> CodeforcesSubmission:
    problem = item.get("problem") or {}
    members = (item.get("author") or {}).get("members") or []
    return CodeforcesSubmission(
        id=int(item["id"]),
        handles=tuple(m["handle"] for m in members if "handle" in m),
        contest_id=problem.get("contestId"),
        index=problem.get("index"),
        # Absent while a submission is still queued, hence .get rather than [].
        verdict=item.get("verdict"),
        passed_test_count=int(item.get("passedTestCount", 0)),
        time_ms=int(item.get("timeConsumedMillis", 0)),
        memory_kb=int(item.get("memoryConsumedBytes", 0)) // 1024,
    )