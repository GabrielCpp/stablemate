---
type: format
slug: workspace-diff-data
title: Workspace diff data
---
# Workspace diff data

Workspace diff data is the diff-viewer contract used by the [serve workspace diff](../http/groom.md#serve-working-tree-diff) invocation, the connected sidecar data plane described by [sidecar live sessions](../sidecar-live-sessions.md), and the fallback [workspace volume diff reader](../concepts/workspace-volume-diff-reader.md). It represents one selected workflow checkout's working-tree changes, against `HEAD` or against where its branch started, as raw unified diff text plus the names of its untracked files and a flag for a failed read. On the sidecar websocket it is the successful `getDiff` [sidecar websocket frame](sidecar-websocket-frame.md) result object under `rpc_result.data`; on the HTTP surface it serializes as the JSON object `{"diff", "untracked", "failed", "reported"}`, plus `repos` when the sidecar names its checkouts and the branch-start members when the branch view was asked for, for the [groom dashboard](../gui/screens/groom-dashboard.md) run Diff tab, described in [changes view](../changes-view.md). The endpoint producer first asks the [sidecar RPC helper](../concepts/sidecar-rpc-helper.md) for the connected sidecar's result and falls back to a volume reader — the local-filesystem one for a native run, the Docker-volume one otherwise — only when that helper returns no data.

The raw unified text stays whole inside the `diff` member instead of being projected into per-file entries. `diff2html` parses it in the browser to build the file list and the coloring, so splitting it up on the server would mean reimplementing a parser that already runs on the other end. The JSON object exists to make the body self-describing and to leave room for a member that is not the diff; it is not an attempt to structure the diff itself. Sidecar diff defaulting discovers local checkout directories with [method-_find_repo_dirs](#method-_find_repo_dirs) before [method-_git_diff](#method-_git_diff) resolves the selected checkout with [method-_repo_base](#method-_repo_base) and runs git against it; fallback diff defaulting delegates empty repository selection to the [workspace volume repository-directory reader](../concepts/workspace-volume-repository-directory-reader.md).

- file: not an on-disk artifact; this is a websocket RPC data object, HTTP response body, and sidecar/fallback handoff shape.
- code: groom/groom/app.py::diff@09402337f758
- code: groom/groom/docker_io.py::read_diff@9069a876d356
- code: groom/groom/localfs.py::read_diff@5e5b04abdd29
- code: groom/groom/gitdiff.py::parse@3a6aaa904d86
- code: groom/groom/assets/dashboard.js::loadRunDiff@6b1e2d0423d6
- code: groom/groom/sidecar.py::_rpc_get_diff@8661ec412d82
- code: groom/groom/sidecar.py::_repo_names@6414bfcac07e
- code: groom/groom/sidecar.py::_git_diff@4a6396f4f32c
- code: groom/groom/gitdiff.py::read_branch_local@66fa6eddc2a9
- code: groom/groom/app.py::_branch_start@06e790f82049
- code: groom/groom/sidecar.py::_repo_base@e9c8c43d932a
- detail: [dashboard diff representation selection](../concepts/dashboard-diff-representation-selection.md)
- tests: groom/tests/test_app.py::test_diff_prefers_sidecar_socket,
  groom/tests/test_app.py::test_diff_endpoint_passes_repo_through,
  groom/tests/test_gitdiff.py::test_a_clean_checkout_reads_as_empty_and_not_failed,
  groom/tests/test_gitdiff.py::test_parse_marks_either_failing_command_as_failed,
  groom/tests/test_app.py::test_diff_endpoint_without_a_view_sends_the_sidecar_no_new_parameter_and_returns_no_base,
  groom/tests/test_app.py::test_diff_endpoint_with_the_branch_view_forwards_it_and_returns_the_base_the_sidecar_computed,
  groom/tests/test_sidecar_session.py::test_a_get_diff_with_no_view_returns_exactly_the_uncommitted_reply

## Contract

- consistency: workspace-diff-data — `GET /diff/{container_id}` returns [field-json-body](#field-json-body) as `application/json`.
- consistency: workspace-diff-data — when sidecar RPC returns data, `GET /diff/{container_id}` uses that data for its response.
- consistency: workspace-diff-data — when sidecar RPC returns no data, `GET /diff/{container_id}` reads from the workflow container's known workspace volume when available.
- sidecar producer: a live sidecar handling `rpc` method `getDiff` returns `{"diff": text, "untracked": [paths], "failed": bool, "repos": [names]}` as the `data` object in a successful `rpc_result` frame after running a working-tree-versus-`HEAD` diff against its local `/workspace` checkout.
- fallback producer: the Docker-volume fallback runs a read-only throwaway git container against one checkout in the selected workflow's workspace volume and returns its stdout as the same raw diff text; a native workflow instead runs git locally against the checkout root through the local-filesystem reader. Both return the same shape, so the endpoint's caller cannot tell which ran.
- sidecar request: the sidecar data-plane request uses [sidecar websocket frame](sidecar-websocket-frame.md) method `getDiff` with `params.repo` and, for the branch view only, `params.view` set to `branch`. Missing `repo` defaults to `""`. A request for the Uncommitted view carries no `view`, so `getDiff` with no new parameter returns exactly the reply it returned before the branch view existed, with no branch-start member.
- endpoint request: the `/diff/{container_id}` endpoint path supplies [field-container-id](#field-container-id); the optional `repo` query parameter is passed unchanged to both the sidecar RPC and the fallback volume reader. The optional `view` query parameter is forwarded to the sidecar only when it is `branch`; any other value reads the Uncommitted view. The parameter is named `view` because Litestar reserves `scope` as a handler keyword.
- websocket consumer: the host-side sidecar RPC resolver delivers the successful `data` object unchanged to the `/diff/{container_id}` endpoint.
- HTTP consumer — run Diff tab: the run detail pane's Diff tab requests the endpoint once when a run with a connected sidecar is selected and again when the operator chooses another checkout, chooses the other view, or refreshes. It sends the run's chosen checkout as `repo`, and `view` `branch` only while the run's switch is on Since branch start, or an empty `repo` before the reply has named any checkout, so the producer's own default checkout selection applies. It parses the `diff` member with diff2html, stores the result as the [dashboard parsed diff file cache](dashboard-parsed-diff-file-cache.md), renders the changed-file tree from that cache, generates per-file markup only when a file is chosen, and lists the `untracked` paths in their own group. It learns the run's checkouts from `repos`.
- served member: the HTTP response adds `served`, `sidecar` when the RPC answered and `volume` for a fallback answer, beside the other members. The sidecar socket does not carry it. The dashboard uses it so a `volume` reply never replaces a kept diff, as [kept run diff](../concepts/kept-run-diff.md) describes.
- repos member: `repos` is the sidecar's list of checkout names, the same names `repo` accepts, and the endpoint passes it through unchanged. A sidecar too old to name its checkouts sends none, the endpoint then omits the member, and the tab shows no selector. The volume and native fallback readers send none. See [run checkout selection](../concepts/run-checkout-selection.md).
- branch view reply: for `view` `branch` the sidecar adds `base` (the merge base commit, or empty), `base_ref` (the ref the default branch was found at, such as `origin/main`, or empty), `base_branch` (the default branch's name, or empty) and `base_reason` (empty when a base was found, else `default-branch` or `not-found`). The endpoint passes them through with `based` true. A sidecar whose reply carries no `base_reason` is too old for the view, and the endpoint sends `based` false instead. The branch view is never answered from a volume or native read: with no sidecar data the endpoint answers an unreadable reply with `reported` true.
- branch start: the default branch is the first that resolves from local refs only, never the network: the ref `origin/HEAD` names, then a local `main`, then a local `master`. The base is `git merge-base HEAD <that ref>`. On the default branch itself there is no base and the reason is `default-branch`. With no default branch, or no common history, the reason is `not-found`. A failed git call is an unreadable read, never a reason.
- branch view diff: the diff text is `git diff <base>` against the working tree, so it holds committed and uncommitted tracked change since the branch started. The untracked names are the same listing as the Uncommitted view.
- read-only: every sidecar git call runs with `diff.autoRefreshIndex=false` and `--no-optional-locks`, because `--no-optional-locks` alone does not stop `git diff` from refreshing the index file.
- tab states: loading, unreadable (the `failed` member is true, a fetch is rejected, or non-empty text does not parse), clean, and unconfirmed (an empty `diff` from a sidecar that sent no `failed` member, which the endpoint marks with `reported` false). An unreadable read never renders as a clean one.
- repository scope: `repo` selects a volume-relative checkout directory, one of the names the `repos` member lists. An empty `repo` lets the sidecar producer choose the first immediate git checkout under `/workspace` and lets the fallback reader choose the first checkout returned by the Docker-volume repository-directory reader.
- sidecar repository default: when `repo` is empty, the sidecar chooses the first discovered git checkout under `/workspace`; discovery includes `/workspace` itself when it is a git checkout and immediate child directories that contain `.git`, then sorts the volume-relative choices before selecting the first. The workspace root checkout is represented as `""`; child checkouts are represented by child directory name only. When no checkout is found, it returns an unreadable result.
- fallback repository default: when `repo` is empty, the fallback reader asks the workspace volume repository-directory reader for sorted checkout paths under the Docker volume and uses the first returned value as the resolved `repo_dir`; when discovery returns no paths, or when the first sorted value is `""` for a volume-root checkout, the diff reader treats the resolved value as no checkout and returns an unreadable result without starting a git container.
- sidecar diff command: sidecar diff text is the stdout of `git -c safe.directory=* -c diff.autoRefreshIndex=false --no-optional-locks -C <selected checkout> diff HEAD`, or `diff <base>` for the branch view, and the untracked names come from `ls-files --others --exclude-standard -z` in the same checkout, each with a 20-second timeout.
- fallback diff command: fallback diff text is the stdout of a read-only `alpine/git:2.43.0` container running `git -c safe.directory=* -C /vol/{repo_dir} diff HEAD` against the mounted workspace volume, with the shared Docker I/O timeout.
- empty-state: an empty `diff` value with `failed` false means the selected checkout had no tracked working-tree changes. An empty `diff` with `failed` true means the read did not happen, and no consumer renders it as no changes.
- error behavior: unavailable repositories, process launch failures, subprocess failures, timeouts, and non-zero diff or untracked-listing statuses become empty diff text with `failed` true for successful producers; unexpected malformed RPC parameters can fail the sidecar RPC and return an error frame under the [sidecar websocket frame](sidecar-websocket-frame.md) contract. An unavailable sidecar connection or sidecar RPC error becomes fallback to the volume reader.
- media: HTTP serialization is `application/json` with four members, plus `repos` when the sidecar names its checkouts, plus `based` and the four `base` members for the branch view. The server does not escape, colorize, split, or annotate the diff text; JSON string encoding is the only transformation it undergoes.
- untracked listing: the producers list untracked, non-ignored files with `git ls-files --others --exclude-standard -z`. Either git command failing fails the whole read.
- no checkout: a sidecar, volume or native read with no checkout to read reports `failed` true.
- push exclusion: this shape is never broadcast. It is fetched on selection and nothing else, so a fleet tick cannot re-render the tab out from under a reading operator.

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
- meaning: volume-relative checkout directory the run's checkout selector chose; an empty value means the sidecar producer or fallback reader chooses the first git checkout it finds by its own repository-discovery rule.
- normalization: the sidecar string-converts the parameter value before selecting a checkout; first-party callers send a plain string.

### field-view

- type: `str`
- default: `""`
- required: false
- wire-key: `view`
- wire-location: `rpc.params.view` for sidecar `getDiff`; HTTP query parameter for `/diff/{container_id}`.
- meaning: `branch` asks for the change since the branch started. Absent or any other value asks for the working tree against `HEAD`.

### field-workspace-volume

- type: `str`
- default: `""`
- required: false
- wire-location: server-side [workflow container](../concepts/workflow-container.md) state, not an HTTP or sidecar frame field.
- meaning: workspace volume name — or, for a native run, the checkout root path — used only by the fallback producer when sidecar RPC data is unavailable. Unknown workflow ids, missing workflow records, and empty values produce an empty `diff` member instead of starting a fallback diff read.

### field-sidecar-result

- type: `dict[str, str] | None`
- default: `None`
- required: false
- wire-location: `rpc_result.data` in a successful [sidecar websocket frame](sidecar-websocket-frame.md) for method `getDiff`
- meaning: optional sidecar RPC result object for method `getDiff`; when present, the endpoint reads its `diff`, `untracked` and `failed` members and does not consult Docker volumes. A result without a `failed` member comes from an old sidecar, and the endpoint reports `reported` false.
- failure rule: absent sidecar connection and sidecar RPC errors are represented as `None` to the endpoint, causing fallback volume lookup.

### field-diff

- type: `str`
- default: `""`
- required: true
- wire-key: `diff`
- wire-location: `rpc_result.data.diff` for sidecar `getDiff`; the `diff` member of the HTTP response body. The two are the same key on purpose — the endpoint passes the sidecar's object shape through rather than renaming into it.
- meaning: raw unified working-tree-versus-`HEAD` diff text for the selected checkout. Missing, falsey, unavailable, timed-out, or non-zero-exit producers become an empty string rather than an endpoint-specific error response.
- item contract: the value is literal unified diff text, not HTML, markdown, JSON, base64, or a pre-rendered file tree; callers must parse or render it as unified diff text.
- ordering: line and hunk order are the order produced by the underlying git diff command; the producer does not post-process, sort, filter, redact, or annotate the stdout.

### field-json-body

- type: `{ "diff": str, "untracked": list[str], "failed": bool, "reported": bool, "repos"?: list[str], "based"?: bool, "base"?: str, "base_ref"?: str, "base_branch"?: str, "base_reason"?: str }`
- default: `{"diff": "", "untracked": [], "failed": true, "reported": true}`
- required: true
- wire-location: body of `GET /diff/{container_id}` with media type `application/json`.
- meaning: the whole HTTP response body. It is the same object shape the sidecar returns under `rpc_result.data`, so the socket path and the volume path hand the endpoint the same thing.
- member rule: `diff` is the raw text, `untracked` names the untracked files, `failed` says the read did not happen, `reported` is false only when an old sidecar sent no `failed` member, `repos` names the run's checkouts when the sidecar can, and `based` and the `base` members are present only for the branch view. No repository label, container id, changed-file count, adds/dels totals, or rendered markup, because the browser derives those from the text.

## Methods

### method-diff

- sig: `async diff(container_id: str, repo: str = "", view: str = "") -> dict`
- abstract: false
- raises: no endpoint-specific exception for unknown workflow id, missing workspace volume, unavailable sidecar connection, sidecar RPC error, falsey sidecar diff, missing checkout, non-zero fallback git exit, or empty diff output.
- verify: json_path(path="exception.type", absent=true)
- raises: unexpected sidecar-registry, Docker subprocess launch/timeout, or response-construction failures can propagate.
- verify: json_path(path="exception.type", matches="Error$")
- verify: json_path(path="$.diff", equals="diff --git a/x b/x\n")
- code: groom/groom/app.py::diff@09402337f758
- detail: [diff documentation scopes](../concepts/diff-documentation-scopes.md)
- tests: groom/tests/test_app.py::test_diff_prefers_sidecar_socket
- tests: groom/tests/test_app.py::test_diff_endpoint_passes_repo_through
- input: `container_id` is the required HTTP path variable; `repo` is the optional query value forwarded unchanged to both producers.
- output: one JSON object, [field-json-body](#field-json-body).
- effects: performs a read-only sidecar RPC attempt or read-only fallback volume diff; it does not mutate workflow state, broadcast dashboard messages, render diff markup, validate repository existence, or write workspace files.
- calls: [sidecar RPC helper](../concepts/sidecar-rpc-helper.md) with method `getDiff`, then [workspace volume diff reader](../concepts/workspace-volume-diff-reader.md#git-diff) or its native equivalent, only when no sidecar data is returned and the workflow has a known workspace volume.
- algorithm:
  1. Request `getDiff` over the connected sidecar data plane with `{"repo": repo}`, adding `"view": "branch"` only when `view` is `branch`.
  2. If the sidecar call returns any data object, return its `diff`, `untracked` and `failed` members plus `reported` (true when the object carries `failed`) `repos` (when the object carries a list), and for the branch view `based` with the `base` members, without consulting the fallback reader.
  3. Look up the workflow container by `container_id` in the in-memory workflow registry.
  4. If the workflow is unknown or has no workspace volume, or the branch view was asked for, return an unreadable result (`failed` true, `reported` true).
  5. Choose the native or Docker differ by the workflow's native flag and run it on a worker thread for the selected volume and `repo` value.
  6. Return the fallback read with `reported` true.

### method-_rpc_get_diff

- sig: `_rpc_get_diff(params: dict) -> dict`
- abstract: false
- raises: no intentional exception when `params` is a mapping and local diff production fails.
- verify: json_path(path="exception.type", absent=true)
- raises: non-mapping `params` values can fail before the sidecar RPC wrapper converts the failure into an error frame.
- verify: json_path(path="exception.type", equals="AttributeError")
- returns: a `diff` value containing the local working-tree changes when the selected checkout has changes.
- verify: json_path(path="$.diff", matches="\\+two")
- returns: an empty `diff` value with `failed` true when no checkout is available.
- verify: json_path(path="$.failed", equals=true)
- code: groom/groom/sidecar.py::_rpc_get_diff@8661ec412d82
- tests: groom/tests/test_sidecar_session.py::test_git_diff_reports_working_tree_changes
- tests: groom/tests/test_sidecar_session.py::test_git_diff_empty_when_no_repo
- tests: groom/tests/test_sidecar_session.py::test_a_get_diff_with_the_branch_view_reads_from_where_the_branch_started
- tests: groom/tests/test_sidecar_session.py::test_a_get_diff_with_the_branch_view_and_no_checkout_is_a_failed_read
- tests: groom/tests/test_sidecar_session.py::test_git_diff_failed_when_the_checkout_is_not_a_git_repo
- input: one sidecar RPC params object for method `getDiff`; the `repo` and `view` members are read.
- output: one JSON-compatible object with `diff` ([workspace diff data](workspace-diff-data.md#field-diff) text), `untracked`, `failed` and `repos` keys, and for the branch view the four `base` keys.
- defaulting: missing `repo` and missing `view` are read as `""`; both values are string-converted.
- effects: performs no websocket send, host-state mutation, file mutation, dashboard broadcast, or fallback Docker read itself; it delegates all local diff reading to [method-_git_diff](#method-_git_diff).
- calls: [method-_git_diff](#method-_git_diff).
- algorithm:
  1. Read `repo` from the params object, defaulting to `""`.
  2. Read `view` the same way.
  3. Return the read from [method-_git_diff](#method-_git_diff) with `repos` added.

### method-_git_diff

- sig: `_git_diff(repo: str, view: str = "") -> DiffRead | BranchRead`
- abstract: false
- raises: no intentional exception for no checkout, subprocess launch failure, subprocess timeout, subprocess failure, or non-zero git exit.
- verify: json_path(path="exception.type", absent=true)
- verify: count(subject="lines in the returned working-tree diff", equals=2)
- verify: count(subject="diff lines when no checkout is available", equals=0)
- raises: unexpected workspace directory iteration failures can propagate.
- verify: json_path(path="exception.type", matches="Error$")
- code: groom/groom/sidecar.py::_git_diff@4a6396f4f32c
- tests: groom/tests/test_sidecar_session.py::test_git_diff_reports_working_tree_changes
- tests: groom/tests/test_sidecar_session.py::test_git_diff_empty_when_no_repo
- tests: groom/tests/test_sidecar_session.py::test_a_get_diff_with_the_branch_view_reads_from_where_the_branch_started
- tests: groom/tests/test_sidecar_session.py::test_a_get_diff_with_the_branch_view_and_no_checkout_is_a_failed_read
- input: `repo` is a workspace-relative checkout directory; `""` asks the sidecar to choose the first discovered checkout under `/workspace`.
- output: raw unified working-tree-versus-`HEAD` diff stdout and the untracked file names for the selected checkout, or an unreadable result (`failed` true) when no usable diff is available.
- repository selection: an explicit `repo` value selects `/workspace/<repo>` directly; an empty value discovers candidate git checkouts and chooses the sorted first result.
- command: runs local `git -c safe.directory=* -c diff.autoRefreshIndex=false --no-optional-locks -C <selected checkout> diff HEAD`, or for the branch view `diff <merge base>` after resolving the base, then `ls-files --others --exclude-standard -z`, each with captured text stdout and a 20-second timeout.
- failure rule: missing checkout discovery, process launch failures, subprocess failures, timeout exceptions, and non-zero git exit statuses all return an unreadable result.
- effects: reads the sidecar container's local workspace and launches a read-only diff subprocess; it does not mutate files, send frames, register connections, broadcast dashboard updates, or fall back to Docker volume readers.
- calls: [method-_find_repo_dirs](#method-_find_repo_dirs) when `repo` is empty, [method-_repo_base](#method-_repo_base) to turn the selected repo value into a local base path, then standard-library subprocess execution for the git command.
- algorithm:
  1. If `repo` is empty, call [method-_find_repo_dirs](#method-_find_repo_dirs) to discover git checkout directories under the sidecar workspace and select the first sorted result.
  2. If no checkout is available, return an unreadable result.
  3. Resolve the selected checkout path with [method-_repo_base](#method-_repo_base).
  4. For the Uncommitted view, run the local git diff command for the selected checkout with captured text output and timeout. For the branch view, find the merge base of `HEAD` and the default branch first, and run `diff <base>`, or return the reason there is no base with an empty diff and `failed` false.
  5. Run `git ls-files --others --exclude-standard -z` for the untracked names.
  6. If launching or waiting for either command fails, or either exits non-zero, return an unreadable result.
  7. Return the stdout and the untracked names unchanged.

### method-git_diff

- sig: `read_diff(volume: str, repo_dir: str = "") -> DiffRead`
- abstract: false
- raises: no intentional exception for no selected checkout or non-zero git/Docker completion.
- verify: count(subject="diff lines when no checkout is available", equals=0)
- verify: count(subject="changed lines in the returned working-tree diff", equals=2)
- verify: count(subject="diff lines when the git container exits non-zero", equals=0)
- raises: process-launch and timeout exceptions from the shared Docker subprocess runner can propagate.
- verify: json_path(path="exception.type", matches="(OSError|TimeoutExpired)")
- code: groom/groom/docker_io.py::read_diff@9069a876d356
- detail: [Docker git diff documentation scope](../concepts/docker-git-diff-documentation-scope.md)
- tests: groom/tests/test_docker_io.py::test_read_diff_fails_when_no_repo_found
- tests: groom/tests/test_docker_io.py::test_read_diff_returns_stdout_and_untracked_on_success
- tests: groom/tests/test_docker_io.py::test_read_diff_fails_on_git_failure
- tests: groom/tests/test_docker_io.py::test_read_diff_fails_when_docker_cannot_run
- input: `volume` is the selected Docker workspace volume name; `repo_dir` is the optional volume-relative checkout directory from the run's checkout selector or the empty default.
- output: raw unified working-tree-versus-`HEAD` diff stdout and the untracked file names, or an unreadable result when no checkout is selected or a git container exits non-zero.
- repository selection: an explicit non-empty `repo_dir` value selects `/vol/{repo_dir}` directly; an empty value asks the first-repository lookup for the first sorted checkout path in the volume, and an empty lookup result remains the no-checkout state.
- command: runs a temporary read-only Docker container from the git image with the workspace volume mounted at `/vol`, `safe.directory=*`, selected checkout working directory, and `diff HEAD` then `ls-files --others --exclude-standard -z` as its two git commands.
- effects: reads Docker volume metadata and launches a read-only Docker diff command; it does not mutate files, send sidecar frames, broadcast dashboard updates, alter workflow state, or create a persistent container.
- calls: [workspace volume repository-directory reader](../concepts/workspace-volume-repository-directory-reader.md#find-repo-dir) when `repo_dir` is empty, then the [Docker subprocess runner](../concepts/docker-subprocess-runner.md#run) for the read-only git command.
- algorithm:
  1. If `repo_dir` is empty, resolve it with the first-repository lookup for `volume`.
  2. If the resolved repository directory is still empty, return an unreadable result without starting a git command.
  3. Run the throwaway read-only git container for `diff HEAD` against `/vol/{repo_dir}`, then a second one for the untracked listing.
  4. If either command fails to launch or returns non-zero, return an unreadable result.
  5. Return stdout and the untracked names unchanged.

### method-git-diff-native

- sig: `read_diff(base: str, repo_dir: str = "") -> DiffRead`
- abstract: false
- raises: no intentional exception when no checkout resolves.
- verify: count(subject="diff lines when no checkout is available", equals=0)
- raises: process-launch failures become an unreadable result.
- verify: count(subject="diff lines when the git process cannot launch", equals=0)
- raises: subprocess errors become an unreadable result.
- verify: count(subject="diff lines when git raises a subprocess error", equals=0)
- raises: the shared timeout becomes an unreadable result.
- verify: count(subject="diff lines when git exceeds the shared timeout", equals=0)
- code: groom/groom/localfs.py::read_diff@5e5b04abdd29
- detail: [native git diff documentation scope](../concepts/native-git-diff-documentation-scope.md)
- input: `base` is the native run's checkout root on the groom host; `repo_dir` is the optional base-relative checkout directory from the run's checkout selector.
- output: raw unified working-tree-versus-`HEAD` diff stdout for the selected checkout, and the untracked file names, or an unreadable result when no checkout resolves or git exits non-zero.
- repository selection: resolves `base/repo_dir` first; when that does not resolve and no `repo_dir` was supplied, asks the base's first-checkout lookup and resolves again. An unresolvable base returns an unreadable result without running git.
- command: runs host-local `git -c safe.directory=* -C <selected checkout> diff HEAD` and then `ls-files --others --exclude-standard -z` with captured text output and the shared Docker I/O timeout, so a wedged git cannot pin the thread pool.
- effects: reads the host filesystem and launches one read-only git subprocess; it does not mutate files, touch Docker, send sidecar frames, or update workflow/dashboard state.
- parity: returns the same read the Docker-volume reader would for the same checkout, which is what lets the endpoint pick between them by a boolean and return one shape.

### method-_repo_base

- sig: `_repo_base(repo: str) -> Path`
- abstract: false
- raises: no intentional exception for string input.
- verify: json_path(path="exception.type", absent=true)
- raises: does not check whether the returned path exists or is a repository.
- verify: json_path(path="returned_path", equals="/workspace/missing")
- code: groom/groom/sidecar.py::_repo_base
- tests: groom/tests/test_sidecar_session.py::test_git_diff_reports_working_tree_changes
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
- raises: no intentional exception for a missing workspace directory.
- verify: json_path(path="exception.type", absent=true)
- raises: unexpected directory iteration failures can propagate.
- verify: json_path(path="exception.type", matches=".+")
- verify: count(subject="discovered checkout directory choices", equals=0)
- code: groom/groom/sidecar.py::_find_repo_dirs
- tests: groom/tests/test_sidecar_session.py::test_git_diff_empty_when_no_repo
- tests: groom/tests/test_sidecar_session.py::test_a_get_diff_with_the_branch_view_reads_from_where_the_branch_started
- tests: groom/tests/test_sidecar_session.py::test_a_get_diff_with_the_branch_view_and_no_checkout_is_a_failed_read
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
