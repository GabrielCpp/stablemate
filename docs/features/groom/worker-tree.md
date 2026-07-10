---
type: feature
slug: worker-tree
title: Worker tree — repository to worker picker
status: implemented
id: stablemate-3
area: groom
---
# Worker tree — repository to worker picker

The left **picker** is a live `Repository → worker` tree. Unlike the
[inbox](operator-inbox.md) (gated workers only), the tree shows **every** worker
grouped under its repository, so an operator can see the whole fleet — running,
idle, blocked, and finished — organised per repo.

## Behaviour

- Workers are grouped by repo label = `repo_name@repo_branch` (falling back to
  `repo_name`, then `—`).
- Repos with a blocked worker float to the top; the rest sort alphabetically.
- Each repo header carries a compact type summary (e.g. `coder×2 author×1`) and,
  when any member is blocked, a red blocked-count pill.
- Each worker row shows a state dot, a self-colouring type badge, the short
  `#id`, and its current graph node.
- Clicking a repo header collapses/expands its workers; clicking a worker loads
  its gate detail into the detail pane. (In the [Changes](changes-view.md) tab a
  click means something different — see that Concept.)
- The filter box narrows repos/workers/types live via `GET /search`.

## Invariants (load-bearing)

- The tree lists **all** workers; it is the fleet view, the complement of the
  message-only inbox.
- Worker `type` (coder/author/…) is derived host-side from the `/workflow`
  mount's `Source` basename, with the `com.docker.compose.service` label as a
  fallback — no sidecar change needed.

## Implementation

- `groom/groom/render.py::render_tree`, `_group_by_repo`, `_tree_group`,
  `_tree_worker`.
- Contract test: `groom/tests/test_render.py::test_tree_groups_workers_by_repo_and_badges_type`.

## Related

- [operator-inbox](operator-inbox.md) · [changes-view](changes-view.md)
