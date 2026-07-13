---
type: format
slug: sidecar-identity-data
title: Sidecar identity data
---
# Sidecar identity data

Sidecar identity data is the sidecar-produced JSON object that identifies one
workflow container to [sidecar websocket frame](sidecar-websocket-frame.md)
`hello` messages and residual HTTP payloads sent through the [sidecar residual
HTTP push helper](concepts/sidecar-residual-http-push-helper.md). Its fields can
update the displayed identity of a [workflow container](concepts/workflow-container.md)
when consumed by hello, progress, blocked, or exited paths, while the event
payloads that merge it may add their own event-specific fields.

- file: not an on-disk artifact; this is an in-memory JSON object embedded in
  sidecar websocket and residual HTTP messages.
- code: groom/groom/sidecar.py::_identity
- verify: groom/tests/test_sidecar_session.py::test_hello_frame_carries_identity_and_snapshot
- verify: groom/tests/test_sidecar.py::test_push_progress_posts_expected_shape

## Contract

- shape: JSON object with exactly the producer-owned keys `container_id`,
  `name`, `repo_name`, and `repo_branch` when produced by first-party sidecar
  code.
- member order: no semantic order; consumers address fields by JSON object key.
- producer: every call reads the current process hostname and the current
  `REPO_NAME` and `REPO_BRANCH` environment values at call time; it does not
  cache identity across calls.
- embedding: websocket hello frames place this object under `identity`; residual
  HTTP pushes merge this object into the top-level request body before adding the
  event-specific payload fields.
- collision rule: residual HTTP event payload keys override same-named identity
  keys because the event payload is merged after this object; first-party event
  producers do not currently send colliding keys.
- consumer boundary: first-party production always emits string values, but groom
  server consumers still treat external JSON values defensively at their own
  boundaries because compatible or direct clients can send non-string values.
- non-effects: building this object does not read Docker metadata, inspect git
  state, read workspace or run files, register sidecar sockets, mutate workflow
  state, perform network I/O, or validate that the advertised repository fields
  match the mounted workspace.

## Fields

### field-container-id

- type: `str`
- default: first 12 characters of the process hostname.
- required: true
- wire-key: `container_id`
- meaning: workflow container id advertised by the sidecar; host-side consumers
  use it as the workflow registry key after their own normalization/empty-id
  checks.
- source: `socket.gethostname()[:12]`.
- constraints: if the hostname is shorter than 12 characters, the whole hostname
  is used; an empty hostname would produce an empty id and make host-side push or
  hello consumers reject the update as not useful.

### field-name

- type: `str`
- default: process hostname only when `REPO_NAME` is absent from the process
  environment.
- required: true
- wire-key: `name`
- meaning: human-facing workflow/container display label offered to host-side
  workflow upsert paths.
- source: `REPO_NAME` environment value when the variable is present; otherwise
  `socket.gethostname()`.
- constraints: an explicitly empty `REPO_NAME` produces an empty name string;
  host-side creation paths that treat falsey names as absent may still fall back
  to the normalized container id when creating a workflow.

### field-repo-name

- type: `str`
- default: empty string when `REPO_NAME` is absent.
- required: true
- wire-key: `repo_name`
- meaning: repository name displayed alongside the workflow when host-side
  consumers accept the non-null identity value.
- source: `REPO_NAME` environment value, defaulting only for absence.
- constraints: an explicitly empty `REPO_NAME` produces an empty string, which is
  still a non-null value for consumers that assign repository-name fields.

### field-repo-branch

- type: `str`
- default: empty string when `REPO_BRANCH` is absent.
- required: true
- wire-key: `repo_branch`
- meaning: repository branch displayed alongside `repo_name` when host-side
  consumers accept the non-null identity value.
- source: `REPO_BRANCH` environment value, defaulting only for absence.
- constraints: an explicitly empty `REPO_BRANCH` produces an empty string, which
  is still a non-null value for consumers that assign repository-branch fields.

## Algorithm

1. Read the process hostname for use as both the container-id source and the name
   fallback.
2. Return a new dictionary whose `container_id` is the hostname truncated to 12
   characters.
3. Set `name` to the current `REPO_NAME` value when that environment variable
   is present, including an empty string; otherwise set it to the full hostname.
4. Set `repo_name` to the current `REPO_NAME` value when present, otherwise the
   empty string.
5. Set `repo_branch` to the current `REPO_BRANCH` value when present, otherwise
   the empty string.

## Deeper Calls

- Calls only standard-library process, socket, and environment readers; there are
  no first-party deeper layers to document below this item.
