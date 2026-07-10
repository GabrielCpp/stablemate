---
type: concept
slug: builtins-registry
title: The builtins registry
---
# The builtins registry

The lookup table [`run_call`](run-call.md) dispatches through: a plain `dict[str, Any]` mapping a
[`call`](../workflow-format.md#call) node's `fn` name to a plain Python callable. Every entry is a
small, pure, synchronous function — no LLM call, no subprocess, no I/O — for cheap in-graph
bookkeeping (counters, placeholder values) that doesn't warrant a full [script](run-script.md) node.

- code: `workhorse/workhorse/builtins.py::REGISTRY`

## `REGISTRY: dict[str, Any]`

- **Keys:** the builtin's name, as referenced by a `call` node's `fn:` field.
- **Values:** a callable taking the node's rendered `args` as keyword arguments and returning a
  single JSON-serializable value (the `raw_result` [`run_call`](run-call.md#algorithm) wraps per
  output spec).
- **Members:**
  - `"incr"` → [`incr`](#incrvalue0---int)
  - `"seed"` → [`seed`](#seedkwargs---int)

## `incr(value=0) -> int`

Increments a counter by one, tolerating the value arriving as a string (workflow context values are
always strings once rendered through Jinja2).

- **Input:** `value: Any` — default `0`.
- **Output:** `int(float(value)) + 1`.
- **Fallback:** any `TypeError`/`ValueError` from the `int(float(value))` conversion (missing arg,
  empty string, non-numeric string) is swallowed and the function returns `1` — i.e. "no prior
  count" is treated the same as "count is zero".

## `seed(**kwargs) -> int`

Always returns `0`, ignoring every keyword argument. Used to reset a counter to a known value from
a `call` node without needing a dedicated "reset" code path — the same `outputs`/`wrap` shape as
`incr` applies, so a workflow can swap `fn: incr` for `fn: seed` without touching the node's
`args`/`outputs`.

- **Input:** any keyword arguments (accepted, unused).
- **Output:** `0`.

## Consumers

- [`run_call`](run-call.md#algorithm) — the only reader, once per `call` node: looks up `node.fn` in
  `REGISTRY`, raising `RuntimeError` if the name isn't a key, then invokes the resolved callable with
  the node's rendered `args`.
