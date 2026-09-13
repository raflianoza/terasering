"""Reading problem definitions from disk.

Test cases are stored as plain files rather than database rows so they can be
edited in a text editor, tracked in git, and diffed when an answer key turns
out to be wrong.

    problems/1234B/
      meta.toml
      subtasks/
        01-small/
          01.in   01.out
        02-medium/
          01.in   01.out

meta.toml:

    cf_contest_id = 1234
    cf_index = "B"
    time_limit_ms = 2000
    memory_limit_mb = 256
    checker = "exact"          # or "float"

    [subtasks]
    "01-small" = 20
    "02-medium" = 30

    [checker_options]
    # eps = 1e-6               # only for the "float" checker
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .checkers import build_checker
from .errors import ProblemLoadError
from .models import TOTAL_POINTS, Limits, Problem, Subtask, TestCase

META_FILENAME = "meta.toml"
SUBTASKS_DIRNAME = "subtasks"

DEFAULT_TIME_LIMIT_MS = 2000
DEFAULT_MEMORY_LIMIT_MB = 256
DEFAULT_CHECKER = "exact"


def load_problem(path: str | Path, *, require_answers: bool = True) -> Problem:
    """Read one problem together with all of its test cases.

    Args:
        require_answers: insist that every input has a matching answer key.
            Turn it off when the keys are about to be generated, which is the
            one situation where their absence is expected rather than a fault.

    Raises:
        ProblemLoadError: the definition is incomplete or inconsistent.
    """
    root = Path(path)
    meta = _read_meta(root / META_FILENAME)

    problem = Problem(
        id=meta.get("id", root.name),
        limits=Limits(
            time_ms=int(meta.get("time_limit_ms", DEFAULT_TIME_LIMIT_MS)),
            memory_mb=int(meta.get("memory_limit_mb", DEFAULT_MEMORY_LIMIT_MB)),
        ),
        subtasks=_load_subtasks(root, meta, require_answers),
        checker=build_checker(
            meta.get("checker", DEFAULT_CHECKER),
            meta.get("checker_options"),
        ),
        root=root,
        cf_contest_id=meta.get("cf_contest_id"),
        cf_index=meta.get("cf_index"),
    )

    if problem.local_max > TOTAL_POINTS:
        raise ProblemLoadError(
            f"{root}: local subtasks total {problem.local_max} points, "
            f"which exceeds {TOTAL_POINTS}"
        )
    return problem


def _read_meta(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ProblemLoadError(f"{path} not found")
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ProblemLoadError(f"{path}: invalid TOML ({exc})") from None


def _load_subtasks(
    root: Path, meta: dict[str, Any], require_answers: bool
) -> tuple[Subtask, ...]:
    points_by_label: dict[str, int] = meta.get("subtasks", {})
    if not points_by_label:
        raise ProblemLoadError(f"{root/META_FILENAME}: [subtasks] table is empty")

    subtasks_dir = root / SUBTASKS_DIRNAME
    if not subtasks_dir.is_dir():
        raise ProblemLoadError(f"{subtasks_dir} not found")

    directories = sorted(p for p in subtasks_dir.iterdir() if p.is_dir())
    found_labels = {p.name for p in directories}

    # A points entry with no matching directory is nearly always a typo, and
    # silently lowers the maximum score if left alone.
    for label in points_by_label:
        if label not in found_labels:
            raise ProblemLoadError(
                f"{root/META_FILENAME} lists subtask {label!r} "
                f"but no such directory exists"
            )

    subtasks = []
    for directory in directories:
        label = directory.name
        if label not in points_by_label:
            raise ProblemLoadError(
                f"subtask {label!r} has no points in {root/META_FILENAME}"
            )
        subtasks.append(
            Subtask(
                label=label,
                points=int(points_by_label[label]),
                tests=_load_tests(directory, require_answers),
            )
        )
    return tuple(subtasks)


def _load_tests(directory: Path, require_answers: bool) -> tuple[TestCase, ...]:
    tests = []
    for input_path in sorted(directory.glob("*.in")):
        expected_path = input_path.with_suffix(".out")
        if require_answers and not expected_path.is_file():
            raise ProblemLoadError(
                f"{input_path} has no matching {expected_path.name}"
            )
        tests.append(TestCase(input_path.stem, input_path, expected_path))

    if not tests:
        raise ProblemLoadError(f"subtask {directory.name!r} has no test cases")
    return tuple(tests)