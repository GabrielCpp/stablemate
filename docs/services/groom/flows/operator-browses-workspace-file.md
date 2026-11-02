---
type: flow
slug: operator-browses-workspace-file
title: Operator browses workspace file
---
# Operator browses workspace file

This journey covers the as-built operator path through the Files tab of a run in the [groom dashboard](../gui/screens/groom-dashboard.md): opening the [Files tab](../gui/screens/groom-dashboard.md#detail-files-tab) of a run whose row says a sidecar is connected, loading [workspace file list data](../formats/workspace-file-list-data.md) through [GET /files/{container_id}](../http/groom.md#get-workspace-file-list), selecting a [files file row](../gui/screens/groom-dashboard.md#detail-files-file-row), loading [workspace file content data](../formats/workspace-file-content-data.md) through [GET /file/{container_id}](../http/groom.md#get-workspace-file-content), and rendering the selected file in the [file body](../gui/screens/groom-dashboard.md#detail-files-file-body). A run with several checkouts shows a [checkout selector](../gui/screens/groom-dashboard.md#detail-checkout-select), described in [run checkout selection](../concepts/run-checkout-selection.md). The server-side reads prefer [sidecar live sessions](../sidecar-live-sessions.md) RPCs and fall back to the workflow workspace volume readers when no live sidecar can serve the data.

Every response on this path is JSON: a `paths` array with the `repos` list of checkout names, and a `{path, content, lang}` object. The server sends no markup and picks no colours; the browser builds the tree, and the highlighter runs client-side against the language name the server derived from the path. That is the whole reason the same two endpoints serve a sidecar-backed read and a volume-backed one identically: neither one is responsible for presentation.

The dashboard implementation uses `groom/groom/assets/dashboard.js::DetailTabs`, `groom/groom/assets/dashboard.js::CheckoutSelect`, `groom/groom/assets/dashboard.js::loadRunFiles`, `groom/groom/assets/dashboard.js::openRunFile`, and `groom/groom/assets/dashboard.js::buildTree`; the server-side path uses `groom/groom/app.py::files`, `groom/groom/app.py::file_content`, and `groom/groom/projection.py::file_lang`.

- start: the groom server is running
- verify: http_status(code=200, title="Groom Dashboard", path="/")
- start: the browser has loaded the [groom dashboard](../gui/screens/groom-dashboard.md)
- verify: visible(locator=".app")
- start: the dashboard starts in runs mode
- verify: visible(locator=".app[data-mode='runs']")
- start: a container run with a connected sidecar is selected
- steps:
  1. The operator opens the run's Files tab. The first open of the tab for that selection reads the tree once with [GET /files/{container_id}](../http/groom.md#get-workspace-file-list), naming the run's chosen checkout in the `repo` query value, or the first checkout of the reply, or none for a sidecar that names no checkouts.
  2. While the read is in flight the tab shows a loading state. When the reply names more than one checkout, the [checkout selector](../gui/screens/groom-dashboard.md#detail-checkout-select) shows, and choosing another checkout reads that checkout's tree and clears the open file and the collapsed folders.
  3. [Serve workspace file list](../http/groom.md#serve-workspace-file-list) first asks the connected sidecar, when present, for `getTree` with the selected `repo`. A successful sidecar response supplies [workspace file list data](../formats/workspace-file-list-data.md) and is returned as `{"paths": [...], "repos": [...]}`, where `repos` names the workspace's checkouts.
  4. If the sidecar is absent, times out, closes, or reports an error, [serve workspace file list](../http/groom.md#serve-workspace-file-list) falls back to the workflow's known workspace volume and reads repo-relative file paths through the [workspace volume file-list reader](../concepts/workspace-volume-file-list-reader.md), or through local-disk listing for a native run. Missing workflow state, missing volume metadata, non-zero fallback reads, or an empty selected checkout produce `{"paths": []}` rather than an endpoint-specific error body.
  5. The tab reads the response as JSON and stores `paths` (an absent or non-array value becoming an empty list), marking its read `ready`. The tree island builds a [dashboard path tree](../formats/dashboard-path-tree.md) from those flat paths — the nesting is a pure function of them, computed in the browser — and renders a directory row for each directory node and a [files file row](../gui/screens/groom-dashboard.md#detail-files-file-row) for each file leaf, directories before files and each group sorted by name. An empty path list renders `(no files)`; a rejected fetch or unparseable body marks the read `error` and renders `failed to load`.
  6. The operator may expand or collapse directories. Collapse state is component-local on purpose: it belongs to this directory in this tab, nothing else reads it, so it stays out of the store, and it survives a re-render because the node is keyed by directory name. Toggling fetches nothing and changes no selection.
  7. The operator activates a [files file row](../gui/screens/groom-dashboard.md#detail-files-file-row). The tab writes the clicked path into its state — which is what marks that row, and only that row, `active` and `aria-current="true"` — sets the viewer to `loading`, and sends [GET /file/{container_id}](../http/groom.md#get-workspace-file-content) with the selected `repo` and `path` query values.
  8. [Serve workspace file content](../http/groom.md#serve-workspace-file-content) names the highlighting language from the requested path through the [groom projection module](../concepts/groom-projection-module.md#method-file-lang) *before* attempting any read, then asks the connected sidecar, when present, for `getFile` with `repo` and `path`. A successful sidecar response supplies [workspace file content data](../formats/workspace-file-content-data.md) as `{"path", "content", "lang"}`.
  9. If the sidecar is absent, times out, closes, rejects the path, or reports an error, [serve workspace file content](../http/groom.md#serve-workspace-file-content) falls back to the workflow workspace volume. It composes `repo/path`, strips only leading slashes, guards the relative path through the [workspace volume relative path guard](../concepts/workspace-volume-relative-path-guard.md), and reads the selected file through the [workspace volume file-content reader](../concepts/workspace-volume-file-content-reader.md). Missing workflow state, missing volume metadata, empty path, unsafe path, missing file, unreadable file, or falsey content produce a `200 OK` body with an empty `content` — and the same `lang`, since it never depended on which read won.
  10. The tab discards the response if a later click has already changed the selected path, so a slow read cannot overwrite a newer file. Otherwise it stores `path`, `content`, and `lang`, and the [file body](../gui/screens/groom-dashboard.md#detail-files-file-body) renders a header carrying the path as a text node plus either `(empty or binary file)` for empty content or a `<pre class="file-pre hljs">` body.
  11. For non-empty content the viewer runs Highlight.js in the browser with the server-supplied language, falling back to auto-detection when the language is unknown to the loaded highlighter. Highlight.js emits escaped HTML, so its output is set as markup; when the library is absent or throws, the viewer inserts the file text as a text node instead, so the plain code block always remains visible.
- end: the Files tab shows the file tree built from the latest `paths` response, exactly one file row marked `aria-current`, and the file body showing the selected path with highlighted or plain raw text, the selected path with `(empty or binary file)`, or an unreadable notice
- verify: json_path(path="$.paths", matches="README.md")
- verify: json_path(path="$.path", equals="src/a.py")
- verify: json_path(path="$.content", equals="print(1)\n")
- verify: json_path(path="$.lang", equals="python")
- verify: visible(locator="#detail-files-panel [aria-current=true]", text="a.py")
- detail: [live sidecar RPC and volume fallback selection](../concepts/live-sidecar-rpc-and-volume-fallback-selection.md)
- detail: [run checkout selection](../concepts/run-checkout-selection.md)
- detail: [dashboard tree flow selection](../concepts/dashboard-tree-flow-selection.md)
- tests: groom/tests/test_app.py::test_files_endpoint_returns_a_json_path_list,
  groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors,
  groom/tests/test_app.py::test_file_content_prefers_sidecar_socket,
  groom/tests/test_app.py::test_file_endpoint_joins_repo_and_path_and_returns_content,
  groom/tests/test_app.py::test_file_endpoint_swallows_unsafe_path,
  groom/tests/test_dashboard_client.py::test_every_endpoint_is_read_as_json,
  groom/tests/test_files_tab_dynamic.py::test_files_tab_controls_have_roles_names_and_keyboard_operation_and_pass_axe,
  groom/tests/test_checkout_selector_dynamic.py::test_changing_the_checkout_clears_the_open_file_and_the_collapsed_folders_of_files,
  groom/tests/test_sidecar_session.py::test_rpc_get_tree_lists_files_skipping_vendor_dirs,
 groom/tests/test_sidecar_session.py::test_rpc_get_file_reads_local_file
