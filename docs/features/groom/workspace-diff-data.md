---
type: format
slug: workspace-diff-data
title: Workspace diff data
---
# Workspace diff data

Workspace diff data is the diff-viewer contract used by the [serve workspace diff](http/groom.md#serve-workspace-diff) invocation, the connected sidecar data plane described by [sidecar live sessions](sidecar-live-sessions.md), and the fallback [workspace volume diff reader](concepts/workspace-volume-diff-reader.md). It represents one selected workflow checkout's working-tree changes as raw unified diff text. On the sidecar websocket it is the successful `getDiff` [sidecar websocket frame](sidecar-websocket-frame.md) result object under `rpc_result.data`; on the HTTP surface it serializes as `text/plain` for the [groom dashboard](gui/screens/groom-dashboard.md) Diff panel and worker-detail diff disclosure. The endpoint producer first asks the [sidecar RPC helper](concepts/sidecar-rpc-helper.md) for the connected sidecar's result and falls back to the Docker-volume reader only when that helper returns no data. Sidecar diff defaulting discovers local checkout directories with [method-_find_repo_dirs](#method-_find_repo_dirs) before [method-_git_diff](#method-_git_diff) resolves the selected checkout with [method-_repo_base](#method-_repo_base) and runs git against it; fallback diff defaulting delegates empty repository selection to the [workspace volume repository-directory reader](concepts/workspace-volume-repository-directory-reader.md).

- file: not an on-disk artifact; this is a websocket RPC data object, HTTP response body, and sidecar/fallback handoff shape.
- code: groom/groom/app.py::diff
- code: groom/groom/docker_io.py::git_diff
- code: groom/groom/sidecar.py::_rpc_get_diff
- code: groom/groom/sidecar.py::_git_diff
- code: groom/groom/sidecar.py::_repo_base
- verify: groom/tests/test_app.py::test_diff_prefers_sidecar_socket,
  groom/tests/test_app.py::test_diff_endpoint_passes_repo_through,
  groom/tests/test_docker_io.py::test_git_diff_returns_stdout_on_success,
  groom/tests/test_docker_io.py::test_git_diff_returns_empty_when_no_repo_found,
  groom/tests/test_docker_io.py::test_git_diff_returns_empty_on_git_failure,
  groom/tests/test_sidecar_session.py::test_git_diff_reports_working_tree_changes,
  groom/tests/test_sidecar_session.py::test_git_diff_empty_when_no_repo

## Contract

- endpoint producer: `GET /diff/{container_id}` returns [field-text-body](#field-text-body) as `text/plain`; it prefers sidecar RPC data and otherwise reads from the workflow container's known workspace volume when available.
- sidecar producer: a live sidecar handling `rpc` method `getDiff` returns `{"diff": text}` as the `data` object in a successful `rpc_result` frame after running a working-tree-versus-`HEAD` diff against its local `/workspace` checkout.
- fallback producer: the Docker-volume fallback runs a read-only throwaway git container against one checkout in the selected workflow's workspace volume and returns its stdout as the same raw diff text.
- sidecar request: the sidecar data-plane request uses [sidecar websocket frame](sidecar-websocket-frame.md) method `getDiff` with `params.repo` as the only meaningful parameter; missing `repo` defaults to `""`.
- endpoint request: the `/diff/{container_id}` endpoint path supplies [field-container-id](#field-container-id); the optional `repo` query parameter is passed unchanged to both the sidecar RPC and the fallback volume reader.
- websocket consumer: the host-side sidecar RPC resolver delivers the successful `data` object unchanged to the `/diff/{container_id}` endpoint.
- HTTP consumer: dashboard JavaScript reads the plain-text response, parses it as unified diff text, stores non-empty parse results as [dashboard parsed diff file cache](dashboard-parsed-diff-file-cache.md), and renders changed-file summaries plus per-file diff HTML in the browser.
- repository scope: `repo` selects a volume-relative checkout directory from the repository picker. An empty `repo` lets the sidecar producer choose the first immediate git checkout under `/workspace` and lets the fallback reader choose the first checkout returned by the Docker-volume repository-directory reader.
- sidecar repository default: when `repo` is empty, the sidecar chooses the first discovered git checkout under `/workspace`; discovery includes `/workspace` itself when it is a git checkout and immediate child directories that contain `.git`, then sorts the volume-relative choices before selecting the first. The workspace root checkout is represented as `""`; child checkouts are represented by child directory name only. When no checkout is found, it returns an empty `diff` value.
- fallback repository default: when `repo` is empty, the fallback reader asks the workspace volume repository-directory reader for sorted checkout paths under the Docker volume and uses the first returned value as the resolved `repo_dir`; when discovery returns no paths, or when the first sorted value is `""` for a volume-root checkout, the diff reader treats the resolved value as no checkout and returns empty text without starting a git diff container.
- sidecar diff command: sidecar diff text is the stdout of `git -c safe.directory=* -C <selected checkout> diff HEAD`, with a 20-second timeout.
- fallback diff command: fallback diff text is the stdout of a read-only `alpine/git:2.43.0` container running `git -c safe.directory=* -C /vol/{repo_dir} diff HEAD` against the mounted workspace volume, with the shared Docker I/O timeout.
- empty-state: an empty `diff` value or response body means the sidecar returned no diff, no fallback checkout was available, the git/Docker process failed, the diff subprocess timed out, or the selected checkout had no working-tree changes; clients treat it as a diff empty state rather than as a transport error.
- error behavior: unavailable repositories, process launch failures, subprocess failures, timeouts, and non-zero diff command statuses become empty diff text for successful producers; unexpected malformed RPC parameters can fail the sidecar RPC and return an error frame under the [sidecar websocket frame](sidecar-websocket-frame.md) contract. An unavailable sidecar connection or sidecar RPC error becomes fallback to the volume reader.
- media: HTTP serialization is `text/plain`; the server does not wrap, escape, colorize, or annotate the returned diff text.

## Fields

### field-container-id

- type: `str`
- default: none
- required: true
- meaning: workflow container id from the route path; it selects the live sidecar connection and, when the socket path is unavailable, the workflow record whose `workspace_volume` enables fallback reads.

### field-repo

- type: `str`
- default: `""`
- required: false
- wire-key: `repo`
- wire-location: `rpc.params.repo` for sidecar `getDiff`; HTTP query parameter for `/diff/{container_id}`.
- meaning: volume-relative checkout directory chosen by the repository picker; an empty value means the sidecar producer or fallback reader chooses the first git checkout it finds by its own repository-discovery rule.
- normalization: the sidecar string-converts the parameter value before selecting a checkout; first-party callers send a plain string.

### field-workspace-volume

- type: `str`
- default: `""`
- required: false
- wire-location: server-side [workflow container](concepts/workflow-container.md) state, not an HTTP or sidecar frame field.
- meaning: Docker workspace volume name used only by the fallback producer when sidecar RPC data is unavailable. Unknown workflow ids, missing workflow records, and empty workspace-volume values produce an empty text response instead of starting a fallback diff read.

### field-sidecar-result

- type: `dict[str, str] | None`
- default: `None`
- required: false
- wire-location: `rpc_result.data` in a successful [sidecar websocket frame](sidecar-websocket-frame.md) for method `getDiff`
- meaning: optional sidecar RPC result object for method `getDiff`; when present, the endpoint reads only its `diff` member and does not consult Docker volumes.
- failure rule: absent sidecar connection and sidecar RPC errors are represented as `None` to the endpoint, causing fallback volume lookup.

### field-diff

- type: `str`
- default: `""`
- required: true
- wire-key: `diff`
- wire-location: `rpc_result.data.diff` for sidecar `getDiff`; HTTP response body after plain-text serialization.
- meaning: raw unified working-tree-versus-`HEAD` diff text for the selected checkout. Missing, falsey, unavailable, timed-out, or non-zero-exit producers become an empty string rather than an endpoint-specific error response.
- item contract: the value is literal unified diff text, not HTML, markdown, JSON, base64, or a pre-rendered file tree; callers must parse or render it as unified diff text.
- ordering: line and hunk order are the order produced by the underlying git diff command; the producer does not post-process, sort, filter, redact, or annotate the stdout.

### field-text-body

- type: `str`
- default: `""`
- required: true
- meaning: HTTP response body for the endpoint; it is the same raw unified diff text as `diff`, emitted with `text/plain` media type and no extra envelope, status marker, repository label, or rendered markup.

## Methods

### method-diff

- sig: `async diff(container_id: str, repo: str = "") -> Response`
- abstract: false
- raises: no endpoint-specific exception for unknown workflow id, missing workspace volume, unavailable sidecar connection, sidecar RPC error, falsey sidecar diff, missing checkout, non-zero fallback git exit, or empty diff output; unexpected sidecar-registry, Docker subprocess launch/timeout, or response-construction failures can propagate.
- code: groom/groom/app.py::diff
- verify: groom/tests/test_app.py::test_diff_prefers_sidecar_socket
- verify: groom/tests/test_app.py::test_diff_endpoint_passes_repo_through
- input: `container_id` is the required HTTP path variable; `repo` is the optional query value forwarded unchanged to both producers.
- output: one `text/plain` HTTP response whose body is [field-text-body](#field-text-body).
- effects: performs a read-only sidecar RPC attempt or read-only fallback Docker-volume diff; it does not mutate workflow state, broadcast dashboard fragments, render diff HTML, validate repository existence, or write workspace files.
- calls: [sidecar RPC helper](concepts/sidecar-rpc-helper.md) with method `getDiff`, then [workspace volume diff reader](concepts/workspace-volume-diff-reader.md#git-diff) only when no sidecar data is returned and the workflow has a known workspace volume.
- algorithm:
  1. Request `getDiff` over the connected sidecar data plane with `{"repo": repo}`.
  2. If the sidecar call returns any data object, return `data.get("diff") or ""` as `text/plain` without consulting the fallback reader.
  3. Look up the workflow container by `container_id` in the in-memory workflow registry.
  4. If the workflow is unknown or has no workspace volume, return an empty `text/plain` response.
  5. Ask the fallback workspace-volume diff reader for the selected volume and `repo` value.
  6. Return the fallback text unchanged as `text/plain`.

### method-_rpc_get_diff

- sig: `_rpc_get_diff(params: dict) -> dict`
- abstract: false
- raises: no intentional exception when `params` is a mapping and local diff production fails; non-mapping `params` values can fail before the sidecar RPC wrapper converts the failure into an error frame.
- code: groom/groom/sidecar.py::_rpc_get_diff
- verify: groom/tests/test_sidecar_session.py::test_git_diff_reports_working_tree_changes
- verify: groom/tests/test_sidecar_session.py::test_git_diff_empty_when_no_repo
- input: one sidecar RPC params object for method `getDiff`; only the `repo` member is read.
- output: exactly one JSON-compatible object with a `diff` key whose value is [workspace diff data](workspace-diff-data.md#field-diff) text.
- defaulting: missing `repo` is read as `""`; the value is string-converted before checkout selection.
- effects: performs no websocket send, host-state mutation, file mutation, dashboard broadcast, or fallback Docker read itself; it delegates all local diff reading to [method-_git_diff](#method-_git_diff).
- calls: [method-_git_diff](#method-_git_diff).
- algorithm:
  1. Read `repo` from the params object, defaulting to `""`.
  2. Convert `repo` to a string.
  3. Return `{"diff": <local diff text>}` using [method-_git_diff](#method-_git_diff).

### method-_git_diff

- sig: `_git_diff(repo: str) -> str`
- abstract: false
- raises: no intentional exception for no checkout, subprocess launch failure, subprocess timeout, subprocess failure, or non-zero git exit; unexpected workspace directory iteration failures can propagate.
- code: groom/groom/sidecar.py::_git_diff
- verify: groom/tests/test_sidecar_session.py::test_git_diff_reports_working_tree_changes
- verify: groom/tests/test_sidecar_session.py::test_git_diff_empty_when_no_repo
- input: `repo` is a workspace-relative checkout directory; `""` asks the sidecar to choose the first discovered checkout under `/workspace`.
- output: raw unified working-tree-versus-`HEAD` diff stdout for the selected checkout, or `""` when no usable diff is available.
- repository selection: an explicit `repo` value selects `/workspace/<repo>` directly; an empty value discovers candidate git checkouts and chooses the sorted first result.
- command: runs local `git -c safe.directory=* -C <selected checkout> diff HEAD` with captured text stdout and a 20-second timeout.
- failure rule: missing checkout discovery, process launch failures, subprocess failures, timeout exceptions, and non-zero git exit statuses all return `""`.
- effects: reads the sidecar container's local workspace and launches a read-only diff subprocess; it does not mutate files, send frames, register connections, broadcast dashboard updates, or fall back to Docker volume readers.
- calls: [method-_find_repo_dirs](#method-_find_repo_dirs) when `repo` is empty, [method-_repo_base](#method-_repo_base) to turn the selected repo value into a local base path, then standard-library subprocess execution for the git command.
- algorithm:
  1. If `repo` is empty, call [method-_find_repo_dirs](#method-_find_repo_dirs) to discover git checkout directories under the sidecar workspace and select the first sorted result.
  2. If no checkout is available, return `""`.
  3. Resolve the selected checkout path with [method-_repo_base](#method-_repo_base).
  4. Run the local git diff command for the selected checkout with captured text output and timeout.
  5. If launching or waiting for the command fails, return `""`.
  6. If the command exits non-zero, return `""`.
  7. Return stdout unchanged.

### method-git_diff

- sig: `git_diff(volume: str, repo_dir: str = "") -> str`
- abstract: false
- raises: no intentional exception for no selected checkout or non-zero git/Docker completion; process-launch and timeout exceptions from the shared Docker subprocess runner can propagate.
- code: groom/groom/docker_io.py::git_diff
- verify: groom/tests/test_docker_io.py::test_git_diff_returns_empty_when_no_repo_found
- verify: groom/tests/test_docker_io.py::test_git_diff_returns_stdout_on_success
- verify: groom/tests/test_docker_io.py::test_git_diff_returns_empty_on_git_failure
- input: `volume` is the selected Docker workspace volume name; `repo_dir` is the optional volume-relative checkout directory from the repository picker or the empty default.
- output: raw unified working-tree-versus-`HEAD` diff stdout for the selected checkout, or `""` when no checkout is selected or the git container exits non-zero.
- repository selection: an explicit non-empty `repo_dir` value selects `/vol/{repo_dir}` directly; an empty value asks the first-repository lookup for the first sorted checkout path in the volume, and an empty lookup result remains the no-checkout state.
- command: runs a temporary read-only Docker container from the git image with the workspace volume mounted at `/vol`, `safe.directory=*`, selected checkout working directory, and `diff HEAD` as the only git command.
- effects: reads Docker volume metadata and launches a read-only Docker diff command; it does not mutate files, send sidecar frames, broadcast dashboard updates, alter workflow state, or create a persistent container.
- calls: [workspace volume repository-directory reader](concepts/workspace-volume-repository-directory-reader.md#find-repo-dir) when `repo_dir` is empty, then the [Docker subprocess runner](concepts/docker-subprocess-runner.md#run) for the read-only git command.
- algorithm:
  1. If `repo_dir` is empty, resolve it with the first-repository lookup for `volume`.
  2. If the resolved repository directory is still empty, return `""` without starting a git command.
  3. Run the throwaway read-only git container against `/vol/{repo_dir}`.
  4. If the command returns non-zero, return `""`.
  5. Return stdout unchanged.

### method-_repo_base

- sig: `_repo_base(repo: str) -> Path`
- abstract: false
- raises: no intentional exception for string input; it does not check whether the returned path exists or is a repository.
- code: groom/groom/sidecar.py::_repo_base
- verify: groom/tests/test_sidecar_session.py::test_git_diff_reports_working_tree_changes
- input: `repo` is the sidecar-local workspace-relative repository selector already chosen by the caller; `""` means the configured sidecar workspace root.
- output: a local filesystem path that should be used as the base directory for the selected repository read.
- root rule: when `repo` is empty or otherwise falsey, the selected base is exactly the configured sidecar workspace root.
- child rule: when `repo` is non-empty, the selected base is the configured sidecar workspace root joined with that value.
- validation: performs no normalization, traversal rejection, `.git` validation, directory existence check, or repository discovery; callers are responsible for passing a trusted selector or applying their own guard before file-content reads.
- effects: observes the sidecar process's configured workspace root and composes a path only; it does not read the filesystem, launch git, mutate files, send websocket frames, call Docker, or update workflow/dashboard state.
- calls: only standard-library path composition; it calls no other groom symbol.
- algorithm:
  1. If `repo` is falsey, return the configured sidecar workspace root.
  2. Otherwise return the configured sidecar workspace root joined with `repo`.

### method-_find_repo_dirs

- sig: `_find_repo_dirs() -> list[str]`
- abstract: false
- raises: no intentional exception for a missing workspace directory; unexpected directory iteration failures can propagate.
- code: groom/groom/sidecar.py::_find_repo_dirs
- verify: groom/tests/test_sidecar_session.py::test_git_diff_empty_when_no_repo
- input: no call-time parameters; discovery reads the sidecar process's configured workspace root.
- output: sorted `list[str]` of workspace-relative checkout directory choices for sidecar diff defaulting.
- root value: `""` represents `/workspace` itself when `/workspace/.git` is a directory.
- child value: a child directory name represents `/workspace/<name>` when that child is a directory, the child name is not `.git`, and `/workspace/<name>/.git` is a directory.
- empty-state: returns `[]` when the configured workspace root is not a directory or when no accepted root or child checkout exists.
- exclusion: does not recurse below immediate children, does not accept a bare `.git` child as a repository option, and does not validate whether accepted `.git` directories are usable git repositories.
- effects: reads directory metadata under the sidecar workspace only; it does not read file contents, launch git, mutate files, send websocket frames, call Docker, or update workflow/dashboard state.
- calls: only standard-library path and sorting operations; it calls no other groom symbol.
- algorithm:
  1. Return `[]` immediately when the configured workspace path is not a directory.
  2. Start with an empty candidate list.
  3. Append `""` when the workspace root contains a directory named `.git`.
  4. Inspect each direct child of the workspace root.
  5. Append a child name only when the child is a directory, the child name is not `.git`, and the child contains a directory named `.git`.
  6. Return the candidate list sorted ascending.
