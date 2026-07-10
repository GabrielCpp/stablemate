---
type: concept
slug: evaluate-branch
title: evaluate — resolve a branch node's route
---
# evaluate — resolve a branch node's route

The handler the [node-walk engine](workflow.md#node-walk-engine)'s `BranchNode` branch calls:
resolves a `branch` node's `next` by matching a context dot-path against its `cases` (equality) or
`conditions` (numeric/string comparisons), falling back to `default` — and, per the
[unattended-resilience guardrail](workflow.md#execution), routes an **unresolvable** path to
`default` too instead of raising, since an upstream step returning an unexpected shape must not
crash a week-long run.

- code: `workhorse/workhorse/runner/branch.py::evaluate`
- verify: `workhorse/tests/test_branch_guardrail.py::test_resolved_value_matches_case`,
  `workhorse/tests/test_branch_guardrail.py::test_missing_key_routes_to_default`,
  `workhorse/tests/test_branch_guardrail.py::test_non_dict_intermediate_routes_to_default`,
  `workhorse/tests/test_branch_guardrail.py::test_missing_top_level_key_routes_to_default`,
  `workhorse/tests/test_branch_guardrail.py::test_unresolvable_without_default_raises_actionable_error`,
  `workhorse/tests/test_branch_guardrail.py::test_resolved_value_no_match_no_default_still_raises`,
  `workhorse/tests/test_branch_guardrail.py::test_conditions_still_evaluated_for_resolved_value`

## Contract

- **Input:** `node: BranchNode` (the [`branch` node](../workflow-format.md#branch) — `path`, `cases`,
  `conditions`, `default`), `context: WorkflowContext`.
- **Output:** `tuple[str, Any]` = `(next_node_id, resolved_value)`. `next_node_id` is always one of
  the ids the `BranchNode`'s edges validated against the graph (a `cases` value, a `conditions[].next`,
  or `default`). `resolved_value` is the dot-path's resolved value, or `None` when the path was
  unresolvable and the node fell back to `default` — both written verbatim into the node's
  [`branch.json`](artifact-writer.md#write_branchnode_id-path-value-next_node) artifact by the
  [node-walk engine](workflow.md#execution) (`main.py::_step_loop`, which calls this and forwards
  the pair straight into `ArtifactWriter.write_branch`).
- **Errors:** raises `RuntimeError` in the two cases described in step 1 and step 4 of the
  algorithm below (unresolvable path with no `default`; resolved value matches nothing and no
  `default`). Raises `ValueError` if a `conditions[].op` isn't one of `_OPS`'s six keys — dead in
  practice since `BranchCondition.op` is a `Literal` Pydantic validates at load time
  ([`workflow-format.md`](../workflow-format.md#branch)), kept as a defensive guard against a
  hand-built `BranchNode`.
- Reads the node's target path via
  [`context.get_dotpath`](workflow-context.md#get_dotpathpath-default_missing---any) — `evaluate` is
  its sole consumer among the node runners. Calls no other module.

## Algorithm

1. **Resolve the path.** `value = context.get_dotpath(node.path, default=_UNRESOLVED)`, where
   `_UNRESOLVED` is a private `object()` sentinel (distinct from a legitimately-stored `None`).
   - If unresolved (`value is _UNRESOLVED`) **and** `node.default` is set: print a `⚠` warning
     naming the node id, the path, and the chosen default, then return `(node.default, None)`.
     This is the guardrail — the *only* runner-level place a malformed/missing upstream output is
     absorbed rather than propagated.
   - If unresolved and `node.default` is unset: raise `RuntimeError` naming the node id, the path,
     and instructing the workflow author to add a `default`.
   - Otherwise continue to step 2 with the resolved `value`.
2. **Stringify.** `str_value = str(value)` — every subsequent comparison (`cases` keys, `_coerce`)
   operates on this string form, so a resolved `int`/`bool`/`float` context value still matches a
   YAML-authored string case/condition.
3. **`cases` (equality, checked first).** If `str_value` is a key in `node.cases` (a `dict[str,
   str]`, value→next-node-id), return `(node.cases[str_value], value)` immediately — equality wins
   over `conditions` even if a condition would also match, so an author relying on both for the
   same path gets the `cases` entry.
4. **`conditions` (ordered comparisons).** Iterate `node.conditions` in declaration order; for each,
   look up its `op` in `_OPS` (raising `ValueError` if unknown — see Contract) and call
   `op_fn(str_value, cond.value)` — both operands go through [`_coerce`](#_coercev-private) inside
   the operator (except `==`/`!=`, which compare the raw operand values, not `str_value`/`cond.value`
   directly — see the `_OPS` table). Return `(cond.next, value)` on the first match; `conditions`
   are OR'd but order matters only for which `next` wins when more than one would match.
5. **`default`.** If nothing matched and `node.default` is set, return `(node.default, value)`.
6. **No match, no default.** Raise `RuntimeError` naming the node id, the resolved `value`, and the
   path — distinct from step 1's error (this is a *resolved* value that matched nothing, not an
   unresolvable path).

## `_OPS` — the comparison table

Module-level `dict[str, Callable[[Any, Any], bool]]`, one entry per `BranchCondition.op`
(`workflow-format.md#branch`'s `op ∈ {==,!=,<,>,<=,>=}`):

| op | function | operands |
|---|---|---|
| `==` | `lambda a, b: a == b` | raw `a`, `b` — no coercion |
| `!=` | `lambda a, b: a != b` | raw `a`, `b` — no coercion |
| `<` | `lambda a, b: _coerce(a) < _coerce(b)` | both passed through `_coerce` |
| `>` | `lambda a, b: _coerce(a) > _coerce(b)` | both passed through `_coerce` |
| `<=` | `lambda a, b: _coerce(a) <= _coerce(b)` | both passed through `_coerce` |
| `>=` | `lambda a, b: _coerce(a) >= _coerce(b)` | both passed through `_coerce` |

Called as `op_fn(str_value, cond.value)` in algorithm step 4 — `a` is always the branch's
stringified resolved value, `b` is always the condition's YAML-authored `value: string`.

## `_coerce(v)` — private

`_coerce(v: Any) -> float | str`. Normalizes an operand for the four ordering operators
(`<`/`>`/`<=`/`>=`) so a numeric-looking string compares numerically rather than
lexicographically (`"10" > "9"` would otherwise be `False` as strings).
1. `try: return float(v)`.
2. `except (TypeError, ValueError): return str(v)` — a non-numeric operand (or `None`) falls back
   to its string form, so an ordering comparison between two non-numeric values still runs (as a
   string compare) instead of raising.

Not used by `==`/`!=` (compared raw) or by the `cases` equality map (compared as `str_value`
already stringified in step 2).

## Consumers

- The [node-walk engine](workflow.md#node-walk-engine) (`workhorse/workhorse/main.py::_step_loop`)
  — the only caller, once per `BranchNode` step; the returned pair is written to
  [`branch.json`](artifact-writer.md#write_branchnode_id-path-value-next_node) and `current_id` is
  set to the returned `next_node_id`.
- `workhorse/workhorse/graph/dot.py` (`workhorse dot --pin`) — reuses `evaluate` against a
  throwaway `WorkflowContext` seeded from `--pin key=value` to resolve which edge a pinned branch
  collapses to when pruning the rendered diagram (see
  [`workflow-context.md`](workflow-context.md#as_dict---dict)).
