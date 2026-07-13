---
type: concept
slug: operator-inbox
title: Operator inbox
status: implemented
id: stablemate-2
area: groom
---
# Operator inbox

The operator inbox is groom's incoming-message set: it contains [workflow containers](concepts/workflow-container.md) that currently hold at least one open [gate info](concepts/gate-info.md) record, renders those containers as [inbox worker rows](gui/screens/groom-dashboard.md#inbox-worker-row) with a [workflow state dot](concepts/workflow-state-dot-renderer.md), optional [workflow type badge](concepts/workflow-type-badge-renderer.md), optional [inbox question preview](concepts/inbox-question-preview.md), and an empty-or-loading state selected from the [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md), [loading fragment renderer](#method-render-loading), and [HTML escape helper](concepts/html-escape-helper.md), and is narrowed by the [filter inbox messages](gui/screens/groom-dashboard.md#filter-inbox-messages) interaction through the [search fragment endpoint](http/groom.md#get-search-fragment). The full fleet remains in the [worker tree](worker-tree.md); the inbox is only the "needs you now" subset.

- code: groom/groom/render.py::render_inbox
- verify: groom/tests/test_render.py::test_inbox_shows_only_workers_with_open_gates
- verify: groom/tests/test_render.py::test_inbox_orders_gated_workers_by_state_then_name
- verify: groom/tests/test_render.py::test_empty_inbox_message
- verify: groom/tests/test_render.py::test_empty_inbox_shows_spinner_while_scanning
- verify: groom/tests/test_render.py::test_empty_inbox_shows_empty_state_when_not_scanning
- verify: groom/tests/test_render.py::test_search_with_query_shows_empty_not_spinner_even_while_scanning

## Contract

- purpose: present only operator-actionable gate messages; a plain running, idle, or finished worker without gates is not an inbox message.
- source: the caller supplies a snapshot list of workflow containers, commonly from the in-memory [workflow registry](concepts/workflow-registry.md) through an endpoint or websocket broadcast layer.
- eligibility: a workflow is included exactly when its `gates` mapping is non-empty and it satisfies the current query.
- state eligibility: gate presence is the inclusion rule; a `running`, `idle`, or `finished` workflow with a non-empty gate map still renders in the inbox, and a `blocked` workflow without gates does not.
- query default: empty string, meaning no text narrowing beyond the gate-presence requirement.
- query matching: non-empty queries are case-insensitive substrings over workflow name, repository name, repository branch, workflow type, current node, and every open gate file path.
- query normalization: inbox rendering lowercases the query for comparison but does not trim, tokenize, split, glob, regex-match, or normalize whitespace before matching.
- query exclusions: workflow container ids, gate question text, gate status text, answer text, exit-code hints, and rendered markdown are not search haystacks.
- order: included workers are sorted by [workflow state](concepts/workflow-state.md) priority `blocked`, then `running`, then `idle`, then `finished`; ties sort by workflow name ascending.
- repository label: row, detail-head, and status-count renderers use [method-render-repository-label](#method-render-repository-label) to derive the displayed or counted repository identity from the workflow container's repository name and branch.
- row source gate: each rendered row chooses the first open gate after sorting gates by file path; that gate supplies the displayed gate path and, for blocked workers, the question preview.
- row state marker: each rendered row includes one [workflow state dot](concepts/workflow-state-dot-renderer.md) before the optional [workflow type badge](concepts/workflow-type-badge-renderer.md); the marker's state class is derived from the same workflow state value exposed in the row's `data-state` attribute.
- exit hint fallback: when the row renderer is called for a workflow without an open gate, a finished workflow with a known exit code displays `exited {code}` as the tail; exit code `0` is classified as ok, every other integer is classified as error, and live or code-less workflows fall back to current-node text instead.
- row selection handoff: each row exposes `data-worker-id` for the dashboard's inbox-row selection behavior; the inbox renderer itself does not mark a row selected, fetch worker detail, or attach a navigation target.
- empty message: no included rows render `No incoming messages — inbox zero.`.
- loading message: no included rows render the [loading fragment renderer](#method-render-loading)'s `Discovering containers…` placeholder only when the [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md) is true and the query is empty.
- filtered-empty rule: a non-empty query that matches no gated workers renders the normal empty message even while discovery is scanning.
- broadcast role: websocket shell updates may replace the inbox list out of band, paired with the status bar; the search endpoint replaces only the inbox list and keeps fleet-wide status counts unchanged.
- fragment identity: every returned fragment has root id `inbox-list` and class `inbox-list`; the optional out-of-band flag only changes the root attribute and never changes filtering, ordering, row content, empty-state selection, or escaping.
- empty-text trust boundary: the normal empty-state helper preserves its supplied text without HTML escaping; first-party callers pass trusted static copy, while dynamic loading messages use the escaping [loading fragment renderer](#method-render-loading) instead.
- state mutation: rendering or filtering the inbox does not mutate workflow state, clear gates, answer gates, inspect Docker, contact sidecars, broadcast websocket updates, or write gate files.
- security: dynamic workflow and gate text is HTML-escaped before it enters the fragment; gate questions stay on the escaped text-node to client-side markdown sanitizer path and are never emitted as raw HTML.

## Fields

### field-workflows

- type: `list[WorkflowContainer]`
- default: none
- required: true
- meaning: current workflow snapshot to classify and render; each item may or may not contain open gate records.

### field-query

- type: `str`
- default: `""`
- required: false
- meaning: operator-entered inbox filter text from the dashboard searchbox or HTTP `q` query parameter.

### field-oob

- type: `bool`
- default: `False`
- required: false
- meaning: when true, marks the returned inbox-list root as an htmx out-of-band replacement fragment.

### field-root-fragment

- type: HTML fragment
- default: none
- required: true
- meaning: one `<div class="inbox-list" id="inbox-list">...</div>` root containing row components, the inbox empty state, or the discovery loading state.

### field-out-of-band-attribute

- type: HTML attribute
- default: absent
- required: false
- meaning: `hx-swap-oob="true"` appears on the root fragment exactly when the caller asks for an out-of-band replacement.

### field-row-fragments

- type: zero or more [inbox worker row](gui/screens/groom-dashboard.md#inbox-worker-row) fragments
- default: empty sequence
- required: false
- meaning: rendered rows for every eligible matching workflow, already sorted by inbox order.

### field-row-interaction-contract

- type: DOM data contract
- default: none
- required: true when row fragments are emitted
- meaning: each row is a `div.row` carrying `data-worker-id` and `data-state`; those attributes are the handoff to dashboard selection code, while role, accessible name, keyboard behavior, and navigation effects are owned by the [inbox worker row](gui/screens/groom-dashboard.md#inbox-worker-row) component and its interactions.

## Methods

### method-render-inbox

- sig: `render_inbox(workflows: list[WorkflowContainer], query: str = "", *, oob: bool = False) -> str`
- abstract: false
- raises: none intentionally raised for ordinary empty, unmatched, or partially populated workflow snapshots.
- code: groom/groom/render.py::render_inbox

Renders the inbox root fragment from a workflow snapshot. The method first keeps workflows whose gates mapping is non-empty and whose searchable fields match the query, then sorts the result by state priority and workflow name. A non-empty result is serialized as worker-row fragments; an empty result is serialized as the normal inbox-zero message or the discovery loading state according to the loading contract.

#### Effects

- Reads: the supplied workflow list, each workflow's open gate mapping, searchable workflow fields, [workflow state](concepts/workflow-state.md), workflow name, and the [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md) only when an empty result needs to choose between loading and inbox-zero text.
- Filters: drops every workflow whose gate mapping is empty before row rendering, regardless of worker state, current node, exit code, or query match.
- Filters: applies the current query through [method-match-inbox-query](#method-match-inbox-query), where an empty query accepts every gated workflow and a non-empty query is a case-insensitive substring match over the documented inbox haystacks.
- Orders: sorts the remaining workflows by dashboard state priority and then workflow name before any row HTML is produced.
- Emits: one root `<div class="inbox-list" id="inbox-list">` HTML fragment containing either ordered [inbox worker row](gui/screens/groom-dashboard.md#inbox-worker-row) fragments, the normal inbox-zero empty state, or the discovery loading state.
- Emits: `hx-swap-oob="true"` on that root only when `oob` is true.
- Calls: [method-render-inbox-row](#method-render-inbox-row) once per included workflow; calls [method-render-empty-or-loading](#method-render-empty-or-loading) only when no workflows remain after filtering; calls [method-render-out-of-band-swap-attribute](#method-render-out-of-band-swap-attribute) for every returned fragment.
- Does not mutate: workflow containers, gate records, workflow registry membership, scanning state, selected worker state, browser DOM state, Docker state, sidecar state, websocket queues, answer files, or gate files.

### method-render-out-of-band-swap-attribute

- sig: `_oob(oob: bool) -> str`
- abstract: false
- raises: none intentionally raised for either boolean input.
- code: groom/groom/render.py::_oob
- verify: groom/tests/test_render.py::test_dynamic_regions_have_stable_ids_and_oob_flag

Serializes the optional htmx out-of-band swap marker used by inbox and status-bar live-region roots. The method is a pure attribute-suffix formatter: it receives the caller's requested out-of-band mode and returns either the exact attribute text required by the [dashboard shell fragment](dashboard-shell-fragment.md) contract or an empty suffix for ordinary in-band markup.

#### Effects

- Reads: only the supplied `oob` boolean.
- Returns: a leading-space-prefixed ` hx-swap-oob="true"` attribute suffix when `oob` is true, so callers can concatenate it directly inside an opening tag after the stable element id.
- Returns: the empty string when `oob` is false, leaving the caller's opening tag without any out-of-band swap marker.
- Emits no dynamic text: the return value is selected from two fixed strings and does not use workflow, gate, query, repository, browser, websocket, or sidecar state.
- Calls: no other groom source symbols.
- Does not mutate: workflow containers, gate records, workflow registry membership, scanning state, selected worker state, browser DOM state, Docker state, sidecar state, websocket queues, answer files, or gate files.

### method-render-empty-or-loading

- sig: `_empty_or_loading(text: str, query: str) -> str`
- abstract: false
- raises: none intentionally raised for empty, non-empty, or unsafe display text, or for empty and non-empty query strings.
- code: groom/groom/render.py::_empty_or_loading
- verify: groom/tests/test_render.py::test_empty_inbox_shows_spinner_while_scanning
- verify: groom/tests/test_render.py::test_empty_inbox_shows_empty_state_when_not_scanning
- verify: groom/tests/test_render.py::test_search_with_query_shows_empty_not_spinner_even_while_scanning

Chooses the placeholder fragment for an empty inbox region. The method treats an empty query as the unfiltered fleet view, where a true [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md) means the visible absence of rows is provisional; any non-empty query is treated as an operator filter over the current fleet and therefore renders the normal empty-result message even while discovery is in flight.

#### Effects

- Reads: the supplied empty-state text and query string.
- Reads: the process-local [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md).
- Emits: a discovery-loading fragment when scanning is true and `query` is empty; that fragment comes from [method-render-loading](#method-render-loading) and therefore contains class `empty loading`, a spinner span with class `spin`, and the default text `Discovering containers…`.
- Emits: `<div class="empty">{text}</div>` when scanning is false or `query` is non-empty.
- Preserves: the supplied `text` value exactly when returning the normal empty-state fragment.
- Calls: [method-render-loading](#method-render-loading) only for the scanning-without-query branch.
- Trusts: the supplied `text` as static safe copy; it is concatenated into the empty-state text node without HTML escaping.
- Does not mutate: workflow containers, gate records, workflow registry membership, the scanning flag, selected worker state, browser DOM state, Docker state, sidecar state, websocket queues, answer files, or gate files.

### method-render-loading

- sig: `render_loading(message: str = "Discovering containers…") -> str`
- abstract: false
- raises: none intentionally raised for empty, unsafe, already-escaped, or non-ASCII display messages.
- code: groom/groom/render.py::render_loading
- verify: groom/tests/test_render.py::test_empty_inbox_shows_spinner_while_scanning

Serializes the provisional empty-region placeholder used while container discovery is still in flight. The method is display-only: it receives message text, escapes it through the shared [HTML escape helper](concepts/html-escape-helper.md#method-escape-html-value), and returns a complete non-interactive loading fragment for insertion inside an inbox or other empty live region.

#### Effects

- Reads: the supplied `message` text only; the default message is `Discovering containers…`.
- Escapes: the message through the [HTML escape helper](concepts/html-escape-helper.md#method-escape-html-value) before it is inserted as a text node.
- Emits: exactly one `<div class="empty loading">` root fragment.
- Emits: one child `<span class="spin"></span>` before the message text so the existing dashboard loading animation can be applied.
- Emits: the escaped message text immediately after the spinner span, without adding an accessible role, accessible name, button semantics, links, inputs, or keyboard handlers.
- Calls: [method-escape-html-value](concepts/html-escape-helper.md#method-escape-html-value); that helper is already documented and bottoms out at the Python standard library.
- Does not read: workflow containers, gate records, query text, the scanning flag, registry membership, selected worker state, Docker state, sidecar state, websocket queues, answer files, or gate files.
- Does not mutate: workflow containers, gate records, workflow registry membership, the scanning flag, selected worker state, browser DOM state, Docker state, sidecar state, websocket queues, answer files, or gate files.

### method-match-inbox-query

- sig: `_matches(wf: WorkflowContainer, query: str) -> bool`
- abstract: false
- raises: none intentionally raised for missing optional workflow text fields.
- code: groom/groom/render.py::_matches

Classifies one workflow against the current filter query. Empty query always matches; non-empty query lowercases the query and the searchable workflow fields, then accepts the workflow if any field contains the query substring.

#### Effects

- Reads: workflow name, repository name, repository branch, workflow type, current node, and every open gate file path from one [workflow container](concepts/workflow-container.md).
- Normalizes: lowercases the query and each haystack value for comparison; missing or falsey haystack values compare as the empty string.
- Returns: `True` immediately for an empty query, without reading the workflow haystacks.
- Returns: `True` for a non-empty query when any documented haystack contains the lowercased query substring; returns `False` when none do.
- Ignores: workflow container id, workflow state, gate question text, gate status text, answer text, exit-code hints, rendered markdown, and detail-pane text.
- Calls: no other groom source symbols.
- Does not mutate: workflow container fields, gate records, inbox ordering, selection state, browser state, server registry state, sidecar state, Docker state, or gate files.

### method-render-inbox-row

- sig: `_inbox_row(wf: WorkflowContainer) -> str`
- abstract: false
- raises: none intentionally raised for workflows with open gate records.
- code: groom/groom/render.py::_inbox_row

Serializes one eligible workflow as the row component documented on the dashboard screen. The row selects the first gate after sorting open gates by `file_path`; uses that path as the primary tail text; falls back to a finished exit-code hint or the current node only when called with no gate; adds an [inbox question preview](concepts/inbox-question-preview.md) only for blocked workflows with a gate; carries `data-worker-id` and `data-state`; renders repository, state, type, short-id, tail, and preview cells; and escapes every dynamic attribute or text value before returning the HTML fragment.

#### Effects

- Reads: workflow container id, state, gates mapping, repository name, repository branch, workflow type, current node, and exit code from one [workflow container](concepts/workflow-container.md).
- Reads: first sorted gate file path and question from [gate info](concepts/gate-info.md) when at least one gate exists.
- Emits: exactly one [inbox worker row](gui/screens/groom-dashboard.md#inbox-worker-row) root fragment with `data-worker-id`, `data-state`, [workflow state dot](concepts/workflow-state-dot-renderer.md), optional [workflow type badge](concepts/workflow-type-badge-renderer.md), repository label, short id, tail text, and optional blocked-question preview.
- Emits: class `blocked` on the row root only when the workflow state is `blocked`; all other states use the base `row` class while retaining their state in `data-state`.
- Emits: a question preview only when both a first gate exists and the workflow state is `blocked`; gated workflows in `running`, `idle`, or `finished` states display the gate path but no preview.
- Emits: the selected gate file path as the row tail when a gate exists; the exit hint and current-node fallback are reachable only if this helper is called for a workflow with no gates.
- Exposes: the workflow id via `data-worker-id` so the dashboard can request worker detail for the selected row.
- Does not mutate: workflow container fields, gate records, inbox ordering, selection state, browser state, server registry state, sidecar state, Docker state, or gate files.
- Calls: [method-build-question-preview](concepts/inbox-question-preview.md#method-build-question-preview), [method-render-exit-hint](#method-render-exit-hint), [method-render-repository-label](#method-render-repository-label), [method-render-short-worker-id](#method-render-short-worker-id), [workflow state dot renderer](concepts/workflow-state-dot-renderer.md#method-render-workflow-state-dot), [workflow type badge renderer](concepts/workflow-type-badge-renderer.md#method-render-workflow-type-badge), and the [HTML escape helper](concepts/html-escape-helper.md#method-escape-html-value) in the row-rendering layer.

### method-render-repository-label

- sig: `_repo_label(wf: WorkflowContainer) -> str`
- abstract: false
- raises: none intentionally raised for missing repository name or branch text.
- code: groom/groom/render.py::_repo_label

Builds the compact repository identity string for one [workflow container](concepts/workflow-container.md). The method is display-only: it reads repository metadata already present on the workflow record, returns unescaped text for the caller to escape when inserting into HTML, and performs no lookup against Docker, sidecar state, filesystem repositories, or the workflow registry.

#### Effects

- Reads: `repo_name` and `repo_branch` from one [workflow container](concepts/workflow-container.md).
- Returns: `{repo_name}@{repo_branch}` when `repo_branch` is non-empty, preserving the repository name exactly as supplied before the `@` separator.
- Returns: `repo_name` when `repo_branch` is empty and `repo_name` is non-empty.
- Returns: the em dash placeholder `—` when both repository name and branch are empty.
- Does not escape: the returned label; row and detail renderers escape it before HTML insertion, while status counting uses it only as an in-memory set member.
- Does not mutate: workflow container fields, open gates, inbox filtering, row selection, status counts, registry state, Docker state, sidecar state, browser state, or gate files.

### method-render-short-worker-id

- sig: `_short_id(wf: WorkflowContainer) -> str`
- abstract: false
- raises: none intentionally raised for empty or short workflow container ids.
- code: groom/groom/render.py::_short_id

Builds the compact worker identifier text used inside an [inbox worker row](gui/screens/groom-dashboard.md#inbox-worker-row). The method is display-only: it reads the workflow container id already present on the workflow record, returns unescaped text for the caller to escape when inserting into HTML, and performs no lookup against Docker, sidecar state, filesystem repositories, or the workflow registry.

#### Effects

- Reads: `container_id` from one [workflow container](concepts/workflow-container.md).
- Returns: the first four characters of `container_id` when the id has at least one character; ids shorter than four characters are returned whole.
- Returns: the placeholder `----` when `container_id` is empty.
- Does not include: the leading `#`; row renderers add that prefix around the escaped returned text.
- Does not escape: the returned short id; row renderers escape it before HTML insertion.
- Does not mutate: workflow container fields, gate records, inbox filtering, row selection, status counts, registry state, Docker state, sidecar state, browser state, or gate files.

### method-render-exit-hint

- sig: `_exit_hint(wf: WorkflowContainer) -> str`
- abstract: false
- raises: none intentionally raised for live, code-less, zero-code, or non-zero-code workflow containers.
- code: groom/groom/render.py::_exit_hint
- verify: groom/tests/test_render.py::test_exit_code_hint_only_on_finished_with_code

Serializes the short terminal-status tail used by row and detail renderers when a workflow is finished and has a known exit code. The method is display-only: it does not change workflow lifecycle state, parse exit payloads, clear gates, or decide whether a workflow belongs in the inbox.

#### Effects

- Reads: [workflow state](concepts/workflow-state.md) and `exit_code` from one [workflow container](concepts/workflow-container.md).
- Returns: the empty string when the workflow state is not `finished`.
- Returns: the empty string when the workflow state is `finished` but `exit_code` is absent.
- Classifies: exit code `0` as `exit-ok`; every known non-zero integer as `exit-err`.
- Emits: `<span class="exit-hint exit-ok">exited 0</span>` for a finished zero-code workflow, or `<span class="exit-hint exit-err">exited {code}</span>` for a finished non-zero-code workflow.
- Escapes: the string form of the exit code before inserting it into the text node.
- Does not mutate: workflow container fields, gate records, inbox eligibility, row selection, current node, registry state, sidecar state, browser state, or gate files.

## Algorithms

### algorithm-render-inbox-fragment

- step: Receive the workflow snapshot list, query string, and out-of-band mode.
- step: Build a new matching list containing only workflows whose `gates` mapping is non-empty and whose searchable fields satisfy [method-match-inbox-query](#method-match-inbox-query).
- step: Sort the matching list by [workflow state](concepts/workflow-state.md) priority `blocked`, `running`, `idle`, `finished`, then workflow name ascending.
- step: If the matching list is empty, render the inner fragment through [method-render-empty-or-loading](#method-render-empty-or-loading) with the static empty message `No incoming messages — inbox zero.` and the current query.
- step: If the matching list is non-empty, render each workflow through [method-render-inbox-row](#method-render-inbox-row) in sorted order and concatenate the resulting row fragments without separators.
- step: Return one `<div class="inbox-list" id="inbox-list">` root around the inner fragment, adding the [field-out-of-band-attribute](#field-out-of-band-attribute) suffix only when requested.

### algorithm-render-inbox-row-fragment

- step: Sort the workflow's open gate records by `file_path` and select the first record, if any.
- step: Use the selected gate path as the row tail when a gate exists; otherwise use [method-render-exit-hint](#method-render-exit-hint) when it returns non-empty, falling back to the workflow current-node text.
- step: Include a blocked-question preview only when the workflow state is `blocked` and a selected gate exists.
- step: Add the `blocked` class only for blocked workflows; all rows carry the base `row` class, `data-worker-id`, and `data-state`.
- step: Emit line-one content in this order: [workflow state dot](concepts/workflow-state-dot-renderer.md), optional [workflow type badge](concepts/workflow-type-badge-renderer.md), repository label, short worker id prefixed with `#`, and tail.
- step: Escape every dynamic attribute and text value before returning the row fragment.

## Failure Semantics

- Unsupported workflow state: inbox sorting indexes the documented state-priority table directly; a workflow state outside [workflow state](concepts/workflow-state.md)'s enum is outside the supported contract and can fail rendering rather than falling back to a display bucket.
- Unsupported gate value: row rendering expects gate records with text `file_path` and `question` values; malformed records are outside the supported contract and can fail in the same way ordinary Python attribute or string operations fail.
- Query input: the supported query type is `str`; `None` or non-string values are outside the contract even though the empty-string default covers ordinary unfiltered rendering.
- Delegated exceptions: this concept defines no domain-specific error object, partial result, or status code; ordinary Python exceptions from delegated render helpers propagate to the caller, and the renderer performs no registry rollback, websocket send, HTTP response construction, gate write, or broadcast itself.
- Empty and unmatched snapshots: an empty workflow list, no open gates, or no query matches are successful inputs that return the empty or loading fragment rather than an error.

## Invariants

- gated-only: workers without open gates never appear in the inbox, even if they are running, idle, finished with an exit code, or matched by the text query.
- answer lifecycle: answering the last gate removes the workflow from the inbox on the next rendered snapshot or live broadcast.
- fleet counts: inbox filtering never redefines status-bar totals; those counts remain global to the workflow registry.
- row accessibility gap: inbox rows are clickable `div` elements without a semantic role, accessible name, or direct keyboard activation; keyboard row movement exists as separate global `j`/`k` behavior on the dashboard.
