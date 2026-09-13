import pytest

from terasering import ProblemLoadError, build_checker
from terasering.checkers import ExactChecker, FloatChecker


class TestExactChecker:
    checker = ExactChecker()

    @pytest.mark.parametrize(
        "expected, actual",
        [
            ("1 2 3", "1 2 3"),
            ("1 2 3\n", "1 2 3"),          # trailing newline
            ("1 2 3", "1  2\t3\n\n"),      # doubled spaces and tabs
            ("1\n2\n3", "1 2 3"),          # newlines versus spaces
            ("", ""),
            ("\n", ""),
        ],
    )
    def test_accepts(self, expected, actual):
        assert self.checker.accepts(expected, actual)

    @pytest.mark.parametrize(
        "expected, actual",
        [
            ("1 2 3", "1 2 4"),
            ("1 2 3", "1 2"),              # too few tokens
            ("1 2", "1 2 3"),              # too many tokens
            ("", "0"),
            ("0.1", "0.10"),               # without tolerance, must match exactly
        ],
    )
    def test_rejects(self, expected, actual):
        assert not self.checker.accepts(expected, actual)


class TestFloatChecker:
    def test_difference_within_tolerance_is_accepted(self):
        assert FloatChecker(eps=1e-6).accepts("0.1", "0.100000001")

    def test_difference_beyond_tolerance_is_rejected(self):
        assert not FloatChecker(eps=1e-6).accepts("0.1", "0.2")

    def test_tolerance_also_applies_relatively(self):
        assert FloatChecker(eps=1e-9).accepts("1000000", "1000000.0001")

    def test_non_numeric_tokens_still_compared_exactly(self):
        checker = FloatChecker(eps=1e-6)
        assert checker.accepts("YES", "YES")
        assert not checker.accepts("YES", "NO")

    def test_token_count_must_still_match(self):
        assert not FloatChecker(eps=1e-6).accepts("1.0 2.0", "1.0")

    def test_nan(self):
        checker = FloatChecker(eps=1e-6)
        # Identical tokens pass through the string comparison and never reach
        # the numeric one.
        assert checker.accepts("nan", "nan")
        # NaN is never close to anything.
        assert not checker.accepts("nan", "NaN")
        assert not checker.accepts("1.0", "nan")


class TestBuildChecker:
    def test_defaults_and_options(self):
        assert isinstance(build_checker("exact"), ExactChecker)
        assert build_checker("float", {"eps": 1e-3}).eps == 1e-3

    def test_unknown_name(self):
        with pytest.raises(ProblemLoadError, match="unknown checker"):
            build_checker("nonexistent")

    def test_invalid_options(self):
        with pytest.raises(ProblemLoadError, match="invalid options"):
            build_checker("float", {"tolerance": 1e-3})
