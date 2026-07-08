---
type: feature
id: stablemate-1
slug: changes-view
title: Changes view — per-repo tree of working-tree diffs
area: groom
status: implemented
---
# Changes view — per-repo tree of working-tree diffs

The **Changes** activity mode presents every worker's working-tree diff grouped
**per repository**, as a browsable file tree. Selecting a file shows that one
file's diff; nothing else is rendered until you click.

## Behaviour

- The pane groups workers under their repo header (same grouping as the
  [worker tree](worker-tree.md)); each worker is a collapsible node.
- Under each worker, its changed paths render as a **nested directory treeview**
  (built client-side from the parsed unified diff), each leaf showing the file
  name and `+adds / -dels`.
- **The diff is shown only when a file is clicked** — never before. Clicking a
  file renders just that file's diff into a side panel (two-pane layout: file
  tree on the left, single-file diff on the right).
- **Clicking is tab-dependent.** In the Changes tab a click drives the tree
  (collapse a worker/directory, or open a file's diff); it must NOT open the
  gate detail the way a worker click does in the Inbox/Fleet tabs. The global
  click handler bails out inside `.changes`, and the Changes view owns its own
  delegated listener.

## Invariants (load-bearing)

- No diff is rendered server-side and none is shown until a file is selected.
- Diffs render client-side with `diff2html` from the `GET /diff/{id}` text; file
  names are escaped before insertion — the XSS-safe boundary is preserved.
- No runtime CDN; `diff2html`/`marked`/`DOMPurify` are vendored.

## Implementation

- `groom/groom/render.py::render_changes`, `_changes_worker` — emits per-worker
  `[data-files-for]` (tree target) + `[data-filediff-for]` (diff panel)
  containers; **no** server-rendered diff and **no** `data-worker-id` (so the
  global worker-select can't hijack a file click).
- `groom/groom/app.py::changes` — `GET /changes`.
- `groom/groom/templates/dashboard.html` — `wireChanges()` (`buildFileTree` /
  `renderTreeNode`, `Diff2Html.parse` once, `Diff2Html.html([file])` on click),
  and the `.changes` early-return in the global body click handler.
- `groom/groom/assets/dashboard.css` — two-pane layout + treeview styles.
- Contract tests: `groom/tests/test_render.py`
  (`test_changes_groups_diffs_per_repo`, `test_changes_empty_message`).

## Related

- [worker-tree](worker-tree.md) · [operator-inbox](operator-inbox.md) ·
  design result: [../groom-redesign/README.md](../groom-redesign/README.md) ·
  architecture overview: [../groom.md](../groom.md)
