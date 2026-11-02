---
type: feature
slug: changes-view
title: Changes view — working-tree diff for one checkout
status: implemented
id: stablemate-1
area: groom
---
# Changes view — working-tree diff for one checkout

A run's **Diff** tab shows one checkout's uncommitted work, or its whole change
since the branch started, as a browsable file tree beside a single-file diff. A
switch in the tab bar chooses between the two, and Uncommitted is the default. A run with several checkouts shows a
checkout selector beside the tabs, and the tab fetches the chosen checkout's raw
unified diff once and renders one file at a time.

It is scoped to one checkout of one run rather than showing every run's diff at
once. The earlier design grouped every worker's changes under a repo header in a
single tree, which meant every mode switch paid for a `git diff` per container.
On a fleet of a dozen runs that view was the slowest thing in the dashboard, and
almost all of what it fetched was never looked at.

## Behaviour

The spec-complete behaviour lives in the typed book, not here. The user
journey, choosing a checkout, fetching the diff and selecting a file, is the
[operator inspects working tree diff](flows/operator-inspects-working-tree-diff.md)
flow, and its claims are split into one obligation per step. The tab's
interactive controls are
[detail diff tab](gui/screens/groom-dashboard.md#detail-diff-tab),
[detail checkout select](gui/screens/groom-dashboard.md#detail-checkout-select),
[detail diff view switch](gui/screens/groom-dashboard.md#detail-diff-view-switch),
and [detail diff file row](gui/screens/groom-dashboard.md#detail-diff-file-row);
their interactions are
[open detail diff tab](gui/screens/groom-dashboard.md#open-detail-diff-tab),
[select detail checkout](gui/screens/groom-dashboard.md#select-detail-checkout),
and
[refresh detail diff](gui/screens/groom-dashboard.md#refresh-detail-diff).
The HTTP endpoint is
[get working tree diff](http/groom.md#get-working-tree-diff), which serves
[workspace diff data](formats/workspace-diff-data.md) as the unified-diff text the
browser parses. The parsed array lives in the
[dashboard parsed diff file cache](formats/dashboard-parsed-diff-file-cache.md), the
nested tree comes from the
[dashboard tree builder](concepts/dashboard-tree-builder.md), and the
[diff representation selection](concepts/dashboard-diff-representation-selection.md)
concept names the split between raw wire text and parsed cache. The tab itself
is covered by [run Diff tab](concepts/run-diff-tab.md), the checkout choice by
[run checkout selection](concepts/run-checkout-selection.md), and the second view by
[branch start diff](concepts/branch-start-diff.md).

## Invariants (load-bearing)

The Diff tab is the only place in the UI that injects untrusted markup
(unified diff text), and every choice below is the smallest one that keeps
the untrusted surface narrow. The XSS boundary is the single
`dangerouslySetInnerHTML` site fed by `Diff2Html.html`; the assets are
vendored under the static mount so the browser never reaches for a CDN; and
the diff is a pull, never a broadcast, so a 5-second fleet tick cannot
re-render the tab out from under a reading operator.

- consistency: changes-view — no diff markup reaches the DOM until one file is selected, server-side or client-side.
- code: groom/groom/app.py::diff@3b4a38e8e9ca
- code: groom/groom/assets/dashboard.js::DiffTab@ed8babf5c628
- code: groom/groom/assets/dashboard.js::loadRunDiff@a79bfdf4c0b1
- tests: groom/tests/test_app.py::test_diff_endpoint_passes_repo_through
- tests: groom/tests/test_diff_tab_dynamic.py::test_diff_tab_controls_have_roles_names_and_keyboard_operation_and_pass_axe

The HTTP endpoint (`groom/groom/app.py::diff`) returns the raw unified text
as `{"diff", "untracked", "failed", "reported", "repos"}`, plus `based` and the
base members for the branch view, and never renders it server-side. The tab renders a placeholder until a changed file is chosen, and
a file's markup is built only for the file at the selected index.

- consistency: changes-view — within the Diff tab, the only `dangerouslySetInnerHTML` site is fed by `Diff2Html.html`, which escapes what it emits. The XSS boundary is one function wide.
- code: groom/groom/assets/dashboard.js::RunFileDiff@139e9580d270
- code: groom/groom/assets/dashboard.js::fileDiffMarkup@1286720f9b96
- tests: groom/tests/test_dashboard_client.py::test_the_only_markup_the_client_sets_comes_from_a_sanitizer_or_a_renderer

`RunFileDiff` passes `Diff2Html.html(...)` into `dangerouslySetInnerHTML`; no
other markup in this tab is set rather than built. The Diff tab is the only
surface that owns this injection. Gate questions go through `Markdown`
(DOMPurify-sourced) and the Files tab goes through `highlight.js`, neither of
which is rendered here.

- consistency: changes-view — no runtime CDN: `diff2html`, `marked`, `DOMPurify`, `highlight.js`, and the Preact/htm bundle are all vendored under the static asset mount.
- verify: count(subject="CDN hostnames in the served shell", equals=0)
- code: groom/groom/templates/dashboard.html@65323b15e0f8
- code: groom/groom/app.py::stamp_assets@daf0c62ee7d3
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
- code: groom/groom/app.py::diff@3b4a38e8e9ca

`groom/groom/app.py::diff` is a `GET /diff/{container_id}` handler: the
browser fetches the unified text on demand and the tab never re-renders on
a websocket tick. The websocket fan-out
([`groom/groom/state.py::broadcast`](concepts/dashboard-client-queue-set.md#method-broadcast-dashboard-message))
only carries JSON frames built by the projection module; the unified diff
string never enters the state payload, so a fleet tick cannot replace the
file the operator is currently reading with another file's diff.

## Related

- [runs-fleet-view](runs-fleet-view.md) ·
  [workspace-diff-data](formats/workspace-diff-data.md) ·
  [dashboard path tree](formats/dashboard-path-tree.md)
