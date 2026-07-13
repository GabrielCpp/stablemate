---
type: format
slug: blocked-push-payload
title: Blocked push payload
---
# Blocked push payload

Blocked push payload is the JSON request body accepted by the [receive blocked push](http/groom.md#receive-blocked-push) invocation on the [groom server](http/groom.md). It is produced by the residual HTTP path in [sidecar protocol](sidecar-protocol.md) through the [sidecar residual HTTP push helper](concepts/sidecar-residual-http-push-helper.md), and records one open [gate info](concepts/gate-info.md) entry on a [workflow container](concepts/workflow-container.md), marking that workflow blocked and notifying connected dashboard tabs with a [blocked notification script fragment](blocked-notification-script-fragment.md). It is the residual HTTP counterpart of the websocket [sidecar blocked applier](concepts/sidecar-blocked-applier.md): both carry one gate-file delta, replace only that gate key, and leave other open gates intact.

- file: not an on-disk artifact; this is a best-effort HTTP JSON request body for `POST /push/blocked`.
- code: groom/groom/app.py::push_blocked
- code: groom/groom/sidecar.py::push_blocked
- verify: groom/tests/test_sidecar.py::test_push_blocked_posts_expected_shape
- verify: groom/tests/test_sidecar.py::test_handle_event_on_awaiting_gate_triggers_blocked_push
- verify: groom/tests/test_sidecar.py::test_push_is_silent_when_groom_is_unreachable
- verify: groom/tests/test_sidecar.py::test_push_is_silent_on_any_unexpected_exception
- verify: groom/tests/test_sidecar_session.py::test_classify_event_awaiting_gate_is_blocked

## Contract

- shape: a JSON object; arrays, strings, numbers, booleans, and `null` are not valid semantic payloads for this endpoint because the handler expects object-style key lookup.
- producer: `groom-sidecar` calls `push_blocked(file_path, question)` when an awaiting gate file is observed, and the await-operator backstop may send the same shape when the sidecar notification path is unavailable; compatible clients may send the same object fields directly.
- producer identity: the first-party residual helper merges sidecar identity into the explicit gate payload before serialization, so sidecar-produced requests contain `container_id`, `name`, `repo_name`, `repo_branch`, `file_path`, and `question`; explicit gate payload keys would win on a key collision, though the current blocked wrapper supplies only `file_path` and `question`.
- producer endpoint: the sidecar posts the serialized JSON object to `http://{GROOM_HOST}:{GROOM_PORT}/push/blocked`, where `GROOM_HOST` defaults to `host.docker.internal` and `GROOM_PORT` defaults to `8787`.
- producer transport: the sidecar serializes the merged object as UTF-8 JSON, declares `Content-Type: application/json`, performs exactly one HTTP `POST` attempt, closes the response object when a response is opened, ignores the response body, and performs no command-line output for this notice path.
- producer timeout: the sidecar uses `GROOM_PUSH_TIMEOUT` seconds for the HTTP call, defaulting to `1.0`; connection failures, HTTP-open failures, response-close failures, and unexpected exceptions are ignored so the notification cannot block or alter workflow execution.
- consumer: the blocked-push endpoint accepts a parsed JSON object and ignores fields other than `container_id`, `file_path`, `question`, `name`, `repo_name`, and `repo_branch`.
- object rule: no nested object, list, or envelope is required; unknown members have no workflow, gate, notification, response, log, or persistence effect.
- id normalization: `container_id` is read with default `""`, converted to text, and truncated to 12 characters before any Docker metadata lookup or workflow mutation.
- gate-key normalization: `file_path` is read with default `""`, converted to text, and used exactly as the key in the workflow's open-gates map; no path canonicalization, trimming, workspace-prefix check, filesystem lookup, or traversal rejection occurs at this format boundary.
- question normalization: `question` is read with default `""`, converted to text, and stored in full on the gate record; only the browser notification message truncates it.
- null rule: explicit JSON `null` for `container_id`, `file_path`, or `question` is converted to the text `"None"`; explicit JSON `null` for `name`, `repo_name`, or `repo_branch` means do not update that optional identity field.
- success guard: an empty normalized `container_id` or empty normalized `file_path` is invalid and yields `ok: false` with no Docker metadata lookup, workflow update, gate record, dashboard broadcast, browser notification, or retry.
- overwrite rule: optional identity fields update the workflow only when their value is not `null`; omitted or `null` values preserve the existing in-memory field, while an empty string is still a non-null update for existing records.
- initial-name rule: when a valid payload creates a new workflow, a truthy `name` becomes the initial workflow name; an omitted, `null`, or falsey `name` falls back to the normalized container id.
- metadata rule: before applying the blocked update, the endpoint tries [push-first volume metadata resolver](concepts/push-first-volume-metadata-resolver.md) hydration for workflows that are absent or do not yet have a workspace volume; this can fill `workspace_volume`, `runs_volume`, and `workflow_type` independently of the JSON payload.
- gate replacement: a valid payload inserts or replaces the one gate keyed by normalized `file_path` and preserves any other open gates on the same workflow.
- state result: a valid payload marks the workflow as `blocked`, stores one gate for `file_path`, preserves current node, exit code, run id, workflow type, workspace volume, and runs volume unless Docker metadata resolution fills the volume/type fields first, then broadcasts the refreshed shell plus a blocked notification script.
- response result: the endpoint response is an object with `ok: false` on the success-guard failure path and `ok: true` after registry mutation and broadcast complete.
- non-effects: this payload does not answer a gate file, clear other gates, append a log event, prune workflow registry entries, authenticate a caller, read file contents, update current node, mark a workflow finished, retry delivery, or persist data outside the groom process.

## Fields

### field-container-id

- type: string-convertible JSON value
- default: `""`
- required: true
- producer: sidecar identity uses the first 12 characters of the sidecar process hostname.
- consumer: the handler converts it with `str(value)[:12]`, rejects the request when the result is empty, and uses the normalized value as the workflow registry key and stored gate workflow id.
- meaning: workflow container id that associates the gate with one in-memory workflow container.
- constraints: values longer than 12 characters collide by their first 12 characters; an explicit `null` becomes `"None"` and is treated as present.

### field-file-path

- type: string-convertible JSON value
- default: `""`
- required: true
- producer: sidecar gate-event handling supplies the workspace-relative [operator gate context file](operator-gate-context-file.md) path; compatible clients may supply any string-convertible path token.
- consumer: the handler converts it with `str(value)`, rejects the request when the result is empty, and uses the normalized value as both the open-gates map key and the stored gate file path.
- meaning: [operator gate context file](operator-gate-context-file.md) path that identifies the operator prompt and scopes the later answer command.
- constraints: the value is not normalized, sorted, validated against the workspace, or checked for existence by the payload consumer; a later payload with the same normalized key replaces the previous gate record for that key.

### field-question

- type: string-convertible JSON value
- default: `""`
- required: false
- producer: sidecar gate-event handling supplies the extracted operator question text from the awaiting [operator gate context file](operator-gate-context-file.md).
- consumer: the handler converts it with `str(value)`, stores the full normalized text on the gate record, and truncates only the browser notification message to the first 200 characters.
- meaning: operator-facing gate question shown in the inbox preview, worker detail, and notification preview.
- constraints: omitted means an empty stored question; an explicit `null` becomes `"None"`; HTML rendering escapes the stored text later.

### field-name

- type: JSON string expected; any non-null JSON value is accepted by assignment
- default: omitted
- required: false
- producer: sidecar identity uses the `REPO_NAME` environment variable when present, including when it is an empty string; only an absent `REPO_NAME` falls back to the sidecar process hostname.
- consumer: when present and non-null, the value is passed to workflow upsert as `name`; omitted or `null` preserves the existing name, and a newly created workflow without a non-empty name defaults to the normalized container id.
- meaning: human-facing workflow/container label used in dashboard rows, notification messages, and repository picker labels.
- constraints: the handler does not convert this field to text; downstream dashboard rendering and searching expect a string-like value.

### field-repo-name

- type: JSON string expected; any non-null JSON value is accepted by assignment
- default: omitted
- required: false
- producer: sidecar identity uses `REPO_NAME` when set, otherwise `""`.
- consumer: when present and non-null, replaces the workflow's current `repo_name`; omitted or `null` preserves the existing repository name.
- meaning: repository name shown in dashboard identity text.
- constraints: empty string clears or leaves the repository-name display blank for an existing workflow; downstream dashboard rendering and searching expect a string-like value.

### field-repo-branch

- type: JSON string expected; any non-null JSON value is accepted by assignment
- default: omitted
- required: false
- producer: sidecar identity uses `REPO_BRANCH` when set, otherwise `""`.
- consumer: when present and non-null, replaces the workflow's current `repo_branch`; omitted or `null` preserves the existing repository branch.
- meaning: repository branch shown with the repository name.
- constraints: empty string suppresses the branch suffix in dashboard identity text; downstream dashboard rendering and searching expect a string-like value.

### field-ignored-fields

- type: any JSON value
- default: omitted
- required: false
- meaning: all keys outside `container_id`, `file_path`, `question`, `name`, `repo_name`, and `repo_branch` are ignored by the current consumer and are not copied into the workflow container or gate record.
- producer: first-party residual HTTP blocked pushes do not add ignored fields; compatible clients may include them without changing current handler behavior.
- consumer: the endpoint never passes ignored keys to the workflow registry, gate record constructor, Docker metadata resolver, shell renderer, notification renderer, dashboard broadcaster, or response object.
- constraints: ignored keys do not make the request invalid, do not affect the response body, do not alter existing gates, and do not create forward-compatibility guarantees for future consumers.
