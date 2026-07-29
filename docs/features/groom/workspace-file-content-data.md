---
type: format
slug: workspace-file-content-data
title: Workspace file content data
---
# Workspace file content data

Workspace file content data is the file-viewer contract used by the [serve workspace file content](http/groom.md#serve-workspace-file-content) invocation, the connected sidecar data plane described by [sidecar live sessions](sidecar-live-sessions.md), and the fallback [workspace volume file-content reader](concepts/workspace-volume-file-content-reader.md). It represents one selected workflow checkout file as raw text, with sidecar-local read paths constrained by the [sidecar-local relative path guard](concepts/sidecar-local-relative-path-guard.md) and fallback read paths constrained by the [workspace volume relative path guard](concepts/workspace-volume-relative-path-guard.md). On the sidecar websocket it is the successful `getFile` [sidecar websocket frame](sidecar-websocket-frame.md) result object under `rpc_result.data`; on the HTTP surface it serializes as the JSON object `{"path", "content", "lang"}` for the [groom dashboard](gui/screens/groom-dashboard.md) Files panel.

The HTTP body carries more than the sidecar result object does, and deliberately. `path` echoes what was asked for, so a viewer that fired two requests can drop the loser instead of showing the wrong file's text under the right file's heading. `lang` is the highlight.js grammar the file name implies, decided on the server so the extension table lives in one place next to the rest of the presentation policy rather than being duplicated in the viewer.

- file: not an on-disk artifact; this is a websocket RPC data object, HTTP response body, and sidecar/fallback handoff shape.
- code: groom/groom/app.py::file_content
- code: groom/groom/sidecar.py::_rpc_get_file
- code: groom/groom/projection.py::file_lang
- code: groom/groom/assets/dashboard.js::openFile
- code: groom/groom/assets/dashboard.js::FileView
- verify: groom/tests/test_app.py::test_file_content_prefers_sidecar_socket,
  groom/tests/test_app.py::test_file_endpoint_joins_repo_and_path_and_returns_content,
  groom/tests/test_app.py::test_file_endpoint_swallows_unsafe_path,
  groom/tests/test_sidecar_session.py::test_rpc_get_file_reads_local_file,
  groom/tests/test_sidecar_session.py::test_rpc_get_file_rejects_traversal,
  groom/tests/test_sidecar_session.py::test_handle_rpc_get_file_traversal_replies_error

## Contract

- sidecar producer: a live sidecar handling `rpc` method `getFile` returns `{"content": text}` as the `data` object in a successful `rpc_result` frame after reading the selected file from its local `/workspace` mount.
- endpoint producer: the `/file/{container_id}` endpoint first asks the live sidecar for a `getFile` result and otherwise asks the fallback volume reader for the selected path's text.
- sidecar request boundary: the host request is a [sidecar websocket frame](sidecar-websocket-frame.md) with method `getFile` and `params` containing `repo` plus `path`; the returned `data` object is this format's object envelope, not the final HTTP body.
- fallback boundary: the fallback reader — the local-filesystem one for a native run, the Docker-volume one otherwise — returns raw text or `None`; the endpoint serializes falsey fallback output as the same empty `content` member used for missing sidecar content.
- websocket consumer: the host-side sidecar RPC resolver delivers the successful `data` object unchanged to the `/file/{container_id}` endpoint, which reads only its `content` member and supplies `path` and `lang` itself.
- HTTP consumer: the Files pane's file opener parses the JSON body, discards it when a later click has already changed the selected path, and otherwise stores `path`, `content`, and `lang` in the client store; the file view renders the text and asks highlight.js for the named grammar.
- sidecar wire shape: sidecar success is exactly a JSON-compatible object whose first-party member is `content`; any additional members would be ignored by the HTTP endpoint and dashboard consumer.
- path scope: `repo` and `path` select one file inside the workflow workspace volume; `repo` is prepended to `path` when present, and an empty combined path produces empty content.
- path normalization: first-party producers convert missing `repo` and `path` values to `""` before composing the read path; the sidecar string-converts supplied values before validation.
- path safety: sidecar reads reject absolute paths, empty path segments, and parent traversal through the [sidecar-local relative path guard](concepts/sidecar-local-relative-path-guard.md) before reading; fallback reads apply the same relative-path safety contract through the [workspace volume relative path guard](concepts/workspace-volume-relative-path-guard.md).
- empty-state: an empty `content` value means no file is selected, the selected file is empty, or no content is available from the sidecar or fallback path; clients render the `(empty or binary file)` viewer state rather than reporting a transport error.
- error behavior: missing files and unreadable files become empty content; an unsafe sidecar path becomes an `ok=false` `rpc_result` so the endpoint can fall back, and an unsafe fallback path becomes a `200 OK` body with empty `content`. A rejected fetch is the client's only error signal, and it renders `failed to load`.
- decoding: sidecar file reads decode text with replacement for invalid characters before placing it in `content`; fallback volume reads return the text stream captured from the reader process.
- media: HTTP serialization is `application/json`. The server does not escape, highlight, wrap, or truncate the text — `content` is the file's bytes decoded to a string and nothing else. The only thing the server adds is the echoed `path` and the projected `lang`.
- language scope: `lang` is presentation policy, not file metadata. It is derived from the requested path alone — never from the content — so it is answerable before the read happens and is the same on the success and empty-content paths.
- markup boundary: the value is JSON data rendered as text. The one place it becomes markup is highlight.js output, whose escaping the viewer relies on; when highlight.js is absent, refuses the grammar, or throws, the viewer interpolates the raw text as text instead of assigning markup.
- empty language: an unmapped extension and an extensionless file both project `""`, which the viewer reads as *let highlight.js auto-detect* rather than as *do not highlight*.

## Fields

### field-container-id

- type: `str`
- default: none
- required: true
- meaning: workflow container id from the route path; it selects the live sidecar connection and, when the socket path is unavailable, the workflow record whose `workspace_volume` enables fallback reads.
- wire-location: `/file/{container_id}` route segment; not present in the sidecar `getFile` result object or the HTTP response body.

### field-rpc-method

- type: literal `"getFile"`
- default: none
- required: true for sidecar RPC requests
- wire-key: `method`
- wire-location: [sidecar websocket frame](sidecar-websocket-frame.md) request object sent by the host to the sidecar; not present in the returned `content` object or HTTP response body.
- meaning: selects the sidecar-local file-content producer. Any other method value is outside this format and is dispatched through another sidecar data-plane format or rejected by the sidecar RPC wrapper.

### field-repo

- type: `str`
- default: `""`
- required: false
- meaning: volume-relative checkout directory chosen by the repository picker; an empty value means the file path is relative to the workspace volume root.
- wire-key: `repo`
- wire-location: `rpc.params.repo` for sidecar `getFile` and `/file/{container_id}?repo=...` for the HTTP endpoint; not present in the returned `content` object or HTTP response body.
- normalization: first-party callers default this value to `""`; the sidecar string-converts the value before composing the local workspace path.

### field-path

- type: `str`
- default: `""`
- required: false
- meaning: repo-relative file path chosen from the Files panel tree; an empty value means no file is selected and produces an empty response body.
- wire-key: `path`
- wire-location: `rpc.params.path` for sidecar `getFile` and `/file/{container_id}?path=...` for the HTTP endpoint; not present in the returned `content` object, but echoed back as the HTTP body's `path` member.
- normalization: first-party callers default this value to `""`; the sidecar string-converts the value before composing the local workspace path.

### field-sidecar-result

- type: `dict[str, str] | None`
- default: `None`
- required: false
- wire-location: `rpc_result.data` in a successful [sidecar websocket frame](sidecar-websocket-frame.md) for method `getFile`
- meaning: optional sidecar RPC result object for method `getFile`; when present, the endpoint reads only its `content` member and does not consult Docker volumes.
- failure rule: absent sidecar connection and sidecar RPC errors are represented as `None` to the endpoint, causing fallback volume lookup.
- ignored members: any sidecar result members other than `content` are ignored by the HTTP endpoint for this format.

### field-workspace-volume

- type: `str`
- default: `""`
- required: false
- wire-location: process-local workflow registry only; not present in sidecar frames, query strings, result objects, or HTTP response bodies.
- meaning: workspace volume or checkout root used by the fallback reader — the local-filesystem one for a native run, the Docker-volume one otherwise — when no successful sidecar result is available.
- empty rule: an absent workflow record or empty volume name prevents fallback reads and produces a response body with empty `content`.

### field-content

- type: `str`
- default: `""`
- required: true
- wire-key: `content`
- wire-location: `rpc_result.data.content` for sidecar `getFile`; the `content` member of the HTTP response body.
- meaning: raw selected file text. Missing, falsey, unavailable, unreadable, or failed producers become an empty string rather than an endpoint-specific error response.
- item contract: the value is literal file text, not HTML, markdown, syntax-highlighted markup, base64, or a structured diff; callers must preserve it as text when rendering.

### field-response-path

- type: `str`
- default: `""`
- required: true
- wire-key: `path`
- wire-location: the `path` member of the HTTP response body; not present in the sidecar `getFile` result object, which the endpoint supplies this value for.
- meaning: the requested repo-relative path, echoed verbatim. It is the correlation token that lets the viewer drop a response whose file is no longer the selected one, and it is the heading the viewer shows above the text.
- derivation: the endpoint's own `path` argument, unchanged by the sidecar result, the fallback read, or any failure branch.

### field-lang

- type: `str`
- default: `""`
- required: true
- wire-key: `lang`
- wire-location: the `lang` member of the HTTP response body; not present in the sidecar `getFile` result object.
- code: groom/groom/projection.py::file_lang
- meaning: the highlight.js grammar name the file name implies. `""` means no mapping was found and the viewer should let highlight.js auto-detect.
- derivation: lowercased basename; `dockerfile` and `makefile` map by whole name, everything else by extension through the projection module's extension table. Content is never inspected.
- stability: computed before the read, so it is identical on the sidecar, fallback, empty, and guard-rejected paths for the same requested path.

### field-json-body

- type: `{ "path": str, "content": str, "lang": str }`
- default: `{"path": "", "content": "", "lang": ""}`
- required: true
- wire-location: body of `GET /file/{container_id}` with media type `application/json`.
- meaning: the whole HTTP response body. Three members, always all three, on every intentional return.
- member rule: no status field, error sentinel, container id, repository label, byte count, mtime, or truncation flag. The sidecar/fallback distinction is invisible here on purpose — the viewer must not be able to tell which producer answered.

## Methods

### method-_rpc_get_file

- sig: `_rpc_get_file(params: dict) -> dict`
- abstract: false
- raises: `ValueError` for unsafe composed paths; unreadable, missing, or unavailable files are intentionally converted to empty content instead.
- code: groom/groom/sidecar.py::_rpc_get_file
- verify: groom/tests/test_sidecar_session.py::test_rpc_get_file_reads_local_file
- verify: groom/tests/test_sidecar_session.py::test_rpc_get_file_rejects_traversal
- input: decoded sidecar RPC params object for method `getFile`; `repo` selects the workspace-relative checkout directory and `path` selects the repo-relative file.
- output: JSON-compatible object with exactly the first-party `content` member for the selected file text.
- effects: reads at most one text file from the sidecar container's local workspace; does not send websocket frames, serialize JSON, call Docker, run Git, mutate workspace files, mutate workflow state, register sidecars, or broadcast dashboard updates.
- path composition: when `repo` is non-empty, combines it with `path` as `repo/path` after removing leading slashes from the combined value; when `repo` is empty, uses `path` unchanged.
- empty rule: when the composed relative path is empty, returns `{"content": ""}` without validating a path or touching the filesystem.
- validation: validates the composed relative path with the [sidecar-local relative path guard](concepts/sidecar-local-relative-path-guard.md) before reading; absolute paths, empty path segments, and parent traversal raise `ValueError` to the RPC wrapper so the websocket reply becomes an `ok=false` `rpc_result`.
- read rule: reads the selected local workspace file as text with replacement for invalid characters; any `OSError` while reading becomes `{"content": ""}`.
- calls: [sidecar-local relative path guard](concepts/sidecar-local-relative-path-guard.md) at `groom/groom/sidecar.py::_safe_relpath`; otherwise only local filesystem text reading is used.
- algorithm:
  1. Read `repo` and `path` from the params object, defaulting each to `""`.
  2. Convert both values to text.
  3. Compose a workspace-relative read path from `repo` and `path`.
  4. If the composed read path is empty, return an empty `content` object.
  5. Validate the composed path with the [sidecar-local relative path guard](concepts/sidecar-local-relative-path-guard.md).
  6. Read the selected file below the sidecar workspace using replacement decoding.
  7. If the read fails with `OSError`, use empty text.
  8. Return the text under the `content` key.

### method-file_content

- sig: `async file_content(container_id: str, repo: str = "", path: str = "") -> dict`
- abstract: false
- raises: no intentional exception for absent workflow state, absent sidecar connection, sidecar RPC failure, empty selected path, unsafe fallback path, missing fallback file, unreadable fallback file, or falsey producer output; unexpected HTTP framework failures or fallback reader exceptions other than `ValueError` can propagate.
- code: groom/groom/app.py::file_content
- verify: groom/tests/test_app.py::test_file_content_prefers_sidecar_socket
- verify: groom/tests/test_app.py::test_file_endpoint_joins_repo_and_path_and_returns_content
- verify: groom/tests/test_app.py::test_file_endpoint_swallows_unsafe_path
- input: `container_id` is the route-selected workflow container id; `repo` is the optional volume-relative checkout directory; `path` is the optional repo-relative file path.
- output: one JSON object with `path`, `content`, and `lang`; `content` is empty when neither the connected sidecar nor the fallback reader supplies truthy text.
- effects: may send one `getFile` RPC through the [sidecar RPC helper](concepts/sidecar-rpc-helper.md), may read one fallback file through the [workspace volume file-content reader](concepts/workspace-volume-file-content-reader.md) or its native equivalent, and never mutates workflow registry state, sidecar registrations, workspace files, dashboard clients, file trees, diffs, or viewer state.
- language first: projects `lang` from the requested path before doing any I/O, so every return path below carries the same value and no branch can forget it.
- sidecar preference: calls the sidecar data plane first with method `getFile` and params `{"repo": repo, "path": path}`; any non-`None` result wins over the volume fallback, even when its `content` member is missing or falsey.
- sidecar serialization: reads `content` from the returned sidecar result object and returns `served.get("content") or ""` under the `content` member. The sidecar's other members, if any, do not reach the body.
- fallback selection: uses the process-local workflow registry only after the sidecar helper returns `None`; the selected workflow must exist and carry a non-empty workspace volume before a fallback read can occur. A native workflow reads through the local-filesystem reader, everything else through the Docker-volume reader.
- fallback path composition: when `repo` is non-empty, composes `repo/path` and strips leading slashes from the combined value; when `repo` is empty, uses `path` unchanged.
- fallback empty rule: missing workspace volume, empty composed path, fallback path `ValueError`, fallback reader `None`, and falsey fallback text all return the same `200 OK` body with empty `content` — the guard rejection is deliberately indistinguishable from a missing file, so a probe learns nothing from the difference.
- media rule: every intentional return is `application/json` with the same three members; the method does not escape content, add syntax highlighting, attach an error sentinel, or vary the status code.
- calls: [sidecar RPC helper](concepts/sidecar-rpc-helper.md) for connected sidecar reads, [workflow registry](concepts/workflow-registry.md) for fallback volume lookup, the [groom projection module](concepts/groom-projection-module.md) for the language, and [workspace volume file-content reader](concepts/workspace-volume-file-content-reader.md) for volume fallback reads.
- algorithm:
  1. Project `lang` from the requested path.
  2. Ask the sidecar RPC helper for `getFile` with the selected repository and file path.
  3. If a sidecar result object is returned, return `path`, its `content` member or `""`, and `lang`, and stop.
  4. Look up the workflow record for the selected container id and read its workspace volume name when present.
  5. Compose the fallback relative path from `repo` and `path`.
  6. If the workspace volume or composed relative path is empty, return the body with empty `content`.
  7. Choose the native or Docker reader by the workflow's native flag and read the file on a worker thread.
  8. If the reader rejects the path with `ValueError`, return the body with empty `content`.
  9. Return the fallback text when truthy, otherwise empty `content`.
