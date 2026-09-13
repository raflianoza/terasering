"""Tests for answer key generation.

Marked `slow` because each one compiles a model solution.
"""

import shutil
import textwrap

import pytest

from terasering import TeraseringError, Verdict, generate, load_problem
from terasering.generator import ALREADY_EXISTS

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("g++") is None, reason="requires g++"),
]

META = """
id = "sum"
time_limit_ms = 1000
memory_limit_mb = 256

[subtasks]
"01-small" = 20
"02-medium" = 30
"""

MODEL = """
#include <cstdio>
int main() { int a, b; scanf("%d %d", &a, &b); printf("%d\\n", a + b); }
"""

INPUTS = {
    "01-small": {"01": "1 2", "02": "10 20"},
    "02-medium": {"01": "300 400"},
}

ANSWERS = {"1 2": "3", "10 20": "30", "300 400": "700"}


@pytest.fixture
def problem_dir(tmp_path):
    """A problem with inputs present but no answer keys yet."""
    for label, cases in INPUTS.items():
        directory = tmp_path / "subtasks" / label
        directory.mkdir(parents=True)
        for name, line in cases.items():
            (directory / f"{name}.in").write_text(f"{line}\n")
    (tmp_path / "meta.toml").write_text(META)
    return tmp_path


@pytest.fixture
def problem(problem_dir):
    return load_problem(problem_dir, require_answers=False)


def keys_on_disk(problem_dir):
    return sorted(p.name for p in problem_dir.rglob("*.out"))


class TestGeneration:
    def test_writes_every_missing_key(self, problem, problem_dir):
        cases = generate(problem, textwrap.dedent(MODEL))

        assert len(cases) == 3
        assert all(case.written for case in cases)
        assert keys_on_disk(problem_dir) == ["01.out", "01.out", "02.out"]

    def test_written_answers_are_correct(self, problem):
        generate(problem, textwrap.dedent(MODEL))

        for subtask in problem.subtasks:
            for test in subtask.tests:
                given = test.input_path.read_text().strip()
                assert test.expected().strip() == ANSWERS[given]

    def test_keys_end_in_a_single_newline(self, problem):
        generate(problem, textwrap.dedent(MODEL))
        content = problem.subtasks[0].tests[0].expected()
        assert content.endswith("\n")
        assert not content.endswith("\n\n")

    def test_one_subtask_only(self, problem, problem_dir):
        cases = generate(problem, textwrap.dedent(MODEL), subtask="02-medium")

        assert len(cases) == 1
        assert keys_on_disk(problem_dir) == ["01.out"]


class TestExistingKeysAreProtected:
    def test_existing_keys_are_kept_by_default(self, problem, problem_dir):
        target = problem_dir / "subtasks" / "01-small" / "01.out"
        target.write_text("written by hand\n")

        cases = generate(problem, textwrap.dedent(MODEL))
        kept = [c for c in cases if not c.written]

        assert len(kept) == 1
        assert kept[0].reason == ALREADY_EXISTS
        assert target.read_text() == "written by hand\n"

    def test_force_overwrites(self, problem, problem_dir):
        target = problem_dir / "subtasks" / "01-small" / "01.out"
        target.write_text("written by hand\n")

        cases = generate(problem, textwrap.dedent(MODEL), force=True)

        assert all(case.written for case in cases)
        assert target.read_text().strip() == "3"

    def test_dry_run_touches_nothing(self, problem, problem_dir):
        cases = generate(problem, textwrap.dedent(MODEL), dry_run=True)

        assert all(case.written for case in cases)  # reported as it would be
        assert keys_on_disk(problem_dir) == []      # but nothing on disk


class TestModelFailures:
    def test_a_timing_out_model_writes_nothing(self, problem, problem_dir):
        source = "#include <unistd.h>\nint main() { sleep(60); }"

        cases = generate(problem, source)

        assert all(case.blocked for case in cases)
        assert all(case.verdict is Verdict.TLE for case in cases)
        assert keys_on_disk(problem_dir) == []

    def test_a_crashing_model_writes_nothing(self, problem, problem_dir):
        source = "int main() { int* p = nullptr; *p = 1; return *p; }"

        cases = generate(problem, source)

        assert all(case.verdict is Verdict.RE for case in cases)
        assert keys_on_disk(problem_dir) == []

    def test_a_model_that_does_not_compile_stops_the_run(self, problem):
        with pytest.raises(TeraseringError, match="failed to compile"):
            generate(problem, "int main() { this is not c++ }")

    def test_an_unknown_subtask_stops_the_run(self, problem):
        with pytest.raises(TeraseringError, match="no subtask named"):
            generate(problem, textwrap.dedent(MODEL), subtask="03-nonexistent")
