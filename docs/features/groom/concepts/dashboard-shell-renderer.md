---
type: concept
slug: dashboard-shell-renderer
title: Dashboard shell renderer
---
# Dashboard shell renderer

Dashboard shell renderer is the groom render-layer function that turns a caller-supplied [workflow container](workflow-container.md) snapshot into one [dashboard shell fragment](../dashboard-shell-fragment.md) for the [groom dashboard](../gui/screens/groom-dashboard.md). It composes the [operator inbox](../operator-inbox.md) live region with the [dashboard shell fragment](../dashboard-shell-fragment.md#field-statusbar-fragment)'s status-bar live region; the [dashboard shell broadcaster](dashboard-shell-broadcaster.md), blocked-push notification path, answer-result path, sidecar state paths, and initial dashboard websocket snapshot use this renderer when they need browser tabs to converge on current fleet state without replacing selected worker detail, repository picker, Files, or Diff panel state.

- code: groom/groom/render.py::render_shell_data
- verify: groom/tests/test_render.py::test_dynamic_regions_have_stable_ids_and_oob_flag

## Contract

- purpose: produce the full server-rendered dashboard shell update that can be sent as one websocket text frame or embedded in another same-swap batch.
- input: caller supplies a list of current [workflow container](workflow-container.md) records; the renderer does not read the workflow registry directly.
- workflow-state domain: every supplied workflow state is expected to be one of the documented [workflow state](workflow-state.md) enum values; there is no fallback display bucket for unknown state values.
- query default: empty string, meaning the inbox part is narrowed only to workflows with open gates.
- query behavior: non-empty query is forwarded unchanged to the [operator inbox](../operator-inbox.md) renderer and affects only inbox row inclusion, not status-bar counts.
- out-of-band default: true, so both live-region roots are normally marked for htmx out-of-band replacement.
- shell scope: includes exactly the `#inbox-list` region followed by the `#statusbar` region. It excludes selected worker detail, repository menu, Files panel content, Diff panel content, notification scripts, answered-event scripts, sidecar JSON frames, HTTP response metadata, and static dashboard chrome.
- ordering: inbox/list fragment always precedes the status-bar fragment in the returned string.
- direct callers: [dashboard shell broadcaster](dashboard-shell-broadcaster.md#method-broadcast-shell), blocked-push and sidecar-blocked broadcast paths, answer-result broadcast path, and the initial browser dashboard websocket snapshot path.
- delegated inbox contract: inbox filtering, query matching, loading-vs-empty selection, row ordering, row markup, row escaping, and the inbox root's optional out-of-band attribute are owned by [operator inbox](../operator-inbox.md#method-render-inbox).
- delegated status-bar contract: status counts for blocked, running, idle, and finished workers; distinct repository totals; worker totals; websocket liveness label; the [statusbar refresh button](../gui/screens/groom-dashboard.md#statusbar-refresh-button); command-palette hint; and the status-bar root's optional out-of-band attribute are owned by [render statusbar](groom-render-module.md#method-render-statusbar) and specified by [field-statusbar-fragment](../dashboard-shell-fragment.md#field-statusbar-fragment).
- indirect process state: the shell renderer itself has no process-global read, but the delegated inbox empty-state path may read the [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) when the workflow snapshot produces no matching inbox rows and the query is empty.
- state mutation: rendering does not mutate workflow containers, gate records, discovery state, websocket client queues, sidecar state, Docker state, answer logs, answer files, or gate files.
- security: delegated renderers HTML-escape dynamic workflow and gate text before it enters text nodes or attributes; this renderer does not add unescaped dynamic content of its own.

## Inputs

### field: workflows

- type: `list[WorkflowContainer]`
- default: none
- required: true
- meaning: current fleet snapshot to render into inbox rows and global status counts.
- ownership: caller-owned list; the renderer treats it as read-only and performs no registry lookup, sorting of the original list, mutation, pruning, or hydration.
- state requirement: every item uses a [workflow state](workflow-state.md) value recognized by inbox ordering and status-bar counting.
- gate requirement: each item's gate mapping may be empty or non-empty; non-empty gates are what make the item eligible for the inbox region.

### field: query

- type: `str`
- default: `""`
- required: false
- meaning: inbox filter text forwarded to the operator-inbox renderer; it does not alter the status-bar total workers, per-state counts, or repository count.
- normalization: forwarded exactly as received; this renderer does not trim, lowercase, split, validate, or escape it before delegation.

### field: oob

- type: `bool`
- default: `True`
- required: false
- meaning: when true, both returned live-region roots include `hx-swap-oob="true"`; when false, the same roots are returned without the out-of-band attribute.
- scope: applies to both top-level roots together; the renderer has no mode that marks only the inbox root or only the status-bar root out of band.

## Output

### field: shell-fragment

- type: [dashboard shell fragment](../dashboard-shell-fragment.md)
- default: none
- required: true
- meaning: concatenated inbox/list and status-bar HTML fragments for the current workflow snapshot.
- grammar: `<div class="inbox-list" id="inbox-list"{oob}>...</div><div id="statusbar"{oob}>...</div>` with no wrapper, delimiter, newline, script, JSON envelope, or transport metadata added by this renderer.
- status-bar content: the second root contains four state-count segments in blocked, running, idle, finished order; one distinct-repository total; one worker total; static websocket-live text; the refresh button; and the command-palette hint.
- inbox empty-state dependency: the first root may contain the discovery loading placeholder instead of inbox-zero text only when the delegated inbox renderer sees no matching gated workflows, the query is empty, and the [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) is true.
- consumers: browser dashboard websocket initial snapshots, shell broadcasts, blocked-push broadcasts, answer-result broadcasts, sidecar state broadcasts, progress/exited broadcasts, and refresh broadcasts.

## Methods

### method-render-shell-data

- sig: `render_shell_data(workflows: list[WorkflowContainer], query: str = "", *, oob: bool = True) -> str`
- abstract: false
- raises: none intentionally raised for empty, unmatched, or partially populated workflow snapshots.
- code: groom/groom/render.py::render_shell_data
- verify: groom/tests/test_render.py::test_dynamic_regions_have_stable_ids_and_oob_flag

Builds the dashboard shell fragment from one workflow snapshot. The method delegates inbox filtering and row rendering to [operator inbox](../operator-inbox.md), delegates status-bar totals and refresh-control markup to the status-bar renderer specified by [field-statusbar-fragment](../dashboard-shell-fragment.md#field-statusbar-fragment), and returns the two fragments as one string without adding separators, wrappers, notification scripts, or JSON envelopes.

#### Effects

- Reads: the supplied workflow list, the optional inbox query, and the requested out-of-band mode.
- Indirectly reads: the [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) only through the delegated inbox empty-state branch for an empty query with no matching gated workflows.
- Calls: [operator inbox](../operator-inbox.md#method-render-inbox) once with the workflow list, query, and out-of-band flag.
- Calls: [render statusbar](groom-render-module.md#method-render-statusbar) once with the workflow list and out-of-band flag; that layer is already grounded by [field-statusbar-fragment](../dashboard-shell-fragment.md#field-statusbar-fragment) and [statusbar refresh button](../gui/screens/groom-dashboard.md#statusbar-refresh-button).
- Call order: the status-bar renderer is reached only after the inbox renderer returns successfully.
- Emits: one [dashboard shell fragment](../dashboard-shell-fragment.md) whose first part targets `#inbox-list` and whose second part targets `#statusbar`.
- Excludes: worker detail panes, file trees, file contents, diffs, repository picker rows, browser-event scripts, sidecar RPC frames, and HTTP response metadata.
- Does not mutate: workflow containers, open gates, registry membership, scanning state, websocket queues, browser DOM state, sidecar state, Docker state, answer logs, answer files, or gate files.

## Algorithms

### algorithm-render-dashboard-shell-fragment

- step: Receive the workflow snapshot list, optional inbox query, and out-of-band mode selected by the caller.
- step: Pass the workflow snapshot, query string, and out-of-band mode to [operator inbox](../operator-inbox.md#method-render-inbox), producing the complete `#inbox-list` root for only currently eligible gated workflows.
- step: Pass the same workflow snapshot and out-of-band mode to [render statusbar](groom-render-module.md#method-render-statusbar), producing the complete `#statusbar` root with fleet-wide counts and status-bar controls; the query is intentionally not passed to this layer.
- step: Concatenate the inbox root string before the status-bar root string with no separator or wrapper.
- step: Return the concatenated [dashboard shell fragment](../dashboard-shell-fragment.md) to the caller for websocket send, queue broadcast, HTTP response composition, or same-swap batching with separate script fragments.

## Invariants

- same snapshot: the inbox and status-bar roots are rendered from the same workflow list supplied to this call.
- query isolation: inbox query text can narrow `#inbox-list`, but it never changes `#statusbar` state counts, repository totals, worker totals, refresh markup, liveness label, or palette hint.
- scanning isolation: the process-local discovery scanning flag can change only the delegated inbox empty-state body; it never changes status-bar counts, root order, out-of-band attributes, companion scripts, websocket metadata, or mutation behavior.
- root identity: every return value contains exactly one `id="inbox-list"` root and exactly one `id="statusbar"` root.
- root order: `#inbox-list` precedes `#statusbar` in every returned shell fragment.
- out-of-band parity: both roots either carry `hx-swap-oob="true"` or both omit it according to the single `oob` input.
- no companion scripts: blocked notification and answered-event scripts are appended by callers after this fragment; this renderer never emits those scripts itself.
- no direct hidden state read: this renderer does not directly read process-global workflow state, browser selection state, sidecar state, Docker state, answer logs, answer files, or gate files; the only indirect process-state read is the delegated inbox empty-state check for discovery scanning.

## Failure Semantics

- The renderer defines no domain-specific error channel and returns no partial-result status; ordinary Python exceptions from the delegated inbox or status-bar renderers propagate to the caller.
- If inbox rendering raises, status-bar rendering is not attempted; if status-bar rendering raises, no shell fragment is returned.
- If delegated rendering raises, this renderer performs no websocket send, queue broadcast, HTTP response construction, or registry rollback; those are caller responsibilities.
- Empty workflow lists, no matching inbox rows, missing optional workflow text fields, and either out-of-band mode are ordinary successful inputs handled by the delegated renderers.
- Because the function only concatenates delegated strings after both calls return, caller-visible side effects are limited to whether the caller later sends or broadcasts the returned text.
