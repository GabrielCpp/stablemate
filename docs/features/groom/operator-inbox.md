---
type: feature
slug: operator-inbox
title: Operator inbox — incoming gate messages only
status: implemented
id: stablemate-2
area: groom
---
# Operator inbox — incoming gate messages only

The **Inbox** is groom's message list: it shows **only workers that have an open
operator gate** — a container that has pushed a `blocked` event and is parked on
`await_operator`, waiting for a human. A plain `RUNNING` worker, or a `FINISHED`
one, is not a message and never appears here. The whole fleet lives in the
[worker tree](worker-tree.md); the inbox is the "needs you now" subset.

## Behaviour

- A worker appears in the inbox exactly when it has at least one gate
  (`wf.gates` non-empty). Gates arrive via a `blocked` push (sidecar or the
  `await_operator.py` backstop — see [sidecar protocol](sidecar-protocol.md)).
- Rows are ordered blocked-first, then by name (`STATE_ORDER` then `wf.name`).
- A blocked row shows the repo, `#id`, the gate path, and a one-line question
  preview.
- Answering a gate clears it; the worker flips to `RUNNING` and **leaves the
  inbox** on the next broadcast — inbox-zero reads as "nothing needs you".
- Empty state: `No incoming messages — inbox zero.` (a discovery pass in flight
  shows the spinner instead).

## Invariants (load-bearing)

- The inbox is filtered to gated workers **only** — this is the whole point of
  the mode. Do not add running/finished workers here; that is the tree's job.
- Gate questions are untrusted LLM-authored markdown and stay on the
  escaped-`data-md` → `marked` → `DOMPurify` path (never raw HTML).

## Implementation

- `groom/groom/render.py::render_inbox` — filters `wf.gates and _matches(...)`,
  renders `_inbox_row`.
- Contract tests: `groom/tests/test_render.py`
  (`test_inbox_shows_only_workers_with_open_gates`,
  `test_inbox_orders_gated_workers_by_state_then_name`).

## Related

- [worker-tree](worker-tree.md) · [sidecar-protocol](sidecar-protocol.md)
