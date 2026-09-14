"""Creating a new problem directory.

Setting a problem up by hand means nested mkdirs and a meta.toml whose subtask
keys have to match the directory names exactly. A typo there is only caught
later, when loading fails or the maximum score turns out lower than intended.

    teras new problems/474B --cf 474/B --subtasks small:20,medium:30
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import TeraseringError
from .models import TOTAL_POINTS

DEFAULT_SUBTASKS = "small:20,medium:30"
DEFAULT_TIME_LIMIT_MS = 2000
DEFAULT_MEMORY_LIMIT_MB = 256
DEFAULT_CHECKER = "exact"

#: Labels become directory names, so anything a path would choke on is out.
_VALID_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: Labels are numbered on creation because subtasks run in directory order.
_ALREADY_NUMBERED = re.compile(r"^\d+[-_]")

_URL_PATTERNS = (
    re.compile(r"(?:contest|gym)/(\d+)/problem/([A-Za-z]\d*)", re.I),
    re.compile(r"problemset/problem/(\d+)/([A-Za-z]\d*)", re.I),
)
_SHORT_PATTERN = re.compile(r"^(\d+)[/\-_ ]?([A-Za-z]\d*)$")


@dataclass(frozen=True)
class SubtaskSpec:
    label: str
    points: int


def parse_problem_ref(reference: str) -> tuple[int, str]:
    """Read a contest id and index out of whatever form is at hand.

    Accepts a full problem URL as well as the shorthands people actually type,
    so there is no need to work out which half of the URL is which.

        474/B  474B  https://codeforces.com/contest/474/problem/B
    """
    text = reference.strip()

    for pattern in _URL_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(1)), match.group(2).upper()

    match = _SHORT_PATTERN.match(text)
    if match:
        return int(match.group(1)), match.group(2).upper()

    raise TeraseringError(
        f"could not read a contest id and index from {reference!r}; "
        f"try 474/B or a problem URL"
    )


def parse_subtasks(spec: str) -> tuple[SubtaskSpec, ...]:
    """Parse `small:20,medium:30` into labels and points."""
    subtasks = []
    for index, chunk in enumerate(spec.split(","), start=1):
        chunk = chunk.strip()
        if not chunk:
            continue

        label, separator, points = chunk.partition(":")
        label = label.strip()
        if not separator:
            raise TeraseringError(
                f"subtask {label!r} has no points; write it as {label}:20"
            )
        if not _VALID_LABEL.match(label):
            raise TeraseringError(f"subtask label {label!r} is not a usable name")
        try:
            value = int(points)
        except ValueError:
            raise TeraseringError(
                f"points for subtask {label!r} must be a whole number, "
                f"got {points.strip()!r}"
            ) from None
        if value <= 0:
            raise TeraseringError(f"subtask {label!r} must be worth more than zero")

        if not _ALREADY_NUMBERED.match(label):
            label = f"{index:02d}-{label}"
        subtasks.append(SubtaskSpec(label, value))

    if not subtasks:
        raise TeraseringError("no subtasks given")

    total = sum(s.points for s in subtasks)
    if total > TOTAL_POINTS:
        raise TeraseringError(
            f"subtasks total {total} points, which exceeds {TOTAL_POINTS}"
        )
    return tuple(subtasks)


def create_problem(
    path: str | Path,
    *,
    subtasks: str = DEFAULT_SUBTASKS,
    reference: str | None = None,
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
    checker: str = DEFAULT_CHECKER,
) -> tuple[Path, tuple[SubtaskSpec, ...]]:
    """Write a problem skeleton: meta.toml plus one directory per subtask.

    Raises:
        TeraseringError: the target already exists, or an argument is unusable.
            Refusing to touch an existing directory matters here because this
            command writes meta.toml, and overwriting one would discard the
            points already assigned.
    """
    root = Path(path)
    if root.exists():
        raise TeraseringError(f"{root} already exists")

    parsed = parse_subtasks(subtasks)
    ids = parse_problem_ref(reference) if reference else None

    for subtask in parsed:
        (root / "subtasks" / subtask.label).mkdir(parents=True)

    (root / "meta.toml").write_text(_render_meta(
        problem_id=root.name,
        ids=ids,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
        checker=checker,
        subtasks=parsed,
    ))
    return root, parsed


def _render_meta(
    *,
    problem_id: str,
    ids: tuple[int, str] | None,
    time_limit_ms: int,
    memory_limit_mb: int,
    checker: str,
    subtasks: tuple[SubtaskSpec, ...],
) -> str:
    lines = [f'id = "{problem_id}"']

    if ids is None:
        lines += [
            "",
            "# Needed to verify Codeforces submissions. From the problem URL:",
            "#   /contest/1234/problem/B",
            "# cf_contest_id = 1234",
            '# cf_index = "B"',
        ]
    else:
        contest_id, index = ids
        lines += ["", f"cf_contest_id = {contest_id}", f'cf_index = "{index}"']

    lines += [
        "",
        f"time_limit_ms = {time_limit_ms}",
        f"memory_limit_mb = {memory_limit_mb}",
        "",
        f'checker = "{checker}"',
        "",
        "[subtasks]",
    ]
    lines += [f'"{s.label}" = {s.points}' for s in subtasks]
    return "\n".join(lines) + "\n"