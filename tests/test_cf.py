"""Tests for Codeforces claim verification.

The transport is injected, so none of these touch the network.
"""

import pytest

from terasering import load_problem
from terasering.cf import (
    ClaimStatus,
    CodeforcesClient,
    CodeforcesError,
    CodeforcesSubmission,
)

HANDLE = "student1"
CONTEST_ID = 1234
INDEX = "B"

META = f"""
id = "1234B"
cf_contest_id = {CONTEST_ID}
cf_index = "{INDEX}"
time_limit_ms = 1000
memory_limit_mb = 256

[subtasks]
"01-small" = 20
"""


def submission(
    id=1000,
    handles=(HANDLE,),
    contest_id=CONTEST_ID,
    index=INDEX,
    verdict="OK",
    passed=10,
):
    """One entry as the Codeforces API would return it."""
    return {
        "id": id,
        "author": {"members": [{"handle": h} for h in handles]},
        "problem": {"contestId": contest_id, "index": index},
        "verdict": verdict,
        "passedTestCount": passed,
        "timeConsumedMillis": 342,
        "memoryConsumedBytes": 8 * 1024 * 1024,
    }


def client_returning(*pages, **kwargs):
    """A client whose transport replays the given pages in order."""
    remaining = list(pages)
    calls = []

    def fetch(url):
        calls.append(url)
        page = remaining.pop(0) if remaining else []
        return {"status": "OK", "result": page}

    client = CodeforcesClient(fetch=fetch, min_interval_s=0, **kwargs)
    client.calls = calls
    return client


@pytest.fixture
def problem(tmp_path):
    subtask = tmp_path / "subtasks" / "01-small"
    subtask.mkdir(parents=True)
    (subtask / "01.in").write_text("1\n")
    (subtask / "01.out").write_text("1\n")
    (tmp_path / "meta.toml").write_text(META)
    return load_problem(tmp_path)


class TestParsing:
    def test_reads_the_fields_it_needs(self):
        client = client_returning([submission(id=77)])
        [parsed] = client.recent(HANDLE)

        assert parsed.id == 77
        assert parsed.handles == (HANDLE,)
        assert parsed.contest_id == CONTEST_ID
        assert parsed.index == INDEX
        assert parsed.accepted
        assert parsed.memory_kb == 8192

    def test_a_queued_submission_has_no_verdict(self):
        raw = submission()
        del raw["verdict"]
        client = client_returning([raw])
        [parsed] = client.recent(HANDLE)

        assert parsed.verdict is None
        assert parsed.pending
        assert not parsed.accepted

    def test_handle_matching_ignores_case(self):
        parsed = CodeforcesSubmission(
            1, ("Student1",), CONTEST_ID, INDEX, "OK", 1, 1, 1
        )
        assert parsed.belongs_to("student1")
        assert not parsed.belongs_to("someone_else")


class TestVerify:
    def test_accepted_claim(self, problem):
        client = client_returning([submission(id=500)])
        result = client.verify(HANDLE, 500, problem)

        assert result.status is ClaimStatus.ACCEPTED
        assert result.accepted
        assert result.submission.id == 500

    def test_rejected_verdict(self, problem):
        client = client_returning([submission(id=500, verdict="TIME_LIMIT_EXCEEDED")])
        result = client.verify(HANDLE, 500, problem)

        assert result.status is ClaimStatus.REJECTED
        assert not result.accepted
        # Reported one-based, matching how Codeforces itself phrases it.
        assert "test 11" in result.detail

    def test_still_being_judged(self, problem):
        client = client_returning([submission(id=500, verdict="TESTING")])
        assert client.verify(HANDLE, 500, problem).status is ClaimStatus.PENDING

    def test_accepted_but_for_another_problem(self, problem):
        client = client_returning([submission(id=500, contest_id=999, index="A")])
        result = client.verify(HANDLE, 500, problem)

        assert result.status is ClaimStatus.WRONG_PROBLEM
        assert "999A" in result.detail

    def test_same_contest_different_index(self, problem):
        client = client_returning([submission(id=500, index="C")])
        assert client.verify(HANDLE, 500, problem).status is ClaimStatus.WRONG_PROBLEM

    def test_unknown_submission_id(self, problem):
        client = client_returning([submission(id=1), submission(id=2)])
        result = client.verify(HANDLE, 999, problem)

        assert result.status is ClaimStatus.NOT_FOUND
        assert result.submission is None

    def test_team_submission_counts_for_each_member(self, problem):
        client = client_returning([submission(id=500, handles=("alice", HANDLE))])
        assert client.verify(HANDLE, 500, problem).accepted

    def test_problem_without_codeforces_metadata(self, problem, tmp_path):
        (tmp_path / "meta.toml").write_text(
            META.replace(f"cf_contest_id = {CONTEST_ID}", "").replace(
                f'cf_index = "{INDEX}"', ""
            )
        )
        bare = load_problem(tmp_path)
        client = client_returning([submission()])

        with pytest.raises(CodeforcesError, match="no cf_contest_id"):
            client.verify(HANDLE, 500, bare)


class TestPaging:
    def test_looks_beyond_the_first_page(self, problem):
        client = client_returning(
            [submission(id=i) for i in range(10, 13)],
            [submission(id=500)],
            page_size=3,
        )
        assert client.verify(HANDLE, 500, problem).accepted
        assert len(client.calls) == 2
        assert "from=4" in client.calls[1]

    def test_stops_when_history_runs_out(self, problem):
        client = client_returning([submission(id=1)], [], page_size=1)
        assert client.verify(HANDLE, 500, problem).status is ClaimStatus.NOT_FOUND
        assert len(client.calls) == 2

    def test_gives_up_after_max_pages(self, problem):
        pages = [[submission(id=i)] for i in range(20)]
        client = client_returning(*pages, page_size=1, max_pages=3)

        assert client.verify(HANDLE, 500, problem).status is ClaimStatus.NOT_FOUND
        assert len(client.calls) == 3


class TestApiErrors:
    def test_api_level_failure_is_reported(self):
        def fetch(url):
            return {"status": "FAILED", "comment": "handle: User not found"}

        client = CodeforcesClient(fetch=fetch, min_interval_s=0)
        with pytest.raises(CodeforcesError, match="User not found"):
            client.recent("nonexistent")

    def test_unexpected_payload_is_reported(self):
        client = CodeforcesClient(fetch=lambda url: {"status": "OK"}, min_interval_s=0)
        with pytest.raises(CodeforcesError, match="unexpected payload"):
            client.recent(HANDLE)

    def test_handles_needing_escaping_are_encoded(self):
        client = client_returning([])
        client.recent("a b&c")
        assert "handle=a+b%26c" in client.calls[0]
