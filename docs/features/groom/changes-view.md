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

The spec-complete behaviour lives in the typed book, not here. The user
journey — picking a checkout, fetching the diff, selecting a file — is the
[operator inspects working tree diff](flows/operator-inspects-working-tree-diff.md)
flow, and its claims are split into one obligation per step. The pane's
interactive controls are
[activity diff mode](gui/screens/groom-dashboard.md#activity-diff-mode),
[diff directory toggle](gui/screens/groom-dashboard.md#diff-directory-toggle),
[diff file row](gui/screens/groom-dashboard.md#diff-file-row), and
[diff view region](gui/screens/groom-dashboard.md#diff-view-region);
their interactions are
[select activity diff mode](gui/screens/groom-dashboard.md#select-activity-diff-mode),
[toggle diff directory](gui/screens/groom-dashboard.md#toggle-diff-directory),
and
[select diff file row](gui/screens/groom-dashboard.md#select-diff-file-row).
The HTTP endpoint is
[get working tree diff](http/groom.md#get-working-tree-diff), which serves
[workspace diff data](workspace-diff-data.md) as the unified-diff text the
browser parses. The parsed array lives in the
[dashboard parsed diff file cache](dashboard-parsed-diff-file-cache.md), the
nested tree comes from the
[dashboard tree builder](concepts/dashboard-tree-builder.md), and the
[diff representation selection](concepts/dashboard-diff-representation-selection.md)
concept names the split between raw wire text and parsed cache. The run-detail
disclosure shares the endpoint and is covered by
[toggle detail working tree diff](gui/screens/groom-dashboard.md#toggle-detail-working-tree-diff).

## Invariants (load-bearing)

The diff pane is the only place in the UI that injects untrusted markup
(unified diff text), and every choice below is the smallest one that keeps
the untrusted surface narrow. The XSS boundary is the single
`dangerouslySetInnerHTML` site fed by `Diff2Html.html`; the assets are
vendored under the static mount so the browser never reaches for a CDN; and
the diff is a pull, never a broadcast, so a 5-second fleet tick cannot
re-render the pane out from under a reading operator.

- consistency: changes-view — no diff markup reaches the DOM until one file is selected, server-side or client-side.
- verify: visible(locator=".fd-empty", text="Select a changed file to see its diff.")
- code: groom/groom/app.py::diff
- code: groom/groom/assets/dashboard.js::DiffView
- code: groom/groom/assets/dashboard.js::loadDiff
- tests: groom/tests/test_app.py::test_diff_endpoint_passes_repo_through
- tests: groom/tests/test_a11y_dynamic.py::test_diff_pane_is_accessible

The HTTP endpoint (`groom/groom/app.py::diff`) returns the raw unified text
as `{"diff": text or ""}` and never renders it server-side. The store starts
with `diff: { status: "idle", files: [], idx: -1 }`, so the tree pane mounts
no `DiffView` markup until a row is clicked; `DiffView` itself returns the
empty placeholder `Select a changed file to see its diff.` whenever
`files[idx]` is undefined, which the initial `-1` index reaches on first load.

- consistency: changes-view — within the diff pane, the only `dangerouslySetInnerHTML` site is fed by `Diff2Html.html`, which escapes what it emits. The XSS boundary is one function wide.
- verify: visible(locator=".diff-wrap", text="<script>alert(1)</script>")
- code: groom/groom/assets/dashboard.js::DiffView
- code: groom/groom/assets/dashboard.js::diffMarkup
- tests: groom/tests/test_dashboard_client.py::test_the_only_markup_the_client_sets_comes_from_a_sanitizer_or_a_renderer

`DiffView` and the run-detail disclosure's `DiffDisclosure` both pass
`Diff2Html.html(...)` into `dangerouslySetInnerHTML`; no other markup in this
pane is set rather than built. The diff pane is the only surface that owns
this injection — gate questions go through `Markdown` (DOMPurify-sourced)
and the files pane goes through `highlight.js`, neither of which is rendered
here.

- consistency: changes-view — no runtime CDN: `diff2html`, `marked`, `DOMPurify`, `highlight.js`, and the Preact/htm bundle are all vendored under the static asset mount.
- verify: count(subject="CDN hostnames in the served shell", equals=0)
- code: groom/groom/templates/dashboard.html
- code: groom/groom/app.py::stamp_assets
- tests: groom/tests/test_app.py::test_an_asset_that_is_not_on_disk_keeps_its_url
- tests: groom/tests/test_app.py::test_the_shell_stamps_every_asset_url_with_the_files_version
- tests: groom/tests/test_app.py::test_the_served_shell_is_the_stamped_one

Every `<script>` and `<link>` URL the shell emits points at `/assets/...` —
`diff2html.min.{css,js}`, `marked.min.js`, `purify.min.js`,
`highlight.min.js`, `hljs-github-dark.min.css`, and `htm-preact.js` all sit
under `groom/groom/assets/`. The asset stamper
(`groom/groom/app.py::stamp_assets`) only rewrites URLs whose path matches
an existing file in `ASSETS_DIR`; a missing file keeps its original URL
rather than being silently redirected to one.

- consistency: changes-view — the diff is a pull, never a push. The websocket frames carry fleet state and detail, never unified diff text.
- verify: count(subject="diff-bearing frames broadcast by the websocket", equals=0)
- code: groom/groom/app.py::diff

`groom/groom/app.py::diff` is a `GET /diff/{container_id}` handler: the
browser fetches the unified text on demand and the pane never re-renders on
a websocket tick. The websocket fan-out
([`groom/groom/state.py::broadcast`](concepts/dashboard-client-queue-set.md#method-broadcast-dashboard-message))
only carries JSON frames built by the projection module; the unified diff
string never enters the state payload, so a fleet tick cannot replace the
file the operator is currently reading with another file's diff.

## Related

- [runs-fleet-view](runs-fleet-view.md) ·
  [workspace-diff-data](workspace-diff-data.md) ·
  [repository-menu-data](repository-menu-data.md) ·
  [dashboard path tree](dashboard-path-tree.md)
