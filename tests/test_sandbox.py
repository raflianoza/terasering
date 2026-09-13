"""Tests that exercise the sandbox directly, bypassing Judge.

Useful for checking things a score cannot reveal, such as which resource
limits actually reach the child process.
"""

import shutil
import textwrap

import pytest

from terasering import CPP, JudgeConfig, Limits, RlimitSandbox, Verdict
from terasering.compiler import Compiler

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("g++") is None, reason="requires g++"),
]

LIMITS = Limits(time_ms=1000, memory_mb=256, output_mb=8)


@pytest.fixture(scope="module")
def compiler():
    return Compiler(CPP)


@pytest.fixture
def empty_input(tmp_path):
    path = tmp_path / "empty.in"
    path.write_text("")
    return path


def execute(compiler, source, tmp_path, empty_input, limits=LIMITS):
    build = compiler.compile(textwrap.dedent(source), tmp_path / "build")
    assert build.succeeded, build.diagnostics
    sandbox = RlimitSandbox(JudgeConfig())
    return sandbox.execute(build.binary, empty_input, limits, tmp_path / "run")


def test_installed_limits_match_what_was_requested(compiler, tmp_path, empty_input):
    source = """
        #include <cstdio>
        #include <sys/resource.h>
        int main() {
            rlimit stack, address_space;
            getrlimit(RLIMIT_STACK, &stack);
            getrlimit(RLIMIT_AS, &address_space);
            printf("%lld %lld\\n",
                   (long long)(stack.rlim_cur >> 20),
                   (long long)(address_space.rlim_cur >> 20));
        }
    """
    execution = execute(compiler, source, tmp_path, empty_input)
    assert execution.verdict is Verdict.OK
    # The stack is deliberately raised to the memory limit; Linux defaults to
    # 8 MB and deep recursion routinely blows past it.
    assert execution.stdout().split() == ["256", "256"]


def test_environment_is_stripped(compiler, tmp_path, empty_input):
    source = """
        #include <cstdio>
        extern char** environ;
        int main() {
            int count = 0;
            for (char** e = environ; *e; ++e) count++;
            printf("%d\\n", count);
        }
    """
    execution = execute(compiler, source, tmp_path, empty_input)
    assert execution.stdout().strip() == "1"  # PATH only


def test_stderr_is_captured_not_discarded(compiler, tmp_path, empty_input):
    source = """
        #include <cstdio>
        int main() { fprintf(stderr, "diagnostic message\\n"); }
    """
    execution = execute(compiler, source, tmp_path, empty_input)
    assert "diagnostic message" in execution.stderr()


def test_child_processes_die_with_the_parent_on_timeout(
    compiler, tmp_path, empty_input
):
    # The parent exits immediately while its child hangs. Without killing the
    # whole process group, that orphan would be left running on the machine.
    source = """
        #include <unistd.h>
        int main() {
            if (fork() == 0) { sleep(300); }
            sleep(300);
        }
    """
    execution = execute(compiler, source, tmp_path, empty_input)
    assert execution.verdict is Verdict.TLE


def test_out_of_memory_wins_over_a_tight_clock(compiler, tmp_path, empty_input):
    # Allocating until refusal is slow, so a memory failure can land right at
    # the time limit. The verdict must still name the real cause.
    source = """
        #include <vector>
        int main() {
            std::vector<char> v;
            for (int i = 0; i < 4000; i++) v.resize(v.size() + (1 << 20), 1);
        }
    """
    execution = execute(
        compiler,
        source,
        tmp_path,
        empty_input,
        limits=Limits(time_ms=1, memory_mb=256, output_mb=8),
    )
    assert execution.verdict is Verdict.MLE


def test_cpu_time_does_not_accumulate_between_runs(compiler, tmp_path, empty_input):
    # If timing used getrusage(RUSAGE_CHILDREN), the second run would inherit
    # the first run's time.
    source = """
        #include <cstdio>
        int main() {
            volatile long long x = 0;
            for (long long i = 0; i < 50000000; i++) x += i;
            printf("%lld\\n", x);
        }
    """
    build = compiler.compile(textwrap.dedent(source), tmp_path / "build")
    sandbox = RlimitSandbox(JudgeConfig())

    first = sandbox.execute(build.binary, empty_input, LIMITS, tmp_path / "run1")
    second = sandbox.execute(build.binary, empty_input, LIMITS, tmp_path / "run2")

    assert second.cpu_time_ms < first.cpu_time_ms * 2
