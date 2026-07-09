---
type: concept
slug: gas-tank
title: Gas tank — the progress-metered infinite-loop guard
---
# Gas tank — the progress-metered infinite-loop guard

A per-run fuel counter that stops a [workflow](workflow.md) walk that never reaches a terminal
node — a `branch` cycle whose exit condition never trips — from spinning silently for the whole
unattended window a run is built to survive. One `_GasTank` instance is created per top-level
[`run`](workflow.md#execution) call and threaded through every nested
[flow](workflow.md#flows) sub-graph, so a non-progressing cycle anywhere in the graph — root or
flow — fails the run loudly instead of hanging it.

- code: `workhorse/workhorse/main.py::_GasTank`

## Sizing — one unit of progress, not the whole run

A flat step ceiling would either trip on a legitimately long run or let a genuine infinite loop
burn the whole unattended window silently. Instead the tank is **progress-metered**: it holds
`capacity` units, spends one per node step, and refuels back to full every time the walk makes
real forward progress. A healthy run — one that keeps advancing to new work — never runs dry no
matter how long it runs; a loop that reprocesses the same unit of work forever burns exactly one
tank and then halts.

- `capacity` — set from `_configured_gas()`: the `WORKHORSE_GAS` env var if it parses as a
  non-negative integer (an unparseable value is ignored, with a warning, and falls back to the
  default); default `5000` (`_DEFAULT_GAS`). `capacity <= 0` disables the guard entirely —
  `burn`/`refuel` become no-ops.

## `burn(node_id)`

Called once per node step, before the node runs.
1. If the guard is disabled (`capacity <= 0`), return immediately.
2. Append `node_id` to a bounded history (`deque(maxlen=2000)`) used only for the diagnostic below.
3. Decrement `gas`. If it drops below `0`, raise `OutOfGasError` naming `capacity`, the fact that
   no refuel happened, and the 8 hottest node ids in the recent history
   (`Counter(recent).most_common(8)`, formatted `<id>×<count>`) — pointing straight at the cycle
   whose exit branch never trips.

## `refuel(node_id, value)`

Called after a `script`/`call` node that declares a `refuel:` key, passing the node's own id and
the context value at that dot-path.
1. If the guard is disabled, return immediately.
2. Compare `value` against the last value seen for this `node_id` (a private sentinel `_UNSEEN`,
   distinct from every real value including `None`, marks "never visited" so the first visit
   always counts as progress).
3. If it changed (or this is the first visit), record the new value and reset `gas = capacity` — a
   new unit of work began (a new story, a new epic). An unchanged value (reprocessing the same
   unit) does not refuel, so a loop that never advances eventually runs the tank dry.

## `OutOfGasError`

A `RuntimeError` subclass; the only exception `_GasTank` raises.
[`run`](workflow.md#execution) catches it at the top level, terminates any in-flight agent
subprocess, marks the run `writer.finish(terminal="fail")`, and returns `1` — the run dir is left
intact for inspection, but resuming it would simply re-enter the same never-progressing cycle.

## Consumers

- [`run`](workflow.md#execution) — constructs the tank once per top-level call and passes it down
  into the node-walk.
- `_step_loop` (`workhorse/workhorse/main.py`) — calls `burn` for every node before it runs, and
  `refuel` after a `script`/`call` node that declares a `refuel:` key.
- `_run_flow` (`workhorse/workhorse/main.py`) — passes the same `tank` into a nested flow's node
  walk, so gas is shared, not reset, across a flow boundary.
