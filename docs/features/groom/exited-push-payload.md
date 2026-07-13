---
type: format
slug: exited-push-payload
title: Exited push payload
---
# Exited push payload

Exited push payload is the JSON request body produced by the residual HTTP sidecar exit notice in [`groom-sidecar --exit-code`](groom-sidecar.md#groom-sidecar-root) and consumed by the [receive exited push](http/groom.md#receive-exited-push) invocation on the [groom server](http/groom.md). It is built through the [sidecar residual HTTP push helper](concepts/sidecar-residual-http-push-helper.md) by merging [sidecar identity data](sidecar-identity-data.md) with an `exit_code` member, and is the terminal counterpart to [progress push payload](progress-push-payload.md) and [blocked push payload](blocked-push-payload.md): a valid payload marks one [workflow container](concepts/workflow-container.md) in the [workflow registry](concepts/workflow-registry.md) finished through the [exited-push workflow-state transition](concepts/workflow-state.md#transition-exited-push), records a numeric exit code when available, and clears any open [gate info](concepts/gate-info.md) entries because an exited container cannot act on answers.

- file: not an on-disk artifact; this is a best-effort HTTP JSON request body for `POST /push/exited`.
- code: groom/groom/app.py::push_exited
- code: groom/groom/sidecar.py::push_exited
- verify: groom/tests/test_sidecar.py::test_push_exited_posts_expected_shape
- verify: groom/tests/test_sidecar.py::test_push_exited_is_silent_when_groom_is_unreachable
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code
- verify: groom/tests/test_app.py::test_push_exited_rejects_missing_container_id

## Contract

- shape: a JSON object; arrays, strings, numbers, booleans, and `null` are not valid semantic payloads for this endpoint because the consumer expects object-style key lookup. No envelope, nested object, ordered field layout, route parameter, query parameter, cookie, authentication token, or required request header participates in this payload contract beyond the JSON body being parsed for object-style key lookup.
- producer: `groom-sidecar --exit-code EXIT_CODE` sends this shape once from the workflow container entrypoint after the workflow process returns, by calling the sidecar exit-push helper with the parsed integer exit code.
- producer identity: first-party sidecar requests merge [sidecar identity data](sidecar-identity-data.md) fields `container_id`, `name`, `repo_name`, and `repo_branch` into the explicit `exit_code` payload before serialization; explicit payload keys would override same-named identity keys, but the current exit producer supplies only `exit_code`.
- producer endpoint: the sidecar posts the serialized JSON object to `http://{GROOM_HOST}:{GROOM_PORT}/push/exited`, where `GROOM_HOST` defaults to `host.docker.internal` and `GROOM_PORT` defaults to `8787`.
- producer transport: the sidecar serializes the merged object as UTF-8 JSON, declares `Content-Type: application/json`, performs exactly one HTTP `POST` attempt, closes the response object when a response is opened, ignores the response body, and performs no command-line output for this notice path.
- producer timeout: the sidecar uses `GROOM_PUSH_TIMEOUT` seconds for the HTTP call, defaulting to `1.0`; connection failures, HTTP-open failures, response-close failures, and unexpected exceptions are ignored so the notification cannot block or alter workflow exit handling.
- consumer: the exited-push endpoint accepts a parsed JSON object and ignores fields other than `container_id`, `exit_code`, `name`, `repo_name`, and `repo_branch`.
- id normalization: `container_id` is read with missing default `""`, converted to text, and truncated to 12 characters before any Docker metadata lookup, workflow mutation, gate clearing, or broadcast.
- success guard: an empty normalized `container_id` is invalid and yields `ok: false` with no workflow update, Docker metadata lookup, gate clearing, or dashboard broadcast; explicit JSON `null` normalizes to the text `"None"` and is therefore accepted by this boundary.
- exit-code parsing: JSON integers and strings whose string form is decimal digits with zero or one leading `-` are stored as integers; booleans, floats, strings with whitespace or a `+` sign, empty strings, `null`, arrays, objects, and other non-numeric values are treated as absent. Strings with more than one leading `-` are malformed for this boundary: they pass the pre-conversion digit check but fail integer conversion, so the request fails through the framework error path rather than producing `ok: false` or preserving the prior exit code.
- overwrite rule: optional identity fields and the parsed exit code update the workflow only when their value is not `null`; omitted, `null`, and non-numeric exit-code values preserve the existing in-memory field on existing workflows.
- initial-name rule: when a valid payload creates a new workflow, a truthy `name` becomes the initial workflow name; an omitted, `null`, or falsey `name` falls back to the normalized container id.
- metadata rule: before applying the finish update, the endpoint tries [push-first volume metadata resolver](concepts/push-first-volume-metadata-resolver.md) hydration for workflows that are absent or do not yet have a workspace volume; this can fill `workspace_volume`, `runs_volume`, and `workflow_type` independently of the JSON payload.
- state result: a valid payload marks the workflow [workflow state](concepts/workflow-state.md) as `finished`, clears all open gates for that workflow, stores a parsed exit code when one was accepted, preserves the previous exit code when the payload omits `exit_code` or supplies an ordinary non-numeric value, preserves current node and run id, preserves workflow type, workspace volume, and runs volume unless Docker metadata resolution fills them first, then broadcasts the refreshed dashboard shell.
- response result: normal handler return is a JSON object `{"ok": bool}`; `false` means the normalized container id was empty, and `true` means metadata resolution, workflow upsert, gate clearing, and dashboard broadcast completed. The response does not echo the exit code, workflow id, cleared gates, workflow state, or rendered shell fragment.
- error result: malformed JSON, non-object request bodies rejected before handler object lookup, Docker metadata lookup failures, malformed multi-hyphen numeric strings that fail integer conversion, shell rendering failures, and dashboard broadcast failures do not use this format's `ok: false` response; they propagate through the framework error path.
- non-effects: this payload does not answer a gate file, write a gate file, append a log event, prune workflow registry entries, authenticate a caller, read file contents, update current node, send a browser notification script, retry delivery, or persist data outside the groom process.

## Fields

### field-container-id

- type: string-convertible JSON value
- default: `""`
- required: true
- producer: first-party sidecar requests set this from the first 12 characters of the sidecar process hostname through [sidecar identity data](sidecar-identity-data.md).
- consumer: the handler converts it with `str(value)[:12]`, rejects the request when the result is empty, and uses the normalized value as the workflow registry key.
- meaning: workflow container id whose in-memory workflow should be marked finished.
- constraints: values longer than 12 characters collide by their first 12 characters; an absent key uses the missing default and is rejected, while explicit JSON `null` becomes `"None"` and is treated as present.

### field-exit-code

- type: integer JSON value or string containing zero or one leading `-` plus decimal digits
- default: omitted
- required: false
- producer: first-party sidecar requests set this from the integer parsed from `groom-sidecar --exit-code EXIT_CODE`.
- consumer: the handler converts accepted numeric values to `int` and passes that value into the workflow update; values that fail the numeric test are passed as `null` into the update and are skipped by the registry upsert.
- meaning: workflow process exit code shown on finished-worker detail when known.
- constraints: accepted string values must contain decimal digits after an optional single leading `-`; strings with whitespace, a leading `+`, a decimal point, or no digits are treated as absent. A string with two or more leading `-` characters is malformed for this boundary and fails during integer conversion rather than being treated as absent.

### field-name

- type: JSON string expected; any non-null JSON value is accepted by assignment
- default: omitted
- required: false
- producer: first-party sidecar requests set this from `REPO_NAME` when that environment variable is present, otherwise from the sidecar process hostname.
- consumer: when present and non-null on an existing workflow, the value replaces the workflow's current `name`; when a valid payload creates a new workflow, a truthy value becomes the initial name.
- meaning: human-facing workflow/container label used in dashboard rows, worker detail headings, and repository picker labels.
- constraints: omitted or `null` preserves an existing workflow name; omitted, `null`, or a falsey value creates a new workflow with the normalized container id as its name. The handler does not convert this field to text before assignment.

### field-repo-name

- type: JSON string expected; any non-null JSON value is accepted by assignment
- default: omitted
- required: false
- producer: first-party sidecar requests set this from `REPO_NAME`, defaulting to an empty string when the environment variable is absent.
- consumer: when present and non-null, the value replaces the workflow's current `repo_name`.
- meaning: repository name shown in dashboard identity text for the finished workflow.
- constraints: omitted or `null` preserves the existing repository name; an empty string is non-null and therefore can intentionally clear or leave blank the repository-name display field. The handler does not convert this field to text before assignment.

### field-repo-branch

- type: JSON string expected; any non-null JSON value is accepted by assignment
- default: omitted
- required: false
- producer: first-party sidecar requests set this from `REPO_BRANCH`, defaulting to an empty string when the environment variable is absent.
- consumer: when present and non-null, the value replaces the workflow's current `repo_branch`.
- meaning: repository branch shown with the repository name for the finished workflow.
- constraints: omitted or `null` preserves the existing repository branch; an empty string is non-null and therefore can intentionally clear or leave blank the repository-branch display field. The handler does not convert this field to text before assignment.

### field-ignored-fields

- type: any JSON value
- default: omitted
- required: false
- meaning: all keys outside `container_id`, `exit_code`, `name`, `repo_name`, and `repo_branch` are ignored by the current consumer and are not copied into the workflow container.
- producer: first-party residual HTTP exited pushes do not add ignored fields; compatible clients may include them without changing current handler behavior.
- consumer: the endpoint never passes ignored keys to the workflow registry, Docker metadata resolver, shell renderer, dashboard websocket broadcaster, or response object.
- constraints: ignored keys do not make the request invalid, do not affect the response body, do not alter gates, and do not create forward-compatibility guarantees for future consumers.
