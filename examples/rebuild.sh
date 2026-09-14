#!/usr/bin/env bash
# Rebuilds the example problem shipped with the repo.
# Run once from the repository root, then commit problems/example-spread/.
set -euo pipefail

rm -rf problems/example-spread

teras new problems/example-spread \
  --subtasks small:20,large:30 \
  --time-limit 1000

cd problems/example-spread/subtasks

# Small cases, written by hand. Each one targets a specific mistake.
printf '5\n1 5 3 9 2\n'               > 01-small/01.in   # ordinary case
printf '1\n42\n'                      > 01-small/02.in   # single element
printf '4\n7 7 7 7\n'                 > 01-small/03.in   # all equal
printf '3\n-5 0 5\n'                  > 01-small/04.in   # negative values
printf '2\n-1000000000 1000000000\n'  > 01-small/05.in   # extreme range

# Large case, generated. Big enough to separate O(n) from O(n^2).
python3 - <<'PY'
import random
random.seed(2026)
n = 100000
values = [random.randint(-10**9, 10**9) for _ in range(n)]
with open("02-large/01.in", "w") as f:
    f.write(f"{n}\n" + " ".join(map(str, values)) + "\n")
PY

cd ../../..
teras gen problems/example-spread examples/spread_linear.cpp
