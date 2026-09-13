# Design notes

This document holds the reasoning that cannot be read off the code itself.
The code says *what*; this page says *why*.

## Scoring rule

```
score = 100                     if accepted on Codeforces
      = sum of local subtasks   otherwise
```

An AC on Codeforces is treated as a final subtask with no constraints. The
most useful consequence: because the full constraints are delegated upstream,
local test cases do not need to be large. They only need to separate O(n³)
from O(n²) from O(n log n), which means they are small enough to write by
hand. The large ones come free from Codeforces.

The raw local score is stored and never overwritten. Disagreement between the
two is valuable signal for an instructor, surfaced by `scoring.diagnose()`.

Subtasks are all-or-nothing, following IOI convention. One failed test case
forfeits the whole subtask. The rule was chosen because it is unambiguous and
easy to explain to participants.

### An AC on Codeforces is not proof of correctness

Weak test data is real, especially on older problems. It is possible for a
small hand-written test case to catch a bug that Codeforces missed, after
which the override rule papers over it as full marks.

For a teaching tool, trusting Codeforces is a reasonable trade. That is
precisely why the local result is kept and why "AC upstream but WA locally"
still appears in the instructor review: sometimes the answer is not "my answer
key is wrong" but "the official tests are weak".

## Time limits

The machine running this judge is not a Codeforces machine. A solution that
finishes there in 900 ms may time out here, or the reverse.

`JudgeConfig.time_limit_factor` multiplies every problem's time limit. Start
loose (2–3×) so partial points measure algorithmic complexity rather than
implementation constants. A tight limit turns the exercise into constant-factor
optimisation, which is usually not the teaching goal.

## Sandbox

The built-in implementation uses rlimits, a plain Linux feature requiring no
installation. It is **adequate** for buggy or wasteful code, but it is **not**
isolation against hostile code: the process can still read files on the server
and reach the network.

For real isolation, write a class satisfying the `Sandbox` protocol that wraps
[`isolate`](https://github.com/ioi/isolate) and pass it via
`Judge(sandbox=...)`. Nothing else changes.

### Why `os.wait4` rather than `subprocess.run`

`resource.getrusage(RUSAGE_CHILDREN)` accumulates across every child ever
reaped, so its numbers are contaminated by earlier runs. `os.wait4()` returns
resource usage for a single process.

The consequence is that `Popen` must not reap its own child first, so
`process.returncode` is assigned manually after `wait4` to stop `Popen` from
waiting again when the object is discarded.

### Why two layers of timeout

`RLIMIT_CPU` has whole-second granularity, too coarse to rely on alone, and it
never fires for a process that waits without consuming CPU — `sleep()`, or
blocking on input that never arrives.

Hence both: `RLIMIT_CPU` as a hard backstop, and a wall-clock watchdog
(`wall_clock_factor × limit + grace`) that kills the process group.

### Why `RLIMIT_STACK` is raised to the memory limit

Linux defaults to 8 MB, and deep recursion — DFS, divide and conquer —
routinely blows past it. Without this, correct solutions would draw spurious
runtime errors. Codeforces likewise ties the stack to the memory limit.

### Why `RLIMIT_NPROC` is not set

It is a per-user limit, not a per-process one. Setting it risks locking out
the account running the judge itself.

### Why MLE is detected from stderr

`RLIMIT_AS` caps **virtual** address space. A single large allocation can be
refused while **resident** memory sits far below the limit, which makes
`ru_maxrss` useless as a signal.

What is reliable is the `std::bad_alloc` message printed when an allocation is
refused. That is why stderr is captured to a file rather than discarded.

## Output comparison

Every checker ignores whitespace entirely, so trailing newlines and doubled
spaces never cause a spurious WA.

`ExactChecker` suffices for unique-answer problems, which is the current scope.
Problems with multiple valid answers and interactive problems are unsupported;
both can be added as new `Checker` implementations without touching any other
module.

## Compilation

`g++ -std=c++23 -O2 -static`.

- `-O2` matches Codeforces. Without it code runs 2–5× slower and produces
  spurious timeouts.
- `-static` avoids shared library trouble should this move to isolate.
- `-DLOCAL` is deliberately **absent**, so `#ifdef LOCAL` debug blocks vanish
  exactly as they do on Codeforces.

The language standard is probed once and remembered. GCC 11–12 spell C++23 as
`c++2b`; without a fallback, a machine with an older compiler would reject
every submission with a confusing message.

Compilation is capped in both time and memory because runaway template
metaprogramming can hang the compiler.

## Test case storage

Test cases live in plain files rather than a database. They can be edited in a
text editor, tracked in git, and diffed when an answer key turns out wrong —
three things that all disappear once the content moves into a table.

## Concurrency

`Judge` is safe to reuse but is not designed to be shared across threads. This
is not a shortcoming: evaluations should run one at a time, because two
processes running concurrently on the same machine make timing measurements
interfere and turn TLE results inconsistent.

When the web layer arrives, use a single queue with a single worker.
