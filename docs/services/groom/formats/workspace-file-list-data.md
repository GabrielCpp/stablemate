---
type: format
slug: workspace-file-list-data
title: Workspace file list data
---
# Workspace file list data

Workspace file list data is the file-tree contract used by the [serve workspace file list](../http/groom.md#serve-workspace-file-list) invocation, the connected sidecar data plane described by [sidecar live sessions](../sidecar-live-sessions.md), and the fallback [workspace volume file-list reader](../concepts/workspace-volume-file-list-reader.md). It represents one selected workflow checkout as repo-relative file paths and is consumed by the [dashboard tree builder](../concepts/dashboard-tree-builder.md) for the [groom dashboard](../gui/screens/groom-dashboard.md) run Files tab. On the sidecar websocket it is the successful `getTree` [sidecar websocket frame](sidecar-websocket-frame.md) result object under `rpc_result.data`; on the HTTP surface the endpoint first asks the [sidecar RPC helper](../concepts/sidecar-rpc-helper.md) for that object and returns the resulting path list, whether the read failed and whether the source reports failures as the JSON object `{"paths": [...], "failed": false, "reported": true}`.

The list stays flat on the wire. Nesting is a pure function of the paths and a display decision the browser is already making — it decides which directories start collapsed — so projecting a tree here would put half a rendering choice on the wire.

The `failed` member is additive. It says the listing could not be completed, so an empty `paths` with `failed` true is a checkout nobody could read and an empty `paths` with `failed` false is a checkout with no files. The `reported` member exists only on the HTTP body. It is false when a sidecar answered without a `failed` member, which is how a sidecar too old to report failure shows itself.

The path-list contract, including endpoint source selection, sidecar handling, pruning, relative paths, empty results, and failure behavior, is covered by the tests below.

- file: not an on-disk artifact; this is a websocket RPC data object, HTTP response body, and sidecar/fallback handoff shape.
- code: groom/groom/sidecar.py::_rpc_get_tree@193010e1b49a
- code: groom/groom/sidecar.py::_list_tree@f932858439aa
- code: groom/groom/sidecar.py::_checkout@f2a0314ca61e
- code: groom/groom/app.py::files@1a8049542599
- code: groom/groom/docker_io.py::read_tree@bb70525049f0
- code: groom/groom/docker_io.py::list_files@e49bcdc817f1
- code: groom/groom/localfs.py::read_tree@88d9baa48a08
- code: groom/groom/localfs.py::list_files@fe6374fbc487
- code: groom/groom/assets/dashboard.js::loadRunFiles@0928854e5520
- code: groom/groom/assets/dashboard.js::loadRunFiles@0928854e5520
- code: groom/groom/assets/dashboard.js::buildTree@1b4860076f0b
- detail: [Dashboard tree input selection](../concepts/dashboard-tree-input-selection.md)
- tests: groom/tests/test_app.py::test_files_endpoint_returns_a_json_path_list,
  groom/tests/test_app.py::test_files_relays_a_sidecar_that_says_its_read_failed,
  groom/tests/test_app.py::test_files_from_an_old_sidecar_is_marked_as_unable_to_report_failure,
  groom/tests/test_sidecar_session.py::test_rpc_get_tree_reports_a_missing_checkout_as_failed,
  groom/tests/test_docker_io.py::test_read_tree_reports_a_failed_docker_run_as_failed,
  groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors,
  groom/tests/test_sidecar_session.py::test_rpc_get_tree_lists_files_skipping_vendor_dirs,
  groom/tests/test_sidecar_session.py::test_handle_rpc_get_tree_replies_ok,
  groom/tests/test_docker_io.py::test_list_files_returns_repo_relative_paths_and_prunes_vendor_dirs,
  groom/tests/test_docker_io.py::test_list_files_volume_root_when_repo_dir_empty,
  groom/tests/test_docker_io.py::test_list_files_empty_on_docker_failure

## Contract

The sidecar's `getTree` handler delegates path discovery to its local tree reader; `groom/groom/sidecar.py::_handle_rpc` places that result in the successful `rpc_result` frame.

- consistency: sidecar-websocket-frame — a live sidecar handling `rpc` method `getTree` returns `{"paths": [...], "failed": bool, "repos": [names]}` as the `data` object in a successful `rpc_result` frame, as constructed by `groom/groom/sidecar.py::_rpc_get_tree`.
- endpoint producer: the `/files/{container_id}` endpoint first asks the live sidecar for a `getTree` result through the [sidecar RPC helper](../concepts/sidecar-rpc-helper.md) and otherwise asks the fallback reader — the local-filesystem one for a native run, the Docker-volume one otherwise — for the same listing; both branches return the path list and the failure flag, not producer metadata.
- websocket consumer: the host-side sidecar RPC resolver delivers the successful `data` object unchanged to the `/files/{container_id}` endpoint, while an absent connection or expected sidecar RPC error becomes `None` so the endpoint can use the fallback volume reader.
- HTTP consumer: the dashboard parses the JSON body, reads its `paths` and `failed` members, and builds the collapsible Files tab tree from those path strings. There is no line splitting, trimming, or blank-line filtering step — the list arrives as a list.
- media forms: both surfaces use the same JSON object with a `paths` member and a `failed` member — `rpc_result.data` on the sidecar socket, the whole response body over HTTP, where `reported` joins them. The browser-internal form is the parsed `paths` array, used as-is.
- path scope: every returned path is relative to the selected checkout root; no returned path is absolute, prefixed with `/workspace`, prefixed with `/vol`, or prefixed with the selected `repo` value.
- selected root: an empty `repo` selects the workspace volume root for the fallback readers and the first checkout found for a sidecar; a non-empty `repo` selects that directory under the workspace for first-party sidecar callers and under the mounted volume for fallback callers.
- pruning: sidecar and fallback producers omit files below `.git`, `node_modules`, `__pycache__`, and `.venv` directories.
- entry type: returned entries are file paths only; directories appear only as prefixes that the dashboard tree builder derives from slash-separated file paths.
- empty-state: an empty path list with `failed` false means the checkout has no files; the run Files tab says `This checkout has no files.` A failed read is never shown as no files.
- ordering: sidecar and fallback producers sort paths ascending before returning them.
- duplicate rule: producers do not intentionally add duplicate paths; the HTTP response and browser tree builder do not deduplicate duplicates if a producer returned them.
- encoding rule: HTTP serialization is ordinary JSON. Path strings travel as array elements, so no separator character is reserved and a path is never split, joined, or trimmed in transit.
- error behavior: a missing selected root, a folder the walk could not enter, a missing workflow volume, a fallback reader that could not start and a non-zero fallback reader process become an empty or partial path list with `failed` true. A sidecar RPC failure or an absent sidecar connection becomes a fallback attempt. None of them is an exception response for this shape.
- failure rule: a reply from a sidecar without a `failed` member reports `reported` false, and an empty list from it says the dashboard cannot confirm the checkout has no files.
- default repo: a sidecar given an empty `repo` reads the first checkout the diff read finds under its workspace root and falls back to the workspace root when it finds none.

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
- meaning: volume-relative checkout directory the run's checkout selector chose; an empty value means the workspace volume root.
- wire-location: `rpc.params.repo` for sidecar `getTree` and `/files/{container_id}?repo=...` for the HTTP endpoint; not present in the returned path entries.
- normalization: first-party producers convert absent values to `""`; the sidecar string-converts the parameter before resolving the selected root.

### field-sidecar-result

- type: `{ "paths": list[str], "failed": bool } | None`
- default: `None`
- required: false
- wire-location: `rpc_result.data` in a successful [sidecar websocket frame](sidecar-websocket-frame.md) for method `getTree`
- meaning: optional sidecar RPC result object for method `getTree`; when present, the endpoint reads only its `paths` and `failed` members and does not consult Docker volumes.
- failure rule: absent sidecar connection and sidecar RPC errors are represented as `None` to the endpoint, causing fallback volume lookup.
- ignored members: any sidecar result members other than `paths` and `failed` are ignored by the HTTP endpoint for this format.

### field-paths

- type: `list[str]`
- default: `[]`
- required: true
- wire-key: `paths`
- wire-location: `rpc_result.data.paths` for sidecar `getTree`; the `paths` member of the HTTP response body.
- meaning: repo-relative file paths. Missing or falsey sidecar paths and unavailable producers become an empty list, and the `failed` member says whether that emptiness is a failed read; process-launch and timeout failures of the fallback reader are reported through `failed`.
- item contract: each item is a non-absolute text path relative to the selected root; slash-separated directory names are represented only as path prefixes on file entries, not as standalone directory rows.
- item exclusion: no item is expected from below a `.git`, `node_modules`, `__pycache__`, or `.venv` directory.
- ordering: sorted ascending by first-party sidecar and fallback producers.
- consumer normalization: none. The dashboard passes the parsed array straight into [dashboard path tree](dashboard-path-tree.md) construction.

### field-failed

- type: `bool`
- default: `false`
- required: true on replies from a current sidecar and from the HTTP endpoint
- wire-key: `failed`
- wire-location: `rpc_result.data.failed` for sidecar `getTree`; the `failed` member of the HTTP response body.
- meaning: true when the listing could not be completed, because the checkout is missing, a folder could not be walked, or the fallback reader failed. A true value does not mean the checkout is empty.
- consumer: the run Files tab shows `This checkout could not be read` with a retry control.

### field-served

- type: `str`
- default: `volume`
- required: true on the HTTP body only
- wire-key: `served`
- wire-location: the `served` member of the HTTP response body only, absent from the sidecar socket.
- meaning: `sidecar` when the connected sidecar answered and `volume` for a fallback answer. It is an addition, so a consumer that ignores it keeps working.

### field-reported

- type: `bool`
- default: `true`
- required: true on the HTTP body only
- wire-key: `reported`
- wire-location: the `reported` member of the HTTP response body only, absent from the sidecar socket.
- meaning: false when a sidecar answered without a `failed` member, so its empty list cannot confirm an empty checkout.

### field-json-body

- type: `{ "paths": list[str], "failed": bool, "reported": bool, "served": str, "repos"?: list[str] }`
- default: `{"paths": [], "failed": true, "reported": true}` when no source can answer
- required: true
- wire-location: body of `GET /files/{container_id}` with media type `application/json`.
- meaning: the HTTP response body. It is the same object shape the sidecar returns under `rpc_result.data`, so the socket path and the HTTP path hand the endpoint the same thing.
- empty rule: an empty list with `failed` false is a successful response, which the dashboard treats as no files.
- member rule: three members, `paths`, `failed` and `reported`, plus `repos` when the sidecar names the run's checkouts (see [run checkout selection](../concepts/run-checkout-selection.md)). There is no repository label, container id, or count.

### field-client-paths

- type: `list[str]`
- default: `[]`
- required: true
- code: groom/groom/assets/dashboard.js::loadRunFiles@6468e7a48cc1
- wire-location: browser-internal value after the Files tab parses the `GET /files/{container_id}` response body.
- meaning: path strings used to build the Files tab tree; this is the input to [dashboard path tree](dashboard-path-tree.md) construction.
- derivation: the parsed body's `paths` member, or an empty list when it is missing. The run Files tab also reads `failed` and `reported`.
- ordering: preserves the producer's order; the path-tree builder sorts directory names and file basenames when presenting the tree.

## Methods

### method-_rpc_get_tree

- sig: `_rpc_get_tree(params: dict) -> dict`
- abstract: false
- raises: no intentional exception for missing or falsey `repo`.
- verify: json_path(path="exception.type", absent=true)
- raises: exceptions from the delegated tree reader can propagate to the RPC wrapper, which converts them into a failed `rpc_result` frame.
- verify: json_path(path="exception.type", matches=".+")
- returns: JSON-compatible object with the first-party `paths` and `failed` members for the requested selected root.
- verify: count(subject="returned paths", equals=2)
- verify: json_path(path="$.paths[0]", equals="README.md")
- verify: json_path(path="$.paths[1]", equals="src/a.py")
- code: groom/groom/sidecar.py::_rpc_get_tree@193010e1b49a
- tests: groom/tests/test_sidecar_session.py::test_rpc_get_tree_lists_files_skipping_vendor_dirs
- input: decoded sidecar RPC params object for method `getTree`.
- effects: reads the sidecar container's local workspace tree through the delegated tree reader; does not send websocket frames, serialize JSON, mutate files, mutate workflow state, inspect Docker, or broadcast dashboard updates.
- calls: sidecar local workspace tree reader at `groom/groom/sidecar.py::_list_tree`.
- algorithm:
  1. Read `repo` from the params object, defaulting to `""`.
  2. Convert the repo value to text.
  3. Return an object whose `paths` value is the sorted file list and whose `failed` value is the failure flag from the sidecar local workspace tree reader.

### method-_list_tree

- sig: `_list_tree(repo: str) -> tuple[list[str], bool]`
- abstract: false
- raises: no intentional exception for a missing selected root, which returns an empty list and a true failure flag.
- verify: json_path(path="exception.type", absent=true)
- raises: no intentional exception for paths that cannot be relativized to the selected base.
- verify: json_path(path="exception.type", absent=true)
- raises: an unreadable folder sets the failure flag and the walk goes on.
- verify: json_path(path="exception.type", matches=".+")
- returns: sorted selected-root-relative file paths and a flag that is true when the root is missing or a folder could not be walked.
- verify: json_path(path="$[0]", equals="README.md")
- verify: json_path(path="$[1]", equals="src/a.py")
- code: groom/groom/sidecar.py::_list_tree@f932858439aa
- tests: groom/tests/test_sidecar_session.py::test_rpc_get_tree_lists_files_skipping_vendor_dirs
- input: `repo` is the workspace-relative selected checkout directory; `""` means the sidecar workspace root.
- output: sorted list of selected-root-relative file paths for all non-pruned files under the selected root.
- effects: reads directory entries from the sidecar workspace only; does not read file contents, follow the websocket, call Docker, run Git, mutate files, mutate workflow state, or broadcast dashboard updates.
- calls: checkout chooser at `groom/groom/sidecar.py::_checkout` and selected-base resolver at `groom/groom/sidecar.py::_repo_base`; filesystem walking, relative-path conversion, and sorting are standard-library concerns.
- repo resolution: the repo string is joined directly under the sidecar workspace root; this tree-list reader does not apply the file-content traversal guard, and callers are expected to pass the selected repository value produced by groom's repository selection flow.
- pruning scope: pruning is applied to child directory names encountered during the recursive walk; the selected base itself must already be the intended workspace root or checkout root.
- algorithm:
  1. Choose the checkout, which is the named `repo` or, when it is empty, the first checkout the diff read finds, and resolve the selected base to that child path under the workspace root. With no checkout found the base is the workspace root.
  2. Return an empty list and a true failure flag when the selected base is not a directory.
  3. Walk the selected base recursively while pruning `.git`, `node_modules`, `__pycache__`, and `.venv` directories.
  4. Convert each discovered file path to a path relative to the selected base; skip any path that cannot be relativized.
  5. Return the collected paths sorted ascending, with the failure flag set when any folder could not be walked.
