---
type: flow
slug: operator-inspects-working-tree-diff
title: Operator inspects working-tree diff
---
# Operator inspects working-tree diff

This journey covers the as-built operator path through the [groom dashboard](../gui/screens/groom-dashboard.md) for inspecting one workflow checkout's working-tree changes, or its whole change since the branch started. It starts from a selected run whose row says a sidecar is connected. The run's [Diff tab](../gui/screens/groom-dashboard.md#detail-diff-tab) reads the diff once when the run is selected, loads [workspace diff data](../formats/workspace-diff-data.md) through [GET /diff/{container_id}](../http/groom.md#get-working-tree-diff), renders a changed-file tree through the [dashboard path tree](../formats/dashboard-path-tree.md), and renders one chosen parsed file through Diff2Html. A run with several checkouts also shows a [checkout selector](../gui/screens/groom-dashboard.md#detail-checkout-select), described in [run checkout selection](../concepts/run-checkout-selection.md). The operator chooses between the two with the [diff view switch](../gui/screens/groom-dashboard.md#detail-diff-view-switch), and [branch start diff](../concepts/branch-start-diff.md) holds how the second view is computed. Server-side diff reads prefer [sidecar live sessions](../sidecar-live-sessions.md) `getDiff` RPCs and fall back to the workflow workspace-volume diff reader when no live sidecar can serve the data.

The wire carries the raw unified diff as one JSON string in the `diff` member, beside the untracked file names, the `failed` and `reported` flags and the `repos` list of checkout names. The Since branch start view adds the commit the branch started at and the branch it was found against. Diff2Html both parses that text and renders it, and it escapes what it emits, which is why the diff rides through unsplit rather than having half a parser reimplemented server-side. Parsing and rendering happen in the browser, once per load; selecting a file afterwards costs no request.

The implementation is anchored by `groom/groom/assets/dashboard.js::DetailTabs`, `groom/groom/assets/dashboard.js::CheckoutSelect`, `groom/groom/assets/dashboard.js::selectCheckout`, `groom/groom/assets/dashboard.js::selectDiffView`, `groom/groom/assets/dashboard.js::DiffViewSwitch`, `groom/groom/assets/dashboard.js::loadRunDiff`, `groom/groom/assets/dashboard.js::buildTree`, `groom/groom/assets/dashboard.js::fileDiffMarkup`, and `groom/groom/app.py::diff`.

- start: the groom server is running, the browser has loaded the [groom dashboard](../gui/screens/groom-dashboard.md), and a [workflow container](../concepts/workflow-container.md) run with a connected sidecar is selected in the Runs pane.
- steps:
  1. The operator selects a run whose row says a sidecar is connected. The dashboard reads the diff once with `GET /diff/{container_id}` and the `repo` of the run's chosen checkout, or no `repo` when the reply has not yet named any checkout, so the endpoint uses its default checkout. The Diff tab shows the `+N −M` counts before it is opened.
  2. [Serve workspace diff](../http/groom.md#serve-working-tree-diff) handles the request. It first asks the connected sidecar, when present, for `getDiff` with the selected `repo` value, returns the successful RPC result's `diff`, `untracked`, `failed` and `repos` members, and otherwise falls back to the workflow's known workspace volume through the [workspace volume diff reader](../concepts/workspace-volume-diff-reader.md). Unknown workflow state, missing volume metadata, no checkout, git failure and timeout become `200 OK` with an empty `diff` string and `failed` true. An empty working tree becomes `200 OK` with an empty `diff` and `failed` false.
  3. The operator opens the tab with [open the run Diff tab](../gui/screens/groom-dashboard.md#open-detail-diff-tab). When the reply named more than one checkout, the [checkout selector](../gui/screens/groom-dashboard.md#detail-checkout-select) shows beside the tabs, and [select a checkout](../gui/screens/groom-dashboard.md#select-detail-checkout) reads that checkout's diff and, when Files is shown, its tree, once each.
  4. The browser reads the fulfilled response as JSON. A `failed` body, a rejected fetch, or non-empty text that Diff2Html cannot parse shows `This diff could not be read` with a Retry control, and never reads as no changes. An empty `diff` from a sidecar that sent no `failed` member says the tab cannot confirm there are no changes.
  5. Otherwise the browser parses the text once with the third-party Diff2Html parser and keeps the result as the [dashboard parsed diff file cache](../formats/dashboard-parsed-diff-file-cache.md). The tree lists the changed files with counts, untracked files go in their own group, and the first changed file's diff shows.
  6. The tab derives one entry per parsed file: the path is `newName` unless it is missing or `/dev/null`, in which case `oldName`; it also carries the file's original index in the parsed array plus its added- and deleted-line counts. Those entries go through the [dashboard tree builder](../concepts/dashboard-tree-builder.md), the same flat-paths-to-nested-nodes function the Files tab uses, producing one [dashboard path tree](../formats/dashboard-path-tree.md).
  7. The tab renders directory rows and [diff file rows](../gui/screens/groom-dashboard.md#detail-diff-file-row), directories before files and sibling leaves sorted by displayed basename with `localeCompare`. Names are rendered as text nodes, so no escaping step stands between the parsed diff and the document. Collapse state is component-local to each directory node, so toggling a directory fetches nothing and reparses nothing.
  8. The operator activates a diff file row. The tab writes that leaf's parsed-file index into its own state, which marks that row and only that row `aria-current="true"`, and renders the parsed file at that index with Diff2Html for a one-element array, using `drawFileList: false`, line matching, line-by-line output, and dark colour scheme. Selecting a file sends no HTTP request, reparses no raw diff text, and mutates no server state.
  9. [Diff view switch](../gui/screens/groom-dashboard.md#detail-diff-view-switch).
  10. The operator may read the diff again with [refresh the run diff](../gui/screens/groom-dashboard.md#refresh-detail-diff).
- end: the Diff tab shows the chosen checkout's changed files in a tree with counts and the selected file's dark line-by-line Diff2Html render
- verify: visible(locator="#detail-diff-panel .d2h-file-wrapper", text="app.py")
- end: at most one changed-file row is marked `aria-current`
- verify: count(subject="active changed-file rows", equals=1)
- end: the Diff tab shows `This diff could not be read` after a failed read, never `no changes`
- verify: visible(locator="#detail-diff-panel", text="This diff could not be read")
- end: the Since branch start view shows the whole change since the branch started, with its base named as `since <sha7> on <branch>`
- end: a branch with no findable start says so in the panel with no count, and Uncommitted still works
- end: a refresh keeps the chosen checkout and the chosen view
- end: when the sidecar stops answering, the Diff tab keeps the last diff read, marked stale in words with a strip that names the read time, as [kept run diff](../concepts/kept-run-diff.md) describes
- end: a detail push arriving mid-read neither re-fetches the diff nor closes the tab
- end: the Diff tab shows the view the switch names, Uncommitted by default, and never shows one view's diff as the other's
- end: server-side sidecar and fallback diff failures are represented as an empty `diff` string with `failed` true, not endpoint-specific error responses
- verify: json_path(path="$.failed", equals=true)
- detail: [live sidecar RPC and volume fallback selection](../concepts/live-sidecar-rpc-and-volume-fallback-selection.md)
- detail: [branch start diff](../concepts/branch-start-diff.md)
- detail: [run checkout selection](../concepts/run-checkout-selection.md)
- detail: [dashboard tree flow selection](../concepts/dashboard-tree-flow-selection.md)
- tests: groom/tests/test_app.py::test_diff_prefers_sidecar_socket,
  groom/tests/test_app.py::test_diff_endpoint_passes_repo_through,
  groom/tests/test_dashboard_client.py::test_every_endpoint_is_read_as_json,
  groom/tests/test_dashboard_client.py::test_the_only_markup_the_client_sets_comes_from_a_sanitizer_or_a_renderer,
  groom/tests/test_diff_tab_dynamic.py::test_diff_tab_controls_have_roles_names_and_keyboard_operation_and_pass_axe,
  groom/tests/test_checkout_selector_dynamic.py::test_selecting_a_checkout_shows_its_change_and_its_tree_and_the_size_follows,
  groom/tests/test_sidecar_session.py::test_git_diff_reports_working_tree_changes,
  groom/tests/test_sidecar_session.py::test_git_diff_empty_when_no_repo,
  groom/tests/test_diff_tab_dynamic.py::test_opening_diff_lists_changed_files_in_a_tree_with_counts_and_shows_the_first_file,
  groom/tests/test_diff_tab_dynamic.py::test_an_unreadable_diff_says_so_offers_a_retry_and_clears_when_a_read_succeeds,
  groom/tests/test_diff_since_branch_dynamic.py::test_since_branch_start_shows_the_whole_change_names_its_base_and_the_size_and_tree_follow
