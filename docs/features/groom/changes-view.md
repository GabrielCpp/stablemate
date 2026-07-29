---
type: feature
slug: changes-view
title: Changes view — working-tree diff for one checkout
status: implemented
id: stablemate-1
area: groom
---
# Changes view — working-tree diff for one checkout

The **diff** activity mode shows one checkout's uncommitted work as a browsable
file tree beside a single-file diff. The operator picks a container and repo from
the repository menu; the pane fetches that checkout's raw unified diff once and
renders one file at a time.

It is scoped to one checkout rather than showing every run's diff at once. The
earlier design grouped every worker's changes under a repo header in a single
tree, which meant every mode switch paid for a `git diff` per container — on a
fleet of a dozen runs the pane was the slowest thing in the dashboard, and almost
all of what it fetched was never looked at.

## Behaviour

- The container/repo picker at the top of the pane is shared with the files mode.
  Nothing loads until a checkout is selected; until then the pane reads
  *Pick a container / repo above.*
- Selecting a checkout fetches [get working tree diff](http/groom.md#get-working-tree-diff),
  which returns `{"diff": "<unified diff text>"}` — see
  [workspace diff data](workspace-diff-data.md).
- The raw unified text rides through the wire unsplit. `diff2html` parses it in
  the browser into per-file entries, which is why the server does not reimplement
  a parser that already runs on the other end.
- The parsed entries become a nested directory tree built by the
  [dashboard tree builder](concepts/dashboard-tree-builder.md);
  each leaf shows the file name and its `+adds / -dels`.
- **The diff is rendered only when a file is clicked.** Until then the right pane
  reads *Select a changed file to see its diff.* Clicking a leaf sets the
  selected index and renders that one file.
- A checkout with no uncommitted changes renders `(no changes)`; a failed fetch
  renders `failed to load`. Neither is an error dialog, and neither disturbs the
  fleet list or the connection state.
- Clicking inside the diff pane never selects a run. The pane is its own mode
  with its own components; run selection lives in the runs pane and there is no
  global click handler either could hijack.

## Invariants (load-bearing)

- No diff is rendered server-side, and none is rendered client-side until a file
  is selected.
- Diff markup is the only thing in this pane assigned through
  `dangerouslySetInnerHTML`, and it comes from `diff2html`, which escapes what it
  emits. That is the XSS boundary, and it is one function wide.
- No runtime CDN: `diff2html`, `marked`, `DOMPurify`, `highlight.js`, and the
  Preact/htm bundle are all vendored under the static asset mount.
- The diff is a pull, never a push. The server does not broadcast diffs, so a
  fleet tick cannot re-render the pane out from under a reading operator.

## Implementation

- `groom/groom/app.py::diff` — `GET /diff/{container_id}?repo=`. Prefers the
  container's sidecar over a `getDiff` RPC and falls back to reading the
  workspace volume directly, native or docker.
- `groom/groom/assets/dashboard.js::loadDiff` — fetches the text, parses it with
  `Diff2Html.parse`, and writes `{status, files, idx}` into the store's `diff`
  slice.
- `groom/groom/assets/dashboard.js::DiffTree` — builds the nested tree and owns
  leaf selection.
- `groom/groom/assets/dashboard.js::DiffView` — renders the single selected file
  with `Diff2Html.html`.
- `groom/groom/assets/dashboard.css` — two-pane layout and treeview styles.

## Related

- [runs-fleet-view](runs-fleet-view.md) ·
  [workspace-diff-data](workspace-diff-data.md) ·
  [repository-menu-data](repository-menu-data.md) ·
  [dashboard path tree](dashboard-path-tree.md)
