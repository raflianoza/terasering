# terasering

A partial-point judge for ICPC-style Codeforces problems.

In ICPC-style contests, a problem is usually pass-or-fail: either your solution is accepted or it gets nothing. `terasering` adds a middle ground.

You can prepare small local test cases grouped into subtasks, then use an accepted Codeforces submission as the final full-score tier. This makes it possible to give meaningful partial credit without having to recreate the full Codeforces test set yourself.

The name comes from *terasering*, or terraced rice fields: each subtask is another step upward.

```bash
teras gen problems/1234B model.cpp

teras run problems/1234B student.cpp --cf-handle alice
```

Example output:

```text
[PASS] 01-small   20/20
[FAIL] 02-medium   0/30
         01       TLE   2530 ms    12 MB

local score : 20/50
peak time   : 2530 ms
codeforces  : ACCEPTED - found submission 285736291 (342 ms, 8 MB)
final score : 100/100

[instructor review] TLE: Ran out of time here only. Usually just a slower
machine rather than a problem with the setup.
```

That last line is the point of the tool. The submission is worth full marks
because Codeforces accepted it, but the local run still reports what happened
and why the two disagree.

## Install

```bash
pip install -e .
```

`terasering` requires:

* Linux
* Python 3.11+
* `g++` 13 or newer for C++23

The built-in sandbox relies on `resource.setrlimit` and `os.wait4`, so it is designed to run on Linux.

For C++, the compiler first tries `c++23`, then falls back to `c++2b`, and finally `c++17` if necessary.

If you are on macOS or Windows, use the included Docker setup:

```bash
docker build -t terasering .
docker run --rm -it -v "$PWD":/work terasering
```

The package itself uses only the Python standard library.

## How scoring works

The scoring rule is intentionally simple:

```text
score = 100                   if accepted on Codeforces
      = sum of local subtasks otherwise
```

Local tests are meant to separate solution quality rather than reproduce the entire Codeforces judge.

For example, you might use small handcrafted cases to distinguish:

* an `O(n³)` solution,
* an `O(n²)` solution,
* and the intended `O(n log n)` solution.

You do not need to build huge local stress tests just to represent the full constraints. Codeforces already has those.

Each local subtask is all-or-nothing. If one test inside a subtask fails, the entire subtask receives zero points.

The local score is always preserved. If a submission fails some local tests but is verified as accepted on Codeforces, the final score becomes `100`, while `diagnose()` reports the disagreement.

This is useful because, in practice, an accepted Codeforces solution failing locally often means the local answer key is wrong rather than the contestant's solution.

## Commands

### `teras run`

Run and score a submission:

```bash
teras run problems/1234B solution.cpp
```

Give a handle and `terasering` finds that person's accepted submission for the problem by itself:

```bash
teras run problems/1234B solution.cpp --cf-handle alice
```

It searches their submission history newest first, so a later fix counts rather than an earlier failed attempt. If you would rather check one specific submission, name it:

```bash
teras run problems/1234B solution.cpp \
  --cf-handle alice \
  --cf-submission 285736291
```

| Option               | Description                                                           |
| -------------------- | --------------------------------------------------------------------- |
| `--cf-handle HANDLE` | Look up this handle's accepted submission for the problem             |
| `--cf-submission ID` | Check one specific submission instead of searching for it             |
| `--cf-ac`            | Treat the solution as accepted on Codeforces without querying the API |
| `--all-tests`        | Keep running tests after a subtask has already failed                 |
| `--time-limit MS`    | Override the time limit from `meta.toml`                              |
| `--time-factor X`    | Multiply the configured time limit                                    |
| `--show-warnings`    | Show compiler warnings                                                |

Codeforces verification does not require login credentials.

When a submission id is given explicitly, `terasering` verifies four things:

1. the submission exists,
2. it belongs to the claimed handle,
3. it was submitted to the expected problem,
4. and its verdict is `OK`.

Checking only the verdict would not be enough, since otherwise someone could simply provide the ID of an unrelated accepted submission.

The verification uses the Codeforces API rather than scraping webpages, so changes to the website layout do not affect it.

### `teras gen`

Writing `.out` files manually is tedious and easy to get wrong.

If you already have a trusted model solution, `terasering` can generate the answer keys automatically:

```bash
teras gen problems/1234B model.cpp
```

Options:

| Option            | Description                                        |
| ----------------- | -------------------------------------------------- |
| `--force`         | Overwrite answer keys that already exist           |
| `--subtask LABEL` | Generate keys only for one subtask                 |
| `--dry-run`       | Show what would be generated without writing files |
| `--time-factor X` | Multiply time limits for the current machine       |

Existing answer keys are left untouched unless `--force` is used.

Generation is also fail-safe: if the model solution crashes or times out, no answer key is written for that run.

Of course, `terasering` cannot know whether your model solution is actually correct. It only knows that the program ran successfully.

For that reason, it is a good idea to get the model solution accepted on Codeforces before using it to generate official keys.

## Problem structure

A problem directory looks like this:

```text
problems/1234B/
  meta.toml
  subtasks/
    01-small/
      01.in
      01.out
      02.in
      02.out

    02-medium/
      01.in
      01.out
```

The corresponding `meta.toml` might be:

```toml
id = "1234B"

cf_contest_id = 1234
cf_index = "B"

time_limit_ms = 2000
memory_limit_mb = 256

checker = "exact"

[subtasks]
"01-small" = 20
"02-medium" = 30
```

The Codeforces contest ID comes from the problem URL:

```text
/contest/1234/problem/B
```

Subtask directory names must match the keys under `[subtasks]` exactly.

Every `.in` file must also have a matching `.out` file.

Both conditions are checked while loading the problem. A typo here would otherwise silently reduce the maximum available score, which is usually not what you want.

### Floating-point answers

For problems with decimal output, use the float checker:

```toml
checker = "float"

[checker_options]
eps = 1e-6
```

Test cases are stored as normal files rather than rows inside some custom database or table format.

That keeps them easy to:

* edit manually,
* inspect,
* version with Git,
* and review through normal diffs.

## Using it as a library

The CLI is only a thin layer over the Python API.

```python
from terasering import (
    CodeforcesClient,
    Judge,
    diagnose,
    effective_score,
    load_problem,
)

problem = load_problem("problems/1234B")

outcome = Judge().evaluate(problem, source)

claim = CodeforcesClient().verify(
    "alice",
    285736291,
    problem,
)

print(effective_score(outcome.local_score, claim.accepted))
print(diagnose(outcome, claim.accepted))
```

## Project structure

The package is split into small modules with fairly clear responsibilities:

| Module         | Responsibility                                          |
| -------------- | ------------------------------------------------------- |
| `models.py`    | Shared data structures                                  |
| `config.py`    | `JudgeConfig`, `Toolchain`, and configurable values     |
| `errors.py`    | Exception hierarchy                                     |
| `checkers.py`  | Output checkers and checker registry                    |
| `sandbox.py`   | Sandbox protocol and the built-in rlimit implementation |
| `compiler.py`  | Compilation and C++ standard detection                  |
| `loader.py`    | Loading problems from disk                              |
| `judge.py`     | Compile, execute, and score submissions                 |
| `generator.py` | Generate answer keys from a model solution              |
| `scoring.py`   | Pure scoring and diagnosis logic                        |
| `cf.py`        | Codeforces submission verification                      |
| `cli.py`       | Implementation of `teras run` and `teras gen`           |

`models.py` intentionally does not import anything else from the package, which helps keep dependencies between modules predictable.

## Extension points

A few parts of the system are intentionally easy to replace.

### Sandbox

The default sandbox uses Linux resource limits and requires almost no setup.

If you need stronger isolation, you can implement the `Sandbox` protocol using something like [`isolate`](https://github.com/ioi/isolate):

```python
# IsolateSandbox is yours to write; the protocol is defined in sandbox.py
judge = Judge(sandbox=IsolateSandbox())
```

You should strongly consider this for environments where submitted code cannot be trusted.

### Checker

To add another checker, implement a class with an `accepts` method and register it in `CHECKERS`.

Problems can then select it from `meta.toml`:

```toml
checker = "my_checker"
```

### Toolchain

Language support is configured through `Toolchain` objects in `config.py`.

Adding another compiled language is mostly a matter of adding another toolchain configuration.

Interpreted languages will usually need their own time-limit multiplier as well.

## Choosing time limits

Your computer is not a Codeforces judge machine.

If you are running inside a VM or container, the performance difference may be even larger.

For local subtasks, it is usually better to start with a relaxed multiplier:

```bash
teras run problems/1234B solution.cpp --time-factor 3
```

A practical way to calibrate it is:

* the intended solution should comfortably pass,
* a clearly slower solution should still fail.

The goal is for partial points to reflect **algorithmic complexity**, not tiny differences in compiler optimization or processor speed.

Once you find a reasonable multiplier for the machine, you can configure it through:

```python
JudgeConfig(time_limit_factor=...)
```

## Tests

Install the development dependencies:

```bash
pip install -e ".[dev]"
```

Run the full suite:

```bash
pytest
```

There are currently 98 tests.

To skip tests that actually invoke the compiler:

```bash
pytest -m "not slow"
```

The slow tests compile and execute real C++ programs.

They cover cases such as:

* CPU-limit TLE,
* wall-clock TLE,
* MLE,
* OLE,
* stack limits,
* and orphaned child processes.

Codeforces-related tests use a fake transport, so the test suite does not make real network requests.

## Limitations

`terasering` currently assumes that each problem has one unique correct output.

That means it does **not** currently support:

* multiple-answer problems,
* special judges for constructive output,
* or interactive problems.

The built-in sandbox is meant to contain buggy or resource-heavy submissions, not malicious ones.

Submitted programs can still potentially read files available to the judging process or access the network.

If you are running untrusted submissions, use stronger isolation.

Timing is also intended to be measured with one evaluation running at a time. Running several submissions concurrently can make execution times interfere with each other and make subtask boundaries unreliable.

Verified Codeforces claims are currently not cached.

Because the Codeforces API is rate-limited, the client spaces requests accordingly. In a larger deployment, a storage layer should cache settled submission claims rather than verifying the same submission repeatedly.

More detail on the design decisions behind the project is available in [`docs/design.md`](docs/design.md).

## License

MIT