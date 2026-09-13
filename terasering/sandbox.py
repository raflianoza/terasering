"""Running untrusted binaries under time and memory limits.

The reasoning behind rlimit, the timing method, and the way MLE is told apart
from RE is documented in docs/design.md.

Requires Linux. Use WSL2 on Windows.
"""

from __future__ import annotations

import os
import resource
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import JudgeConfig
from .errors import SandboxError
from .models import Execution, Limits, Verdict

BYTES_PER_MB = 1024 * 1024

#: Refusing to run elsewhere is deliberate. The failures on other platforms are
#: silent rather than loud: macOS does not enforce RLIMIT_AS, reports ru_maxrss
#: in bytes instead of kilobytes, and cannot link statically. A judge that
#: quietly reports wrong verdicts is worse than one that will not start.
_SUPPORTED_PLATFORM = "linux"

#: Messages emitted when an allocation is refused. See docs/design.md for why
#: MLE detection relies on stderr rather than on maxrss.
_OUT_OF_MEMORY_MARKERS = (
    "bad_alloc",
    "Cannot allocate memory",
    "out of memory",
)


class Sandbox(Protocol):
    """Runs one binary against one input file.

    An alternative implementation, such as a wrapper around `isolate`, only
    needs to provide this method; nothing else in the system changes.
    """

    def execute(
        self,
        binary: Path,
        input_path: Path,
        limits: Limits,
        workdir: Path,
    ) -> Execution: ...


@dataclass(frozen=True)
class RlimitSandbox:
    """Sandbox built on Linux rlimits.

    Adequate for buggy or wasteful code, but not isolation against code that
    is actively hostile: the process can still read files on the server and
    reach the network.
    """

    config: JudgeConfig = JudgeConfig()

    def __post_init__(self) -> None:
        if not sys.platform.startswith(_SUPPORTED_PLATFORM):
            raise SandboxError(
                f"RlimitSandbox requires Linux, but this is {sys.platform!r}. "
                f"Run the judge in a Linux container or VM; see the Dockerfile."
            )

    def execute(
        self,
        binary: Path,
        input_path: Path,
        limits: Limits,
        workdir: Path,
    ) -> Execution:
        workdir.mkdir(parents=True, exist_ok=True)
        stdout_path = workdir / "stdout.txt"
        stderr_path = workdir / "stderr.txt"

        with (
            open(input_path, "rb") as stdin,
            open(stdout_path, "wb") as stdout,
            open(stderr_path, "wb") as stderr,
        ):
            process = subprocess.Popen(
                [str(binary)],
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                cwd=str(workdir),
                env=dict(self.config.env),
                preexec_fn=self._apply_limits(limits),
            )
            wait_status, usage, timed_out = self._wait(process, limits)

        cpu_time_ms = int((usage.ru_utime + usage.ru_stime) * 1000)
        memory_kb = int(usage.ru_maxrss)
        exit_code, term_signal = _decode_wait_status(wait_status)

        verdict = self._classify(
            limits=limits,
            cpu_time_ms=cpu_time_ms,
            exit_code=exit_code,
            term_signal=term_signal,
            timed_out=timed_out,
            output_size=stdout_path.stat().st_size,
            stderr_text=_tail(stderr_path),
        )

        return Execution(
            verdict=verdict,
            cpu_time_ms=cpu_time_ms,
            memory_kb=memory_kb,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            exit_code=exit_code,
            signal=term_signal,
        )

    # -- internals -------------------------------------------------------

    def _apply_limits(self, limits: Limits):
        """Build the preexec callback that installs rlimits in the child."""
        cpu_seconds = self.config.cpu_limit_s(limits.time_ms)
        memory_bytes = limits.memory_mb * BYTES_PER_MB
        output_bytes = limits.output_mb * BYTES_PER_MB

        def apply() -> None:
            os.setsid()  # own process group, so the whole tree can be killed
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            resource.setrlimit(resource.RLIMIT_STACK, (memory_bytes, memory_bytes))
            resource.setrlimit(resource.RLIMIT_FSIZE, (output_bytes, output_bytes))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        return apply

    def _wait(self, process: subprocess.Popen, limits: Limits):
        """Wait for the process, killing it if it outlives the wall-clock budget.

        os.wait4 is used so the resource usage returned belongs to this process
        alone.
        """
        timed_out = False

        def on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            _kill_process_group(process.pid)

        timeout = self.config.wall_clock_timeout_s(limits.time_ms)
        watchdog = threading.Timer(timeout, on_timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            _, wait_status, usage = os.wait4(process.pid, 0)
        finally:
            watchdog.cancel()
            # Tell Popen its child is already reaped so it does not wait again
            # when the object is discarded.
            process.returncode = 0

        return wait_status, usage, timed_out

    def _classify(
        self,
        *,
        limits: Limits,
        cpu_time_ms: int,
        exit_code: int | None,
        term_signal: int | None,
        timed_out: bool,
        output_size: int,
        stderr_text: str,
    ) -> Verdict:
        if term_signal == signal.SIGXFSZ or output_size > limits.output_mb * BYTES_PER_MB:
            return Verdict.OLE

        if timed_out or term_signal == signal.SIGXCPU:
            return Verdict.TLE

        # A refused allocation is a memory verdict however long it took to get
        # there. This check precedes the time checks because failing to
        # allocate is itself slow, so a near-limit run would otherwise be
        # reported as a timeout and hide the real cause.
        if term_signal is not None and _looks_out_of_memory(stderr_text):
            return Verdict.MLE

        # Killed by our watchdog, racing the timed_out flag, or by the OOM killer.
        if term_signal == signal.SIGKILL:
            return Verdict.TLE

        # A process may exit cleanly yet still land just above the limit.
        if cpu_time_ms > limits.time_ms:
            return Verdict.TLE

        if term_signal is not None:
            return Verdict.RE

        if exit_code != 0:
            return Verdict.RE

        return Verdict.OK


def _decode_wait_status(wait_status: int) -> tuple[int | None, int | None]:
    if os.WIFSIGNALED(wait_status):
        return None, os.WTERMSIG(wait_status)
    return os.WEXITSTATUS(wait_status), None


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass  # already gone


def _looks_out_of_memory(text: str) -> bool:
    return any(marker in text for marker in _OUT_OF_MEMORY_MARKERS)


def _tail(path: Path, limit: int = 4096) -> str:
    if not path.exists():
        return ""
    return path.read_text(errors="replace")[-limit:]
