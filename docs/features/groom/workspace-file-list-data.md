---
type: format
slug: workspace-file-list-data
title: Workspace file list data
---
# Workspace file list data

Workspace file list data is the file-tree contract used by the [serve workspace file list](http/groom.md#serve-workspace-file-list) invocation, the connected sidecar data plane described by [sidecar live sessions](sidecar-live-sessions.md), and the fallback [workspace volume file-list reader](concepts/workspace-volume-file-list-reader.md). It represents one selected workflow checkout as repo-relative file paths and is consumed by the [dashboard tree builder](concepts/dashboard-tree-builder.md) for the [groom dashboard](gui/screens/groom-dashboard.md) Files panel. On the sidecar websocket it is the successful `getTree` [sidecar websocket frame](sidecar-websocket-frame.md) result object under `rpc_result.data`; on the HTTP surface the endpoint first asks the [sidecar RPC helper](concepts/sidecar-rpc-helper.md) for that object and returns the resulting path list as the JSON object `{"paths": [...]}`.

The list stays flat on the wire. Nesting is a pure function of the paths and a display decision the browser is already making — it decides which directories start collapsed — so projecting a tree here would put half a rendering choice on the wire.

- file: not an on-disk artifact; this is a websocket RPC data object, HTTP response body, and sidecar/fallback handoff shape.
- code: groom/groom/sidecar.py::_rpc_get_tree
- code: groom/groom/sidecar.py::_list_tree
- code: groom/groom/app.py::files
- code: groom/groom/docker_io.py::list_files
- code: groom/groom/localfs.py::list_files
- code: groom/groom/assets/dashboard.js::loadFiles
- code: groom/groom/assets/dashboard.js::buildTree
- verify: groom/tests/test_app.py::test_files_endpoint_returns_a_json_path_list,
  groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors,
  groom/tests/test_sidecar_session.py::test_rpc_get_tree_lists_files_skipping_vendor_dirs,
  groom/tests/test_sidecar_session.py::test_handle_rpc_get_tree_replies_ok,
  groom/tests/test_docker_io.py::test_list_files_returns_repo_relative_paths_and_prunes_vendor_dirs,
  groom/tests/test_docker_io.py::test_list_files_volume_root_when_repo_dir_empty,
  groom/tests/test_docker_io.py::test_list_files_empty_on_docker_failure

## Contract

- sidecar producer: a live sidecar handling `rpc` method `getTree` returns `{"paths": [...]}` as the `data` object in a successful `rpc_result` frame; the handler delegates path discovery to the sidecar's local tree reader.
- endpoint producer: the `/files/{container_id}` endpoint first asks the live sidecar for a `getTree` result through the [sidecar RPC helper](concepts/sidecar-rpc-helper.md) and otherwise asks the fallback reader — the local-filesystem one for a native run, the Docker-volume one otherwise — for the same path list; both branches return only the final path list, not producer metadata.
- websocket consumer: the host-side sidecar RPC resolver delivers the successful `data` object unchanged to the `/files/{container_id}` endpoint, while an absent connection or expected sidecar RPC error becomes `None` so the endpoint can use the fallback volume reader.
- HTTP consumer: the dashboard parses the JSON body, reads its `paths` member, and builds the collapsible Files panel tree from those path strings. There is no line splitting, trimming, or blank-line filtering step — the list arrives as a list.
- media forms: both surfaces use the same JSON object with one `paths` member — `rpc_result.data` on the sidecar socket, the whole response body over HTTP. The browser-internal form is the parsed `paths` array, used as-is.
- path scope: every returned path is relative to the selected checkout root; no returned path is absolute, prefixed with `/workspace`, prefixed with `/vol`, or prefixed with the selected `repo` value.
- selected root: an empty `repo` selects the workspace volume root; a non-empty `repo` selects that directory under the workspace for first-party sidecar callers and under the mounted volume for fallback callers.
- pruning: sidecar and fallback producers omit files below `.git`, `node_modules`, `__pycache__`, and `.venv` directories.
- entry type: returned entries are file paths only; directories appear only as prefixes that the dashboard tree builder derives from slash-separated file paths.
- empty-state: an empty path list serializes as `{"paths": []}` and means the client has no file tree to show; the Files pane renders `(no files)`.
- ordering: sidecar and fallback producers sort paths ascending before returning them.
- duplicate rule: producers do not intentionally add duplicate paths; the HTTP response and browser tree builder do not deduplicate duplicates if a producer returned them.
- encoding rule: HTTP serialization is ordinary JSON. Path strings travel as array elements, so no separator character is reserved and a path is never split, joined, or trimmed in transit.
- error behavior: a missing selected root, sidecar RPC failure, absent sidecar connection, missing workflow volume, or non-zero fallback reader process becomes an empty path list or fallback attempt rather than an exception response for this shape.

## Fields

### field-container-id

- type: `str`
- default: none
- required: true
- meaning: workflow container id from the route path; it selects the live sidecar connection and, when the socket path is unavailable, the workflow record whose `workspace_volume` enables fallback reads.
- wire-location: `/files/{container_id}` route segment; not present in the sidecar `getTree` result object or the HTTP response body.

### field-repo

- type: `str`
- default: `""`
- required: false
- meaning: volume-relative checkout directory chosen by the repository picker; an empty value means the workspace volume root.
- wire-location: `rpc.params.repo` for sidecar `getTree` and `/files/{container_id}?repo=...` for the HTTP endpoint; not present in the returned path entries.
- normalization: first-party producers convert absent values to `""`; the sidecar string-converts the parameter before resolving the selected root.

### field-sidecar-result

- type: `{ "paths": list[str] } | None`
- default: `None`
- required: false
- wire-location: `rpc_result.data` in a successful [sidecar websocket frame](sidecar-websocket-frame.md) for method `getTree`
- meaning: optional sidecar RPC result object for method `getTree`; when present, the endpoint reads only its `paths` member and does not consult Docker volumes.
- failure rule: absent sidecar connection and sidecar RPC errors are represented as `None` to the endpoint, causing fallback volume lookup.
- ignored members: any sidecar result members other than `paths` are ignored by the HTTP endpoint for this format.

### field-paths

- type: `list[str]`
- default: `[]`
- required: true
- wire-key: `paths`
- wire-location: `rpc_result.data.paths` for sidecar `getTree`; the `paths` member of the HTTP response body.
- meaning: repo-relative file paths. Missing or falsey sidecar paths, unavailable producers, and non-zero fallback reader processes become an empty list; process-launch and timeout exceptions are outside this data shape.
- item contract: each item is a non-absolute text path relative to the selected root; slash-separated directory names are represented only as path prefixes on file entries, not as standalone directory rows.
- item exclusion: no item is expected from below a `.git`, `node_modules`, `__pycache__`, or `.venv` directory.
- ordering: sorted ascending by first-party sidecar and fallback producers.
- consumer normalization: none. The dashboard passes the parsed array straight into [dashboard path tree](dashboard-path-tree.md) construction.

### field-json-body

- type: `{ "paths": list[str] }`
- default: `{"paths": []}`
- required: true
- wire-location: body of `GET /files/{container_id}` with media type `application/json`.
- meaning: the HTTP response body. It is the same object shape the sidecar returns under `rpc_result.data`, so the socket path and the HTTP path hand the endpoint the same thing.
- empty rule: an empty list is a successful response, which the dashboard treats as no files.
- member rule: exactly one member, `paths`. There is no status field, error sentinel, repository label, container id, or count.

### field-client-paths

- type: `list[str]`
- default: `[]`
- required: true
- code: groom/groom/assets/dashboard.js::loadFiles
- wire-location: browser-internal value after the Files pane parses the `GET /files/{container_id}` response body.
- meaning: path strings used to build the Files pane tree; this is the input to [dashboard path tree](dashboard-path-tree.md) construction.
- derivation: the parsed body's `paths` member, or an empty list when it is missing.
- ordering: preserves the producer's order; the path-tree builder sorts directory names and file basenames when presenting the tree.

## Methods

### method-_rpc_get_tree

- sig: `_rpc_get_tree(params: dict) -> dict`
- abstract: false
- raises: no intentional exception for missing or falsey `repo`; exceptions from the delegated tree reader can propagate to the RPC wrapper, which converts them into a failed `rpc_result` frame.
- code: groom/groom/sidecar.py::_rpc_get_tree
- verify: groom/tests/test_sidecar_session.py::test_rpc_get_tree_lists_files_skipping_vendor_dirs
- input: decoded sidecar RPC params object for method `getTree`.
- output: JSON-compatible object with exactly the first-party `paths` member for the requested selected root.
- effects: reads the sidecar container's local workspace tree through the delegated tree reader; does not send websocket frames, serialize JSON, mutate files, mutate workflow state, inspect Docker, or broadcast dashboard updates.
- calls: sidecar local workspace tree reader at `groom/groom/sidecar.py::_list_tree`.
- algorithm:
  1. Read `repo` from the params object, defaulting to `""`.
  2. Convert the repo value to text.
  3. Return an object whose `paths` value is the sorted file list from the sidecar local workspace tree reader.

### method-_list_tree

- sig: `_list_tree(repo: str) -> list[str]`
- abstract: false
- raises: no intentional exception for a missing selected root or paths that cannot be relativized to the selected base; unexpected filesystem walk errors can propagate.
- code: groom/groom/sidecar.py::_list_tree
- verify: groom/tests/test_sidecar_session.py::test_rpc_get_tree_lists_files_skipping_vendor_dirs
- input: `repo` is the workspace-relative selected checkout directory; `""` means the sidecar workspace root.
- output: sorted list of selected-root-relative file paths for all non-pruned files under the selected root.
- effects: reads directory entries from the sidecar workspace only; does not read file contents, follow the websocket, call Docker, run Git, mutate files, mutate workflow state, or broadcast dashboard updates.
- calls: selected-base resolver at `groom/groom/sidecar.py::_repo_base`; filesystem walking, relative-path conversion, and sorting are standard-library concerns.
- repo resolution: the repo string is joined directly under the sidecar workspace root; this tree-list reader does not apply the file-content traversal guard, and callers are expected to pass the selected repository value produced by groom's repository selection flow.
- pruning scope: pruning is applied to child directory names encountered during the recursive walk; the selected base itself must already be the intended workspace root or checkout root.
- algorithm:
  1. Resolve the selected base to the workspace root when `repo` is empty, otherwise to the named child path under the workspace root.
  2. Return an empty list when the selected base is not a directory.
  3. Walk the selected base recursively while pruning `.git`, `node_modules`, `__pycache__`, and `.venv` directories.
  4. Convert each discovered file path to a path relative to the selected base; skip any path that cannot be relativized.
  5. Return the collected paths sorted ascending.
