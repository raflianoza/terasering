import pytest

from terasering import ProblemLoadError, load_problem
from terasering.checkers import FloatChecker

HEADER = """
id = "sample"
time_limit_ms = 1500
memory_limit_mb = 128
"""

SUBTASKS = """
[subtasks]
"01-small" = 20
"""

META = HEADER + SUBTASKS


@pytest.fixture
def problem_dir(tmp_path):
    """A minimal valid problem: one subtask holding one test case."""
    subtask = tmp_path / "subtasks" / "01-small"
    subtask.mkdir(parents=True)
    (subtask / "01.in").write_text("1\n")
    (subtask / "01.out").write_text("1\n")
    (tmp_path / "meta.toml").write_text(META)
    return tmp_path


def test_loads_a_complete_problem(problem_dir):
    problem = load_problem(problem_dir)
    assert problem.id == "sample"
    assert problem.limits.time_ms == 1500
    assert problem.limits.memory_mb == 128
    assert problem.local_max == 20
    assert len(problem.subtasks) == 1
    assert problem.subtasks[0].tests[0].expected() == "1\n"


def test_cf_url_is_none_without_metadata(problem_dir):
    assert load_problem(problem_dir).cf_url is None


def test_cf_url_is_built_from_metadata(problem_dir):
    (problem_dir / "meta.toml").write_text(
        HEADER + 'cf_contest_id = 1234\ncf_index = "B"\n' + SUBTASKS
    )
    assert load_problem(problem_dir).cf_url.endswith("/contest/1234/problem/B")


def test_checker_is_selectable_from_meta(problem_dir):
    (problem_dir / "meta.toml").write_text(
        HEADER + 'checker = "float"\n' + SUBTASKS + "\n[checker_options]\neps = 1e-3\n"
    )
    checker = load_problem(problem_dir).checker
    assert isinstance(checker, FloatChecker)
    assert checker.eps == 1e-3


def test_missing_meta(tmp_path):
    with pytest.raises(ProblemLoadError, match="not found"):
        load_problem(tmp_path)


def test_malformed_toml(problem_dir):
    (problem_dir / "meta.toml").write_text("this = = not toml")
    with pytest.raises(ProblemLoadError, match="invalid TOML"):
        load_problem(problem_dir)


def test_input_without_matching_output(problem_dir):
    (problem_dir / "subtasks" / "01-small" / "01.out").unlink()
    with pytest.raises(ProblemLoadError, match="no matching"):
        load_problem(problem_dir)


def test_subtask_without_points(problem_dir):
    forgotten = problem_dir / "subtasks" / "02-forgotten"
    forgotten.mkdir()
    (forgotten / "01.in").write_text("1\n")
    (forgotten / "01.out").write_text("1\n")
    with pytest.raises(ProblemLoadError, match="no points"):
        load_problem(problem_dir)


def test_points_without_directory_is_caught_as_a_typo(problem_dir):
    (problem_dir / "meta.toml").write_text(META + '"02-typoo" = 30\n')
    with pytest.raises(ProblemLoadError, match="no such directory"):
        load_problem(problem_dir)


def test_empty_subtask(problem_dir):
    for path in (problem_dir / "subtasks" / "01-small").iterdir():
        path.unlink()
    with pytest.raises(ProblemLoadError, match="no test cases"):
        load_problem(problem_dir)


def test_points_exceeding_one_hundred(problem_dir):
    (problem_dir / "meta.toml").write_text(META.replace("= 20", "= 120"))
    with pytest.raises(ProblemLoadError, match="exceeds"):
        load_problem(problem_dir)


def test_missing_answer_key_is_allowed_when_not_required(problem_dir):
    # `teras gen` loads a problem precisely because the keys are absent.
    (problem_dir / "subtasks" / "01-small" / "01.out").unlink()
    problem = load_problem(problem_dir, require_answers=False)
    assert len(problem.subtasks[0].tests) == 1
