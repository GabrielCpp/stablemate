---
type: format
slug: repository-menu-data
title: Repository menu data
---
# Repository menu data

Repository menu data is the JSON body of the [serve repository menu](http/groom.md#serve-repository-menu) invocation: one group per workflow container, each carrying the checkouts found on that container's workspace. It is what the [groom dashboard](gui/screens/groom-dashboard.md) picker turns into selectable rows, and the container/repository pair the operator picks is what every later files and diff request is scoped to.

It arrives **grouped, not flat**, because grouped is the shape the server actually has — one checkout enumeration per container — and because a row's label is derived from both halves of the pair. Flattening on the server would throw away the grouping and then oblige the client to reconstruct it to render group order. The client flattens instead, in one function, at render time.

Nothing in this format is markup. Every value is a string or an integer, and the picker's state dot, type badge, and label are Preact components fed from those values. That is the difference from the fragment era, when this endpoint returned rendered option rows and the escaping of an operator-supplied repository path was the renderer's responsibility.

- file: not an on-disk artifact; this is a transient JSON HTTP response body.
- code: groom/groom/app.py::repos
- code: groom/groom/projection.py::repo_entries
- code: groom/groom/assets/dashboard.js::repoItems
- code: groom/groom/assets/dashboard.js::RepoMenu
- refs: [groom projection module](concepts/groom-projection-module.md), [workspace volume repository-directory reader](concepts/workspace-volume-repository-directory-reader.md), [workflow container](concepts/workflow-container.md)
- verify: groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo
- verify: groom/tests/test_app.py::test_repos_endpoint_reads_native_run_from_local_disk
- verify: groom/tests/test_projection.py::test_repo_entries_group_checkouts_under_their_container
- verify: groom/tests/test_projection.py::test_repo_entries_empty_when_nothing_is_running

## Contract

- producer: [serve repository menu](http/groom.md#serve-repository-menu) filters the process-local workflow registry to workflows with a known workspace, enumerates each one's checkouts concurrently, and hands the resulting pairs to the projection.
- media: `application/json`. A list of group objects — the top level is a list, not an object, because there is nothing fleet-wide to say alongside it.
- source snapshot: the endpoint reads the workflow registry once for the request; later registry changes do not mutate an already-returned menu. The picker is re-fetched every time it opens, which is how it stays current without a subscription.
- pull only: this shape is never pushed. It costs one checkout enumeration per container, so sending it on every fleet tick would spend that on every tab whether or not the picker was open.
- eligibility: a workflow contributes a group only when its `workspace_volume` field is non-empty. A workflow whose workspace is unknown has nothing browsable, so it is absent rather than present-and-empty.
- reader selection: a native workflow's checkouts are enumerated straight from local disk; every other workflow's are enumerated through a throwaway read-only Docker container. Both return the same list of volume-relative directories, which is why the group shape does not record which ran.
- checkout discovery: each eligible workflow's checkout list is resolved independently and concurrently; no eligible workflow skips discovery.
- error behavior: a non-zero checkout-discovery process for one workflow becomes that workflow's empty checkout list and does not remove other workflows' groups; process-launch and timeout exceptions are not converted by this contract and can fail the `/repos` request at the framework level.
- empty-checkout behavior: a workflow with no discovered checkout still contributes one entry with `repo: ""`, so its workspace root can be browsed at all.
- empty-menu behavior: no eligible workflows serializes as `[]`. The picker renders the non-interactive `No repositories available.` state from that, and a still-in-flight fetch renders `Loading…` — two distinct states, so an empty fleet never reads as a slow one.
- ordering: groups arrive in the fleet's own order — blocked first, then by workflow name — and each group's entries keep the sorted order checkout discovery returned. The client does not re-sort.
- filtering: the picker's search box filters entries client-side by case-insensitive substring over `label`. The server does not receive the query, because the menu is already in the tab.
- no escaping: values are JSON data set as text or as attribute values by Preact. There is no HTML-escaping step anywhere on this path, because nothing here becomes markup.
- side effects: building this data never mutates workflow state, writes workspace files, contacts sidecar sockets, broadcasts websocket updates, reads file contents, or computes diffs.

## Fields

### field-groups

- type: `list` of group objects
- default: `[]`
- required: true
- wire-location: the whole HTTP response body.
- meaning: one entry per eligible workflow container, already ordered for display.
- cardinality: zero or more; at most one group per eligible workflow in the registry snapshot.

### field-group-container

- type: `str`
- default: none
- required: true
- wire-key: `container`
- meaning: the workflow's container id. It is the selection value every later `/files`, `/file`, and `/diff` request is addressed to, and half of the picker row's key.

### field-group-name

- type: `str`
- default: none
- required: true
- wire-key: `name`
- meaning: the workflow's name, which for a groom run is its `<workflow>-<runid>` label. There is exactly one workflow per container, so the container name *is* the workflow name and the group needs no second identity.

### field-group-state

- type: `str` — one of `blocked`, `running`, `idle`, `finished`
- default: none
- required: true
- wire-key: `state`
- source: [workflow state](concepts/workflow-state.md).
- meaning: the lifecycle state the picker's state dot shows and the projection's group sort key. It travels as the enum's value, never the enum object.

### field-group-type

- type: `str`
- default: `""`
- required: true
- wire-key: `type`
- meaning: the workflow kind shown as a badge beside the row. An empty value means no badge.

### field-group-type-hue

- type: `int` — 0–359
- default: `0`
- required: true
- wire-key: `type_hue`
- code: groom/groom/projection.py::type_hue
- meaning: the badge's hue, derived deterministically from the type string so the same workflow kind is the same colour in the picker and in the fleet list without a shared palette table.

### field-group-repos

- type: `list` of entry objects
- default: `[{"repo": "", "label": <name>}]`
- required: true
- wire-key: `repos`
- meaning: the checkouts under this container's workspace, one entry each. Never empty — an empty discovery result becomes the single volume-root entry.
- ordering: the sorted order checkout discovery returned, preserved.

### field-entry-repo

- type: `str`
- default: `""`
- required: true
- wire-key: `repo`
- meaning: the volume-relative checkout directory, sent as the `repo` query parameter on subsequent files and diff requests. `""` selects the workspace root.
- constraint: does not include the volume mount prefix and does not include a trailing `/.git` segment.

### field-entry-label

- type: `str`
- default: none
- required: true
- wire-key: `label`
- meaning: the visible row text, `name/repo` when `repo` is non-empty and `name` alone for the volume-root entry. It is also the string the picker's client-side search matches against and the label the picker button shows after selection.
- derivation: composed server-side from both halves of the pair, so the client never has to know the joining rule.

## Methods

### method-repo-entries

- sig: `repo_entries(entries: list[tuple[WorkflowContainer, list[str]]]) -> list[dict[str, Any]]`
- abstract: false
- raises: none intentionally; a workflow state outside the known set would fail the sort's state lookup.
- code: groom/groom/projection.py::repo_entries
- verify: groom/tests/test_projection.py::test_repo_entries_group_checkouts_under_their_container
- verify: groom/tests/test_projection.py::test_repo_entries_empty_when_nothing_is_running
- input: pairs of workflow container and its discovered volume-relative checkout directories, in any order.
- output: the group list described above, sorted and label-composed.
- effects: pure. It reads only its argument, and mutates no workflow, registry, socket, or module state.
- empty-checkout rule: an empty or falsey checkout list is replaced by `[""]` before entries are built, which is what guarantees every group has at least one selectable row.
- algorithm:
  1. Sort the pairs by dashboard state order, then workflow name.
  2. For each pair, emit the container id, name, state value, type, and type hue.
  3. Replace an empty checkout list with a single empty-string checkout.
  4. Emit one entry per checkout, composing `name/repo` as the label, or `name` alone when the checkout is the volume root.

### method-repos

- sig: `async repos() -> list[dict]`
- abstract: false
- raises: no endpoint-specific exception for an empty fleet or a workflow with no discoverable checkout; discovery process-launch and timeout exceptions can propagate.
- code: groom/groom/app.py::repos
- verify: groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo
- verify: groom/tests/test_app.py::test_repos_endpoint_reads_native_run_from_local_disk
- input: none; the handler reads the process-local workflow registry.
- output: [field-groups](#field-groups), serialized as the JSON response body.
- effects: reads workflow registry state and launches one read-only checkout enumeration per eligible workflow, on worker threads; it mutates nothing.
- concurrency: enumerations run concurrently rather than in sequence, because each is an independent throwaway process and a serial fleet-sized loop would make opening the picker feel like a page load.
- calls: the local-filesystem or Docker-volume [workspace volume repository-directory reader](concepts/workspace-volume-repository-directory-reader.md) per workflow, then [method-repo-entries](#method-repo-entries).
- algorithm:
  1. Take the fleet snapshot and keep only workflows with a non-empty workspace volume.
  2. For each, pick the native or Docker checkout lister by the workflow's native flag and run it on a worker thread.
  3. Await all enumerations together.
  4. Project the resulting pairs into groups and return them.
