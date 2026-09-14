import pytest

from terasering import ProblemLoadError, TeraseringError, load_problem
from terasering.scaffold import (
    create_problem,
    parse_problem_ref,
    parse_subtasks,
)


class TestParseProblemRef:
    @pytest.mark.parametrize(
        "reference",
        [
            "474/B",
            "474B",
            "474-B",
            "474 b",
            "https://codeforces.com/contest/474/problem/B",
            "https://codeforces.com/problemset/problem/474/B",
            "codeforces.com/contest/474/problem/b",
            "  474/B  ",
        ],
    )
    def test_accepted_forms_all_mean_the_same_problem(self, reference):
        assert parse_problem_ref(reference) == (474, "B")

    def test_index_with_a_digit(self):
        # Easy and hard versions share a letter, so the digit matters.
        assert parse_problem_ref("1234/A1") == (1234, "A1")

    def test_gym_urls(self):
        assert parse_problem_ref(
            "https://codeforces.com/gym/104567/problem/C"
        ) == (104567, "C")

    @pytest.mark.parametrize("reference", ["", "B", "hello", "474/", "//"])
    def test_unreadable_references(self, reference):
        with pytest.raises(TeraseringError, match="could not read"):
            parse_problem_ref(reference)


class TestParseSubtasks:
    def test_labels_are_numbered_in_order(self):
        parsed = parse_subtasks("small:20,medium:30")
        assert [s.label for s in parsed] == ["01-small", "02-medium"]
        assert [s.points for s in parsed] == [20, 30]

    def test_labels_that_are_already_numbered_are_left_alone(self):
        parsed = parse_subtasks("01-tiny:10,02-huge:40")
        assert [s.label for s in parsed] == ["01-tiny", "02-huge"]

    def test_whitespace_is_tolerated(self):
        parsed = parse_subtasks(" small : 20 , medium : 30 ")
        assert [s.points for s in parsed] == [20, 30]

    def test_missing_points(self):
        with pytest.raises(TeraseringError, match="has no points"):
            parse_subtasks("small,medium:30")

    def test_non_numeric_points(self):
        with pytest.raises(TeraseringError, match="whole number"):
            parse_subtasks("small:lots")

    def test_zero_points(self):
        with pytest.raises(TeraseringError, match="more than zero"):
            parse_subtasks("small:0")

    def test_label_that_would_break_a_path(self):
        with pytest.raises(TeraseringError, match="not a usable name"):
            parse_subtasks("a/b:20")

    def test_total_above_one_hundred(self):
        with pytest.raises(TeraseringError, match="exceeds 100"):
            parse_subtasks("small:60,medium:60")

    def test_empty(self):
        with pytest.raises(TeraseringError, match="no subtasks"):
            parse_subtasks("")


class TestCreateProblem:
    def test_creates_directories_and_meta(self, tmp_path):
        root, subtasks = create_problem(tmp_path / "474B", reference="474/B")

        assert (root / "meta.toml").is_file()
        assert (root / "subtasks" / "01-small").is_dir()
        assert (root / "subtasks" / "02-medium").is_dir()
        assert len(subtasks) == 2

    def test_the_result_loads_once_tests_are_added(self, tmp_path):
        root, subtasks = create_problem(tmp_path / "474B", reference="474/B")
        for subtask in subtasks:
            directory = root / "subtasks" / subtask.label
            (directory / "01.in").write_text("1\n")
            (directory / "01.out").write_text("1\n")

        problem = load_problem(root)
        assert problem.cf_contest_id == 474
        assert problem.cf_index == "B"
        assert problem.local_max == 50

    def test_a_fresh_skeleton_reports_its_empty_subtasks(self, tmp_path):
        # Loading before any test cases exist should say so plainly.
        root, _ = create_problem(tmp_path / "474B")
        with pytest.raises(ProblemLoadError, match="no test cases"):
            load_problem(root)

    def test_codeforces_fields_are_commented_out_when_unknown(self, tmp_path):
        root, _ = create_problem(tmp_path / "draft")
        meta = (root / "meta.toml").read_text()

        assert "# cf_contest_id" in meta
        assert "\ncf_contest_id" not in meta

    def test_limits_and_checker_are_configurable(self, tmp_path):
        root, _ = create_problem(
            tmp_path / "474B",
            time_limit_ms=3000,
            memory_limit_mb=512,
            checker="float",
        )
        meta = (root / "meta.toml").read_text()

        assert "time_limit_ms = 3000" in meta
        assert "memory_limit_mb = 512" in meta
        assert 'checker = "float"' in meta

    def test_refuses_to_touch_an_existing_directory(self, tmp_path):
        target = tmp_path / "474B"
        target.mkdir()

        with pytest.raises(TeraseringError, match="already exists"):
            create_problem(target)

    def test_nothing_is_created_when_arguments_are_bad(self, tmp_path):
        target = tmp_path / "474B"

        with pytest.raises(TeraseringError):
            create_problem(target, subtasks="small:60,medium:60")
        assert not target.exists()