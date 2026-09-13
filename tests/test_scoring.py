import pytest

from terasering import Mismatch, SubmissionOutcome, SubtaskOutcome, TestOutcome, Verdict
from terasering.scoring import diagnose, effective_score


def outcome(*verdicts: Verdict, earned: int = 0, maximum: int = 50) -> SubmissionOutcome:
    """Build a SubmissionOutcome holding one subtask with the given verdicts."""
    subtask = SubtaskOutcome(
        label="01",
        points_possible=maximum,
        points_earned=earned,
        tests_total=len(verdicts),
        tests=[TestOutcome(str(i), v, 0, 0) for i, v in enumerate(verdicts)],
    )
    return SubmissionOutcome(local_score=earned, local_max=maximum, subtasks=[subtask])


class TestEffectiveScore:
    @pytest.mark.parametrize("local", [0, 20, 50])
    def test_codeforces_ac_always_gives_full_marks(self, local):
        assert effective_score(local, cf_accepted=True) == 100

    @pytest.mark.parametrize("local", [0, 20, 50])
    def test_without_ac_the_local_score_stands(self, local):
        assert effective_score(local, cf_accepted=False) == local


class TestDiagnose:
    def test_never_complains_without_a_codeforces_claim(self):
        assert diagnose(outcome(Verdict.WA), cf_accepted=False) is None

    def test_a_full_local_score_is_not_a_problem(self):
        assert diagnose(outcome(Verdict.OK, earned=50), cf_accepted=True) is None

    def test_everything_failing_points_at_the_input_format(self):
        result = outcome(Verdict.WA, Verdict.WA)
        assert diagnose(result, cf_accepted=True) is Mismatch.ALL_TESTS_FAILED

    def test_partial_failure_from_a_wrong_answer(self):
        result = outcome(Verdict.OK, Verdict.WA)
        assert diagnose(result, cf_accepted=True) is Mismatch.WRONG_ANSWER

    def test_partial_failure_from_running_out_of_time(self):
        result = outcome(Verdict.OK, Verdict.TLE)
        assert diagnose(result, cf_accepted=True) is Mismatch.TOO_SLOW

    def test_correctness_outranks_speed(self):
        result = outcome(Verdict.OK, Verdict.TLE, Verdict.WA)
        assert diagnose(result, cf_accepted=True) is Mismatch.WRONG_ANSWER

    def test_compilation_failure(self):
        result = SubmissionOutcome(0, 50, compile_error="boom")
        assert diagnose(result, cf_accepted=True) is Mismatch.COMPILE_ERROR

    def test_every_mismatch_has_an_explanation(self):
        for mismatch in Mismatch:
            assert mismatch.hint
