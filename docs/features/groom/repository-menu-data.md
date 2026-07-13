---
type: format
slug: repository-menu-data
title: Repository menu data
---
# Repository menu data

Repository menu data is the in-memory handoff from the [serve repository menu](http/groom.md#serve-repository-menu) invocation to the [repository menu option](gui/screens/groom-dashboard.md#repository-menu-option) renderer. It pairs each eligible [workflow container](concepts/workflow-container.md) with the volume-relative checkout directories returned by the [workspace volume repository-directory reader](concepts/workspace-volume-repository-directory-reader.md), and the resulting HTML lets the dashboard choose which container/repository pair to use for files and diff requests.

- file: not an on-disk artifact; this is an in-memory HTTP handler and renderer contract.
- code: groom/groom/app.py::repos
- verify: groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo
- verify: groom/tests/test_render.py::test_repo_menu_one_entry_per_container_repo
- verify: groom/tests/test_render.py::test_repo_menu_empty_when_no_entries

## Contract

- producer: [serve repository menu](http/groom.md#serve-repository-menu) creates the entry list by filtering the process-local workflow registry and resolving checkout directories for each eligible workflow.
- source snapshot: the endpoint reads the current workflow registry once for the request; later registry changes do not mutate the already-built menu data.
- consumer: [repository menu option](gui/screens/groom-dashboard.md#repository-menu-option) rendering consumes the entries and turns each workflow/repository pair into an HTML option row; [filter repository menu options](gui/screens/groom-dashboard.md#filter-repository-menu-options) then consumes each rendered row's `data-label` value as the browser-local search string.
- eligibility: a workflow contributes one tuple only when its `workspace_volume` field is non-empty.
- checkout discovery: each eligible workflow's checkout list is resolved independently from its workspace volume; no eligible workflows skip checkout discovery entirely.
- error behavior: a non-zero checkout-discovery process for one workflow is represented as that workflow's empty checkout list and does not remove other workflows' entries; process-launch and timeout exceptions are not converted by this contract and may fail the `/repos` request at the framework level.
- empty-checkout behavior: a workflow with no discovered checkout directories still contributes one rendered option with an empty repository path so the dashboard can browse the workspace volume root.
- empty-menu behavior: no eligible workflows produces the non-interactive `No repositories available.` fragment rather than an option row.
- ordering: workflow tuple order is not the visible order contract; the renderer sorts workflows by dashboard state order (`blocked`, `running`, `idle`, `finished`) and workflow name, while checkout directories keep the sorted order returned for that workflow.
- escaping: every dynamic workflow id, repository path, option label, workflow state value, and workflow type value is HTML-escaped before it enters the rendered option attributes or text nodes.
- side effects: building this data never mutates workflow state, writes workspace files, contacts sidecar sockets, broadcasts websocket updates, reads file contents, or computes diffs.

## Fields

### field-entries

- type: `list[tuple[WorkflowContainer, list[str]]]`
- default: none
- required: true
- meaning: complete repository-menu input; each tuple contains one eligible workflow and the checkout directories resolved for that workflow.
- cardinality: zero or more tuples; at most one tuple per eligible workflow in the registry snapshot.
- ordering: input tuple order is accepted but not exposed directly because the renderer applies the visible workflow sort before emitting options.

### field-entry

- type: `tuple[WorkflowContainer, list[str]]`
- default: none
- required: true for each item in `entries`
- meaning: one eligible workflow together with all checkout directories discovered for that workflow's workspace volume.
- constraint: the tuple's workflow is the same workflow whose `workspace_volume` was passed to checkout discovery.
- expansion: renders as one option per checkout directory when `repo_dirs` is non-empty, otherwise renders as one volume-root option for the workflow.

### field-workflow

- type: `[Workflow container](concepts/workflow-container.md)`
- default: none
- required: true
- meaning: the workflow identity, state, type badge, label, and container id used to produce one or more repository menu options.
- constraint: `workspace_volume` is non-empty when this record is produced by the HTTP handler.
- visible state: `state` selects the sort bucket and state dot; `workflow_type` may add a type badge; `name` forms the label prefix; `container_id` becomes the `data-container` selection value.

### field-repo-dirs

- type: `list[str]`
- default: empty list
- required: true
- meaning: volume-relative checkout directories under the workflow workspace volume; each value becomes a `data-repo` value and the suffix of the visible option label.
- empty-state: an empty list means no checkout was found or checkout discovery returned empty after a non-zero Docker process for that workflow; the renderer treats this as one volume-root option with `data-repo=""`.
- constraint: each non-empty value is the parent directory of a `.git` directory discovered one or two levels below the volume root.
- ordering: values are already sorted by checkout discovery and are emitted in that order within the workflow's visible group.

### field-repo-dir

- type: `str`
- default: none
- required: true for each item in `repo_dirs`
- meaning: volume-relative repository checkout path selected by the dashboard for subsequent files and diff requests.
- constraint: does not include the leading volume mount prefix and does not include the trailing `/.git` segment.
- empty-value: an empty value is not a discovered checkout; it is the renderer's synthetic volume-root option when `repo_dirs` is empty.

### field-option-label

- type: `str`
- default: derived from workflow name and repository path
- required: true
- meaning: visible option name and `data-label` value; formed as `workflow.name/repo` when `repo` is non-empty and as `workflow.name` for the volume-root option; the dashboard repository-menu search matches this value case-insensitively.
- escaping: HTML-escaped before insertion into the `data-label` attribute and visible `.repo-item-label` text node.

### field-option-container

- type: `str`
- default: derived from `workflow.container_id`
- required: true
- meaning: `data-container` value placed on the rendered option row so selecting the option targets the chosen workflow container.
- escaping: HTML-escaped before insertion into the `data-container` attribute.

### field-option-repo

- type: `str`
- default: derived from one `repo_dir` item or `""` for the synthetic volume-root option
- required: true
- meaning: `data-repo` value placed on the rendered option row so selecting the option targets the chosen checkout directory for files and diff requests.
- escaping: HTML-escaped before insertion into the `data-repo` attribute.

### field-option-state-dot

- type: `HTML fragment`
- default: derived from `workflow.state`
- required: true
- meaning: visual workflow lifecycle marker rendered before the repository option label.
- source: [workflow state](concepts/workflow-state.md) from the tuple's workflow container.
- shape: `<span class="dot {state}"></span>` where `{state}` is the workflow state value.
- escaping: the state value is HTML-escaped before insertion into the class attribute.

### field-option-type-badge

- type: `HTML fragment | ""`
- default: `""` when `workflow.workflow_type` is empty
- required: false
- meaning: optional workflow-kind chip rendered between the state dot and option label.
- source: `workflow.workflow_type` from the tuple's workflow container.
- shape: when present, `<span class="badge" data-type="{workflow_type}" style="--type-hue:{hue}">{workflow_type}</span>` where hue is derived deterministically by the [workflow type badge renderer](concepts/workflow-type-badge-renderer.md).
- escaping: workflow type is HTML-escaped before insertion into the `data-type` attribute and text node.
