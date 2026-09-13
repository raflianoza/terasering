"""Judge settings and toolchain definitions.

Every number worth tuning lives here rather than being scattered as constants
across the other modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

_MINIMAL_ENV: Mapping[str, str] = MappingProxyType({"PATH": "/usr/bin:/bin"})


@dataclass(frozen=True)
class Toolchain:
    """How to turn source code into an executable.

    `standards` is ordered from most preferred to fallback. GCC 11-12 spell
    C++23 as 'c++2b', so without a fallback any machine with an older compiler
    would reject every submission.
    """

    name: str
    compiler: str
    source_suffix: str
    standards: tuple[str, ...]
    flags: tuple[str, ...] = ()

    def command(self, standard: str, source: Path, binary: Path) -> tuple[str, ...]:
        return (
            self.compiler,
            f"-std={standard}",
            *self.flags,
            "-o",
            str(binary),
            str(source),
        )


#: -DLOCAL is deliberately absent so results match Codeforces.
#: -static avoids shared library trouble should this move to isolate later.
CPP = Toolchain(
    name="cpp",
    compiler="g++",
    source_suffix=".cpp",
    standards=("c++23", "c++2b", "c++17"),
    flags=("-O2", "-static"),
)

TOOLCHAINS: dict[str, Toolchain] = {CPP.name: CPP}


@dataclass(frozen=True)
class JudgeConfig:
    """Operational parameters for the judge.

    time_limit_factor multiplies every problem's time limit. This machine is
    not a Codeforces machine, so raise it when correct solutions start hitting
    spurious TLEs.
    """

    time_limit_factor: float = 1.0
    output_limit_mb: int = 64

    compile_timeout_s: float = 15.0
    compile_memory_mb: int = 2048

    #: Wall-clock budget is time_limit * factor + grace. Needed because a CPU
    #: limit never fires for a process that waits without consuming CPU.
    wall_clock_factor: float = 2.0
    wall_clock_grace_s: float = 1.0

    #: Slack granted to RLIMIT_CPU above the wall-clock budget, in whole seconds.
    cpu_limit_grace_s: int = 2

    env: Mapping[str, str] = field(default=_MINIMAL_ENV)

    def wall_clock_timeout_s(self, time_limit_ms: int) -> float:
        return (time_limit_ms * self.wall_clock_factor) / 1000 + self.wall_clock_grace_s

    def cpu_limit_s(self, time_limit_ms: int) -> int:
        return int(time_limit_ms / 1000) + self.cpu_limit_grace_s
