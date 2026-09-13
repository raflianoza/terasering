"""Integration tests that really compile and run C++ code.

Marked `slow` because each one invokes g++. Skip them with:

    pytest -m "not slow"
"""

import shutil
import textwrap

import pytest

from terasering import Judge, JudgeConfig, Limits, Verdict, load_problem

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("g++") is None, reason="requires g++"),
]

META = """
id = "sum"
time_limit_ms = 1000
memory_limit_mb = 256

[subtasks]
"01-small" = 30
"""

CORRECT = """
#include <cstdio>
int main() { int a, b; scanf("%d %d", &a, &b); printf("%d\\n", a + b); }
"""

WRONG = """
#include <cstdio>
int main() { printf("0\\n"); }
"""


@pytest.fixture(scope="module")
def problem(tmp_path_factory):
    """An a+b problem with two test cases in a single subtask."""
    root = tmp_path_factory.mktemp("sum")
    subtask = root / "subtasks" / "01-small"
    subtask.mkdir(parents=True)
    for name, (line, answer) in {"01": ("1 2", "3"), "02": ("10 20", "30")}.items():
        (subtask / f"{name}.in").write_text(f"{line}\n")
        (subtask / f"{name}.out").write_text(f"{answer}\n")
    (root / "meta.toml").write_text(META)
    return load_problem(root)


@pytest.fixture(scope="module")
def judge():
    return Judge()


def run(judge, problem, source, **kwargs):
    return judge.evaluate(problem, textwrap.dedent(source), **kwargs)


class TestScoring:
    def test_correct_solution_earns_full_points(self, judge, problem):
        outcome = run(judge, problem, CORRECT)
        assert outcome.compiled
        assert outcome.local_score == 30
        assert [t.verdict for t in outcome.tests()] == [Verdict.OK, Verdict.OK]

    def test_wrong_solution_earns_nothing(self, judge, problem):
        outcome = run(judge, problem, WRONG)
        assert outcome.local_score == 0
        assert outcome.tests()[0].verdict is Verdict.WA

    def test_compilation_failure(self, judge, problem):
        outcome = run(judge, problem, "int main() { this is not c++ }")
        assert not outcome.compiled
        assert "error" in outcome.compile_error

    def test_stop_on_failure_skips_the_rest(self, judge, problem):
        outcome = run(judge, problem, WRONG, stop_on_failure=True)
        assert len(outcome.tests()) == 1
        assert outcome.subtasks[0].skipped == 1

    def test_all_tests_runs_everything(self, judge, problem):
        outcome = run(judge, problem, WRONG, stop_on_failure=False)
        assert len(outcome.tests()) == 2
        assert outcome.subtasks[0].skipped == 0


class TestResourceLimits:
    def test_slow_code_hits_the_time_limit(self, judge, problem):
        source = """
            #include <cstdio>
            int main() {
                volatile long long x = 0;
                for (long long i = 0; i < 20000000000LL; i++) x += i;
                printf("%lld\\n", x);
            }
        """
        assert run(judge, problem, source).tests()[0].verdict is Verdict.TLE

    def test_waiting_without_burning_cpu_still_times_out(self, judge, problem):
        # A CPU limit never fires here; the wall-clock watchdog is what catches it.
        source = "#include <unistd.h>\nint main() { sleep(60); }"
        test = run(judge, problem, source).tests()[0]
        assert test.verdict is Verdict.TLE
        assert test.cpu_time_ms < 100

    def test_running_out_of_memory(self, judge, problem):
        source = """
            #include <vector>
            int main() {
                std::vector<char> v;
                for (int i = 0; i < 4000; i++) v.resize(v.size() + (1 << 20), 1);
            }
        """
        # A generous time budget, so this exercises the memory limit rather
        # than racing the clock: allocating until refusal is itself slow.
        outcome = judge.evaluate(
            problem,
            textwrap.dedent(source),
            limits=Limits(time_ms=10_000, memory_mb=256),
        )
        assert outcome.tests()[0].verdict is Verdict.MLE

    def test_runaway_output(self, judge, problem):
        source = """
            #include <cstdio>
            int main() { for (long long i = 0;; i++) printf("%lld\\n", i); }
        """
        outcome = judge.evaluate(
            problem,
            textwrap.dedent(source),
            limits=Limits(time_ms=2000, memory_mb=256, output_mb=8),
        )
        assert outcome.tests()[0].verdict is Verdict.OLE

    def test_a_crash_becomes_a_runtime_error(self, judge, problem):
        source = "int main() { int* p = nullptr; *p = 1; return *p; }"
        assert run(judge, problem, source).tests()[0].verdict is Verdict.RE


class TestConfiguration:
    def test_time_limit_factor_loosens_the_budget(self, problem):
        source = """
            #include <cstdio>
            #include <ctime>
            int main() {
                clock_t start = clock();
                volatile long long x = 0;
                while ((double)(clock() - start) / CLOCKS_PER_SEC < 1.4) x++;
                printf("3\\n");
            }
        """
        code = textwrap.dedent(source)

        strict = Judge(config=JudgeConfig(time_limit_factor=1.0))
        assert strict.evaluate(problem, code).tests()[0].verdict is Verdict.TLE

        relaxed = Judge(config=JudgeConfig(time_limit_factor=3.0))
        assert relaxed.evaluate(problem, code).tests()[0].verdict is Verdict.OK
