"""Compiling submitted source into an executable."""

from __future__ import annotations

import resource
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import JudgeConfig, Toolchain
from .errors import ToolchainError
from .models import CompileResult

BYTES_PER_MB = 1024 * 1024


@dataclass
class Compiler:
    """Wraps one toolchain together with its resource limits.

    The language standard is probed once and then remembered, since probing
    the compiler for every submission would be wasteful.
    """

    toolchain: Toolchain
    config: JudgeConfig = JudgeConfig()
    _standard: str | None = None

    @property
    def standard(self) -> str:
        if self._standard is None:
            self._standard = self._detect_standard()
        return self._standard

    def compile(self, source: str, workdir: Path) -> CompileResult:
        workdir.mkdir(parents=True, exist_ok=True)
        source_path = workdir / f"solution{self.toolchain.source_suffix}"
        binary_path = workdir / "solution"
        source_path.write_text(source)

        command = self.toolchain.command(self.standard, source_path, binary_path)

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.config.compile_timeout_s,
                preexec_fn=self._limit_compiler,
            )
        except subprocess.TimeoutExpired:
            # Happens with runaway template metaprogramming.
            return CompileResult(
                succeeded=False,
                binary=None,
                diagnostics=(
                    f"Compilation exceeded {self.config.compile_timeout_s:.0f}s "
                    f"and was stopped."
                ),
                command=command,
            )
        except FileNotFoundError:
            raise ToolchainError(
                f"compiler {self.toolchain.compiler!r} not found"
            ) from None

        diagnostics = process.stderr.strip()
        if process.returncode != 0 or not binary_path.exists():
            return CompileResult(False, None, diagnostics, command)

        # Warnings are carried along even on success.
        return CompileResult(True, binary_path, diagnostics, command)

    # -- internals -------------------------------------------------------

    def _limit_compiler(self) -> None:
        limit = self.config.compile_memory_mb * BYTES_PER_MB
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    def _detect_standard(self) -> str:
        """Pick the first standard the compiler actually understands."""
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / f"probe{self.toolchain.source_suffix}"
            probe.write_text("int main() { return 0; }\n")
            for standard in self.toolchain.standards:
                command = [
                    self.toolchain.compiler,
                    f"-std={standard}",
                    "-fsyntax-only",
                    str(probe),
                ]
                try:
                    process = subprocess.run(command, capture_output=True)
                except FileNotFoundError:
                    raise ToolchainError(
                        f"compiler {self.toolchain.compiler!r} not found"
                    ) from None
                if process.returncode == 0:
                    return standard

        raise ToolchainError(
            f"{self.toolchain.compiler} accepted none of: "
            f"{', '.join(self.toolchain.standards)}"
        )
