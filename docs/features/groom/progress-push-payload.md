---
type: format
slug: progress-push-payload
title: Progress push payload
---
# Progress push payload

Progress push payload is the JSON request body accepted by the [receive progress push](http/groom.md#receive-progress-push) invocation on the [groom server](http/groom.md). It is produced by the residual HTTP progress path through the [sidecar residual HTTP push helper](concepts/sidecar-residual-http-push-helper.md), described in [sidecar protocol](sidecar-protocol.md), and updates one [workflow container](concepts/workflow-container.md) in the [workflow registry](concepts/workflow-registry.md) to [workflow state](concepts/workflow-state.md) `running` after the [push-first volume metadata resolver](concepts/push-first-volume-metadata-resolver.md) has had a chance to hydrate volume metadata. It is the residual HTTP counterpart of the websocket [sidecar progress applier](concepts/sidecar-progress-applier.md): both carry a current-node liveness delta and neither clears gates or terminal metadata.

- file: not an on-disk artifact; this is a best-effort HTTP JSON request body for `POST /push/progress`.
- code: groom/groom/app.py::push_progress
- code: groom/groom/sidecar.py::push_progress
- verify: groom/tests/test_sidecar.py::test_push_progress_posts_expected_shape
- verify: groom/tests/test_sidecar.py::test_handle_event_under_runs_triggers_progress_push
- verify: groom/tests/test_sidecar.py::test_push_is_silent_when_groom_is_unreachable
- verify: groom/tests/test_sidecar.py::test_push_is_silent_on_any_unexpected_exception
- verify: groom/tests/test_sidecar_session.py::test_classify_event_runs_write_is_progress

## Contract

- shape: a JSON object; arrays, strings, numbers, booleans, and `null` are not valid semantic payloads for this endpoint because the handler expects object-style key lookup.
- producer: `groom-sidecar` calls `push_progress(current_node)` with a current-node string, then the residual push helper merges [sidecar identity data](sidecar-identity-data.md) with `{"current_node": current_node}` and posts the merged object to `/push/progress`.
- producer-trigger: an inotify write under the configured `/runs` tree is classified as progress and supplies the sidecar's current-node snapshot; compatible backstop clients may send the same object fields directly.
- producer identity: first-party residual pushes include `container_id`, `name`, `repo_name`, and `repo_branch` before the explicit `current_node` field is merged; explicit event payload keys win on collision, though the current progress wrapper supplies only `current_node`.
- producer endpoint: the sidecar posts the serialized JSON object to `http://{GROOM_HOST}:{GROOM_PORT}/push/progress`, where `GROOM_HOST` defaults to `host.docker.internal` and `GROOM_PORT` defaults to `8787`.
- producer transport: the first-party sidecar serializes the merged object as UTF-8 JSON, declares `Content-Type: application/json`, performs exactly one HTTP `POST` attempt, closes the response object when a response is opened, ignores the response body, and performs no command-line output for this notice path.
- producer timeout: the sidecar uses `GROOM_PUSH_TIMEOUT` seconds for the HTTP call, defaulting to `1.0`; connection failures, HTTP-open failures, response-close failures, and unexpected exceptions are ignored so progress reporting never blocks or changes workflow execution.
- consumer: the progress-push endpoint accepts the parsed JSON object and ignores fields other than `container_id`, `name`, `repo_name`, `repo_branch`, and `current_node`.
- object rule: no envelope, nested object, ordered field layout, route parameter, query parameter, cookie, authentication token, or required request header participates in this payload contract beyond the JSON body being parsed for object-style key lookup.
- id normalization: `container_id` is read with missing default `""`, converted to text, and truncated to 12 characters before any state lookup or mutation.
- null rule: explicit JSON `null` for `container_id` is converted to the text `"None"` and is therefore accepted by the endpoint; explicit JSON `null` for `name`, `repo_name`, `repo_branch`, or `current_node` means preserve the existing in-memory field for existing workflows.
- success guard: an empty normalized `container_id` is invalid and yields `ok: false` with no Docker metadata resolution, no workflow create/update, and no dashboard broadcast.
- overwrite rule: optional identity and current-node fields update the workflow only when their value is not `null`; omitted or `null` values preserve the existing in-memory field, while empty strings and non-string JSON values are non-null and therefore are passed through to the registry fields that accept them.
- initial-name rule: if the payload creates a new workflow, a truthy `name` becomes the initial workflow name; an omitted, `null`, or empty-string `name` falls back to the normalized container id.
- metadata rule: before applying the visible progress update, the endpoint tries push-first Docker metadata hydration for workflows that are absent or do not yet have a workspace volume; this can fill `workspace_volume`, `runs_volume`, and `workflow_type` independently of the JSON payload.
- state result: a valid payload marks the workflow as `running` and preserves open gates, exit code, run id, and any existing type/volume metadata unless Docker metadata resolution fills type/volume fields first.
- broadcast result: after a successful workflow upsert, the endpoint broadcasts a fresh dashboard shell fragment to connected dashboard clients and then returns `ok: true`.
- non-effects: this payload does not clear gates, mark a workflow blocked or finished, record an exit code, append a log event, answer a gate file, prune workflows, start discovery, authenticate a caller, or persist data outside the groom process.
- response: normal handler return is a JSON object `{"ok": bool}`; `false` means the normalized container id was empty, and `true` means metadata resolution, workflow upsert, and dashboard broadcast completed.
- error result: malformed JSON, non-object request bodies rejected before handler object lookup, Docker metadata lookup failures, shell rendering failures, and dashboard broadcast failures do not use this format's `ok: false` response; they propagate through the framework error path.

## Fields

### field-container-id

- type: string-convertible JSON value
- default: `""`
- required: true
- meaning: workflow container id; the handler converts it with `str(value)[:12]`, rejects the request when the result is empty, and uses the normalized value as the workflow registry key.
- producer: first-party residual HTTP pushes set this from the sidecar process hostname truncated to 12 characters before serialization.
- consumer: the handler converts the value with `str(value)[:12]`, rejects only an empty normalized result, and does not verify that the id names a Docker container before attempting push-first metadata hydration.
- constraints: required for a useful update but not required by JSON parsing; an absent key uses the missing default and is rejected, an empty string is rejected, values longer than 12 characters collide by their first 12 characters, and explicit JSON `null` becomes `"None"` and is treated as present.

### field-name

- type: any JSON value accepted by workflow name assignment
- default: omitted
- required: false
- meaning: human-facing workflow/container label; when present and non-null on an existing workflow, replaces the workflow's current `name`, otherwise the existing value remains.
- producer: first-party residual HTTP pushes set this to `REPO_NAME` when that environment variable is non-empty, otherwise to the sidecar process hostname.
- consumer: the handler passes the value to the workflow registry without text conversion; the registry applies non-null values to existing records and chooses a newly created workflow's initial name from the truthy value or from the normalized container id.
- constraints: for a newly created workflow, a truthy value becomes the initial name; omitted, `null`, or empty-string values create the workflow with the normalized container id as its name. Downstream dashboard rendering and searching expect a string-like value.

### field-repo-name

- type: any JSON value accepted by workflow repository-name assignment
- default: omitted
- required: false
- meaning: repository name shown in dashboard identity text; when present and non-null, replaces the workflow's current `repo_name`.
- producer: first-party residual HTTP pushes set this from `REPO_NAME`, defaulting to an empty string when the environment variable is absent.
- consumer: the handler passes the value to the workflow registry without text conversion, and the registry applies it only when it is not `null`.
- constraints: an empty string is non-null and therefore can intentionally clear or leave blank the repository-name display field. Downstream dashboard rendering and searching expect a string-like value.

### field-repo-branch

- type: any JSON value accepted by workflow repository-branch assignment
- default: omitted
- required: false
- meaning: repository branch shown with the repository name; when present and non-null, replaces the workflow's current `repo_branch`.
- producer: first-party residual HTTP pushes set this from `REPO_BRANCH`, defaulting to an empty string when the environment variable is absent.
- consumer: the handler passes the value to the workflow registry without text conversion, and the registry applies it only when it is not `null`.
- constraints: an empty string is non-null and therefore can intentionally clear or leave blank the repository-branch display field. Downstream dashboard rendering and searching expect a string-like value.

### field-current-node

- type: any JSON value accepted by workflow current-node assignment
- default: omitted
- required: false
- meaning: current workhorse node label shown in dashboard metadata; when present and non-null, replaces the workflow's current `current_node` while the workflow is marked running.
- producer: first-party residual HTTP progress pushes set this from the progress event's current-node snapshot; when called without an argument, the sidecar sends an empty string.
- consumer: the handler passes the value to the workflow registry without text conversion, and the registry applies it only when it is not `null` while always setting workflow state to `running` on the success path.
- constraints: omitted or `null` preserves the previous current node; an empty string is non-null and therefore writes an explicitly unknown/blank current-node value while still marking the workflow running. Downstream dashboard rendering and searching expect a string-like value.

### field-ignored-fields

- type: any JSON member whose key is not `container_id`, `name`, `repo_name`, `repo_branch`, or `current_node`
- default: omitted
- required: false
- meaning: extension or accidental fields in the request body that the current consumer does not read.
- producer: first-party residual HTTP progress pushes do not add ignored fields; compatible clients may include them without changing current handler behavior.
- consumer: the endpoint never passes ignored keys to the workflow registry, Docker metadata resolver, shell renderer, dashboard websocket broadcaster, or response object.
- constraints: ignored keys do not make the request invalid, do not affect the response body, do not create or update workflow-container fields, and do not create forward-compatibility guarantees for future consumers.
