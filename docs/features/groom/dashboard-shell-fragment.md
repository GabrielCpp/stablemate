---
type: format
slug: dashboard-shell-fragment
title: Dashboard shell fragment
---
# Dashboard shell fragment

Dashboard shell fragment is the HTML format produced by the [dashboard shell renderer](concepts/dashboard-shell-renderer.md) and sent over [websocket-dashboard](http/groom.md#websocket-dashboard) broadcasts to update the [groom dashboard](gui/screens/groom-dashboard.md). It contains the current [operator inbox](operator-inbox.md) replacement target and status-bar replacement target for the same [workflow container](concepts/workflow-container.md) snapshot; the inbox part can show the provisional loading state from the [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md), while the status-bar part always counts the supplied workflow list. Callers that need browser events append separate script fragments after this shell fragment rather than changing the shell shape.

- file: not an on-disk artifact; this is a transient HTML websocket/HTTP fragment.
- code: groom/groom/render.py::render_shell_data
- verify: groom/tests/test_render.py::test_dynamic_regions_have_stable_ids_and_oob_flag
- verify: groom/tests/test_render.py::test_statusbar_counts_states
- verify: groom/tests/test_render.py::test_statusbar_has_refresh_button
- verify: groom/tests/test_render.py::test_inbox_shows_only_workers_with_open_gates
- verify: groom/tests/test_render.py::test_empty_inbox_shows_spinner_while_scanning
- verify: groom/tests/test_render.py::test_search_with_query_shows_empty_not_spinner_even_while_scanning

## Contract

- producer: [dashboard shell renderer](concepts/dashboard-shell-renderer.md) serializes this format from a caller-supplied workflow snapshot by concatenating [operator inbox](operator-inbox.md#method-render-inbox) output and status-bar output.
- inputs: a list of [workflow container](concepts/workflow-container.md) records, optional inbox query text, an out-of-band mode flag, and the process-local [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md) read by the delegated inbox empty-state path; the status-bar portion ignores the query and scanning flag.
- consumers: browser dashboard websocket swaps, initial dashboard websocket snapshot, blocked-push broadcasts, answer-result broadcasts, sidecar state broadcasts, progress/exited broadcasts, and refresh broadcasts consume the fragment as htmx-compatible HTML.
- media: HTML fragment text, not a full HTML document and not JSON.
- root count: exactly two top-level replacement roots are produced by the shell renderer: `#inbox-list` first and `#statusbar` second.
- source grammar: `<div class="inbox-list" id="inbox-list"{oob}>...</div><div id="statusbar"{oob}>...</div>`, where `{oob}` is either the exact out-of-band attribute suffix or the empty string.
- production order: the shell renderer calls the inbox renderer exactly once, then calls the status-bar renderer exactly once, and returns the two resulting strings adjacent in that order.
- out-of-band mode: when the renderer's `oob` input is true, both live-region roots carry `hx-swap-oob="true"`; when false, neither root carries that attribute.
- input forwarding: the renderer forwards the supplied workflow list, query string, and out-of-band flag unchanged to the inbox fragment; it forwards only the supplied workflow list and out-of-band flag to the status-bar fragment.
- replacement targets: `#inbox-list` replaces the dashboard's operator inbox list; `#statusbar` replaces the dashboard status bar. No other DOM region is targeted by this fragment.
- snapshot consistency: both regions represent the same workflow list supplied to the renderer, while an inbox query may narrow only the inbox rows.
- query behavior: non-empty query affects only `#inbox-list`; `#statusbar` always counts the full supplied workflow list.
- scanning behavior: when no workflow qualifies for `#inbox-list`, an empty query and a true [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md) produce the discovery loading placeholder; any non-empty query produces the normal inbox-zero text even while scanning is true.
- websocket envelope: the fragment is sent as websocket text content directly; there is no JSON wrapper, message type, request id, acknowledgement id, or version field around it.
- append-only companions: blocked notifications and successful answer events are represented by separate script fragments appended after this fragment in the same websocket text payload; this fragment never embeds those scripts itself.
- excluded content: selected worker detail, repository menu, files tree, file content, diff content, browser notification scripts, answered-event scripts, sidecar JSON frames, and HTTP response wrappers are outside this format.
- escaping: dynamic workflow and gate text inside the regions is HTML-escaped by the delegated renderers before the fragment is returned.
- mutation: rendering this fragment does not add, remove, reorder, or mutate workflow containers, gates, repositories, answer logs, websocket clients, or scanning state.
- accessibility: the produced roots have stable ids but no explicit `role`, `aria-live`, or accessible name in the fragment; the status-bar refresh button inside `#statusbar` is the only interactive control in this format and is documented on the [groom dashboard](gui/screens/groom-dashboard.md#statusbar-refresh-button).
- failure model: the format has no embedded error channel; renderer exceptions propagate to the caller before any websocket send or queueing step completes.
- deeper calls: the shell renderer delegates inbox-root construction to [operator inbox](operator-inbox.md#method-render-inbox) and status-bar-root construction to `groom/groom/render.py::render_statusbar`; it performs no parsing, no state lookup, and no first-party mutation itself.

## Inputs

### field: workflows-input

- type: `list[WorkflowContainer]`
- default: none
- required: true
- consumer-use: passed as the first positional input to both delegated root renderers.
- mutation: not mutated by the shell renderer.
- meaning: caller-supplied fleet snapshot used by both top-level roots; each workflow may contribute inbox rows, state counts, repository totals, and worker totals according to the delegated root renderers.

### field: query-input

- type: `str`
- default: `""`
- required: false
- consumer-use: passed only to the inbox-root renderer.
- normalization: not stripped, lowercased, parsed, or otherwise changed by the shell renderer.
- meaning: inbox filter text forwarded unchanged to the `#inbox-list` renderer; it never changes `#statusbar` counts, repository totals, worker totals, liveness text, refresh markup, or command-palette hint.

### field: oob-input

- type: `bool`
- default: `True`
- required: false
- consumer-use: passed unchanged to both delegated root renderers.
- meaning: whole-fragment out-of-band mode; true selects the exact ` hx-swap-oob="true"` suffix for both roots, and false selects the empty suffix for both roots.

### field: discovery-scanning-flag-input

- type: `bool`
- default: process-local initial value is `True`
- required: true for empty unfiltered inbox rendering; not passed as a renderer argument.
- code: groom/groom/state.py::SCANNING
- consumer-use: read indirectly by the delegated inbox empty-state renderer only after workflow filtering leaves no inbox rows.
- meaning: presentation-state flag that decides whether an empty unfiltered `#inbox-list` represents discovery still in progress (`Discovering containers…`) or inbox zero (`No incoming messages — inbox zero.`); it never changes the status-bar fragment.

## Fields

### field-inbox-list-fragment

- type: HTML fragment rooted at `<div class="inbox-list" id="inbox-list">`
- default: none
- required: true
- root: `<div class="inbox-list" id="inbox-list"{oob}>...</div>`.
- code: groom/groom/render.py::render_inbox
- attributes: fixed `class="inbox-list"`, fixed `id="inbox-list"`, optional `hx-swap-oob="true"`, and no first-party `data-*`, `role`, `aria-*`, `tabindex`, or inline `style` attributes on the root.
- content: zero or more [inbox worker row](gui/screens/groom-dashboard.md#inbox-worker-row) fragments, the inbox-zero empty state `No incoming messages — inbox zero.`, or the discovery loading state `Discovering containers…`.
- selection rule: includes only workflows with at least one open gate and matching the current inbox query.
- empty rule: when no workflow qualifies and discovery is not scanning, or when the query is non-empty, emits `<div class="empty">No incoming messages — inbox zero.</div>`.
- loading rule: when no workflow qualifies, discovery is scanning, and the query is empty, emits `<div class="empty loading"><span class="spin"></span>Discovering containers…</div>`.
- filtered loading rule: when no workflow qualifies and the query is non-empty, emits the normal inbox-zero empty state even when the [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md) is true.
- ordering: included rows are sorted by workflow state priority and workflow name by the delegated [operator inbox](operator-inbox.md) renderer.
- accessibility: root has no explicit `role`, `aria-live`, tabindex, or accessible name; row-level a11y is documented on the [inbox worker row](gui/screens/groom-dashboard.md#inbox-worker-row).
- meaning: operator-inbox replacement target for actionable gate messages in the current query and workflow snapshot.

### field-statusbar-fragment

- type: HTML fragment rooted at `<div id="statusbar">`
- default: none
- required: true
- root: `<div id="statusbar"{oob}>...</div>`.
- code: groom/groom/render.py::render_statusbar
- attributes: fixed `id="statusbar"`, optional `hx-swap-oob="true"`, and no first-party root `class`, `data-*`, `role`, `aria-*`, `tabindex`, or inline `style` attributes.
- content: four per-state count segments, total repository count, total worker count, websocket liveness label, [statusbar refresh button](gui/screens/groom-dashboard.md#statusbar-refresh-button), and static command-palette hint.
- counts: emits blocked, running, idle, and finished segments in that order, each as a state dot plus `<span class="n">{count}</span> {state}`.
- repository total: counts distinct repository labels after applying the renderer's repository-label rule to every supplied workflow; a workflow without a repository name contributes the fallback label `—`.
- worker total: counts every supplied workflow, regardless of state, gates, inbox query, selected worker, or repository selection.
- websocket label: emits a visual `live` marker with `.ws-dot`; it is static text and not a connection-state protocol field.
- refresh control: emits native button `<button id="btn-refresh-bar" class="statusbar-refresh" title="Rescan containers (reconcile + prune)">⟳</button>`.
- palette hint: emits static hint text containing `<span class="kbd">⌘K</span> palette`; it is not a focusable control.
- accessibility: root has no explicit `role`, `aria-live`, tabindex, or accessible name; the refresh control has native button role, accessible name from its title, and native keyboard activation.
- meaning: dashboard status-bar replacement target for fleet-wide counts and always-visible refresh/palette affordance for the current workflow snapshot.

### field-hx-swap-oob-attribute

- type: HTML boolean-like attribute text
- default: absent when renderer `oob` is false; present when renderer `oob` is true.
- required: false
- code: groom/groom/render.py::_oob
- value: exact leading-space attribute suffix ` hx-swap-oob="true"` when enabled; empty string when disabled.
- placement: appears on both top-level roots or neither root; the renderer never marks only one of `#inbox-list` and `#statusbar`.
- target dependency: requires matching elements with ids `inbox-list` and `statusbar` to already exist in the dashboard document for htmx out-of-band replacement.
- meaning: htmx out-of-band marker on each replacement root that tells websocket swaps to update matching existing dashboard elements instead of treating the fragment as ordinary in-band content.

### field-fragment-order

- type: fixed ordering rule
- default: `inbox-list` then `statusbar`
- required: true
- code: groom/groom/render.py::render_shell_data
- separator: none; the two complete root fragments are adjacent in one string.
- delegated calls: `render_inbox(workflows, query, oob=oob)` followed by `render_statusbar(workflows, oob=oob)`.
- query scope: the query input is absent from the status-bar call.
- companion placement: notification and answered-event scripts, when present, are appended after this two-root sequence by the caller.
- meaning: the inbox/list fragment is concatenated before the status-bar fragment with no wrapper, delimiter, newline, JSON envelope, or script between them.
