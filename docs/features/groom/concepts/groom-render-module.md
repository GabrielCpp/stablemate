---
type: concept
slug: groom-render-module
title: Groom render module
---
# Groom render module

Groom render module is the server-side HTML-fragment rendering boundary for the [groom dashboard](../gui/screens/groom-dashboard.md). It consumes in-memory [workflow container](workflow-container.md) and [gate info](gate-info.md) records, applies the shared [workflow state](workflow-state.md) display order, escapes dynamic values through the [HTML escape helper](html-escape-helper.md), and emits the [operator inbox](../operator-inbox.md), repository menu, worker detail, status bar, dashboard shell, blocked-notification script, and answered-notification script fragments used by the [groom server](../http/groom.md). The module owns string rendering only: callers own workflow registry reads and mutations, HTTP responses, websocket sends, Docker and sidecar I/O, answer-file writes, and browser-side markdown or diff rendering.

- code: groom/groom/render.py
- verify: groom/tests/test_render.py::test_dynamic_regions_have_stable_ids_and_oob_flag,
  groom/tests/test_render.py::test_statusbar_counts_states,
  groom/tests/test_render.py::test_gate_question_rendered_as_escaped_data_md_text_node,
  groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form,
  groom/tests/test_render.py::test_worker_detail_has_one_diff_disclosure,
  groom/tests/test_render.py::test_repo_menu_one_entry_per_container_repo,
  groom/tests/test_render.py::test_inbox_shows_only_workers_with_open_gates,
  groom/tests/test_render.py::test_render_answered_script_carries_worker_and_file
- refs: [operator inbox](../operator-inbox.md), [dashboard shell fragment](../dashboard-shell-fragment.md), [worker detail renderer](worker-detail-renderer.md), [repository menu data](../repository-menu-data.md), [blocked notification script fragment](../blocked-notification-script-fragment.md), [groom answered script fragment](../groom-answered-script-fragment.md)

## Contract

- purpose: convert caller-supplied groom dashboard state into safe HTML or same-swap script fragments without performing state lookup, persistence, transport, Docker, sidecar, markdown, or diff work.
- import behavior: importing the module binds renderer functions, the state-order mapping, and standard-library JSON/HTML helpers only; it performs no scan, socket registration, file I/O, Docker subprocess, HTTP response construction, websocket send, or template read.
- input ownership: callers supply workflow snapshots, repository-menu entries, selected worker records, notification messages, and answered-gate identifiers; the module treats those values as render inputs and never fetches them from the workflow registry.
- output ownership: every public renderer returns a string fragment; callers decide whether to embed it in an HTTP response, send it over a websocket, concatenate it with other fragments, or discard it.
- dynamic regions: `#inbox-list` and `#statusbar` are the only broadcast shell roots rendered by this module; selected worker detail, repository picker, Files, and Diff panels are rendered or fetched on demand so live broadcasts do not clobber operator-local selection or typed answer state.
- escaping boundary: dynamic workflow, repository, gate, message, and identifier text is escaped before insertion into HTML attributes or text nodes, except for JSON script details that are serialized as JavaScript literals by the standard-library JSON encoder.
- markdown boundary: gate questions are emitted as escaped text inside `data-md` nodes for browser-side markdown rendering and DOMPurify sanitization; the module never emits agent-authored markdown as raw HTML.
- side-effect boundary: rendering does not mutate workflow containers, gate maps, discovery state, selected browser state, websocket client queues, sidecar sessions, Docker containers, answer logs, answer files, or gate files.
- first-party public members: exactly `STATE_ORDER`, `esc`, `render_loading`, `render_repo_menu`, `render_inbox`, `render_statusbar`, `render_worker_detail`, `render_shell_data`, `render_notify_script`, and `render_answered_script` form the module's public render surface.
- private member folding: private helpers are folded into the public member contracts they serve; helper concepts already document state dots, workflow-type badges, question previews, repository labels, short ids, exit hints, detail headers, and out-of-band swap attributes where they are observable.
- external boundary: Python standard-library HTML escaping and JSON serialization are below this groom module and do not create deeper groom crawl items.

## Fields

### field-state-order

- type: `dict[WorkflowState, int]`
- default: `{BLOCKED: 0, RUNNING: 1, IDLE: 2, FINISHED: 3}`
- required: true
- code: groom/groom/render.py::STATE_ORDER
- detail: [workflow state](workflow-state.md)
- meaning: shared display-order map used when sorting inbox rows and repository-menu workflow groups.
- ordering: blocked workers sort first, then running, idle, and finished workers.
- mutation: treated as module constant by renderers; no public renderer writes to it.

## Public Members

### method-esc

- sig: `esc(value: str | None) -> str`
- abstract: false
- raises: none intentionally raised for `None`, empty strings, quote characters, markup-like text, already-escaped entity text, or non-ASCII text.
- code: groom/groom/render.py::esc
- verify: groom/tests/test_render.py::test_gate_question_rendered_as_escaped_data_md_text_node
- detail: [HTML escape helper](html-escape-helper.md)
- does:
  - Converts `None` to the empty string and escapes dynamic text for safe insertion into groom-rendered HTML attributes and text nodes.
  - Leaves markdown sanitization, URL validation, CSS validation, and document-level HTML sanitization outside this helper.

### method-render-loading

- sig: `render_loading(message: str = "Discovering containers…") -> str`
- abstract: false
- raises: none intentionally raised for empty, unsafe, already-escaped, or non-ASCII display messages.
- code: groom/groom/render.py::render_loading
- verify: groom/tests/test_render.py::test_empty_inbox_shows_spinner_while_scanning
- detail: [operator inbox loading fragment](../operator-inbox.md#method-render-loading)
- does:
  - Emits one non-interactive `<div class="empty loading">` fragment with a spinner span and escaped message text.
  - Provides the provisional empty state used while discovery is scanning and the inbox query is empty.

### method-render-repo-menu

- sig: `render_repo_menu(entries: list[tuple[WorkflowContainer, list[str]]]) -> str`
- abstract: false
- raises: none intentionally raised for empty entries, workflows without discovered repositories, or empty checkout-directory lists.
- code: groom/groom/render.py::render_repo_menu
- verify: groom/tests/test_render.py::test_repo_menu_one_entry_per_container_repo,
  groom/tests/test_render.py::test_repo_menu_empty_when_no_entries
- detail: [repository menu data](../repository-menu-data.md)
- component: [repository menu option](../gui/screens/groom-dashboard.md#repository-menu-option)
- does:
  - Sorts workflow groups by [field-state-order](#field-state-order) and workflow name.
  - For each sorted workflow group, preserves the caller-supplied checkout-directory order when expanding rows.
  - Emits one `role="option"` repository-menu row per supplied checkout directory, or one synthetic volume-root row with `data-repo=""` when a workflow has no checkout directories.
  - Derives each option label as `workflow.name/repo` for non-empty checkout directories and as `workflow.name` for the synthetic volume-root row.
  - Carries `data-container`, `data-repo`, and `data-label` attributes for the browser repository picker and escapes every dynamic attribute value and visible label before insertion.
  - Prefixes each option row with a [workflow state dot renderer](workflow-state-dot-renderer.md) fragment and, when `workflow_type` is non-empty, a [workflow type badge renderer](workflow-type-badge-renderer.md) fragment.
  - Emits a non-interactive `<div class="repo-empty">No repositories available.</div>` fragment when no rows are available.
  - Performs no workflow lookup, checkout discovery, repository filtering, selection-state mutation, websocket send, HTTP response construction, or browser-side menu insertion.

### method-render-inbox

- sig: `render_inbox(workflows: list[WorkflowContainer], query: str = "", *, oob: bool = False) -> str`
- abstract: false
- raises: none intentionally raised for ordinary empty, unmatched, or partially populated workflow snapshots.
- code: groom/groom/render.py::render_inbox
- verify: groom/tests/test_render.py::test_inbox_shows_only_workers_with_open_gates,
  groom/tests/test_render.py::test_inbox_orders_gated_workers_by_state_then_name,
  groom/tests/test_render.py::test_empty_inbox_message,
  groom/tests/test_render.py::test_empty_inbox_shows_spinner_while_scanning,
  groom/tests/test_render.py::test_empty_inbox_shows_empty_state_when_not_scanning,
  groom/tests/test_render.py::test_search_with_query_shows_empty_not_spinner_even_while_scanning
- detail: [operator inbox](../operator-inbox.md)
- does:
  - Filters the supplied workflow snapshot to workers with open gates that match the current inbox query.
  - Sorts included workers by [field-state-order](#field-state-order) and workflow name.
  - Emits the complete `#inbox-list` root with optional out-of-band swap markup, ordered inbox rows, or the documented loading/empty state.

### method-render-statusbar

- sig: `render_statusbar(workflows: list[WorkflowContainer], *, oob: bool = False) -> str`
- abstract: false
- raises: none intentionally raised for empty or partially populated workflow snapshots.
- code: groom/groom/render.py::render_statusbar
- verify: groom/tests/test_render.py::test_statusbar_counts_states,
  groom/tests/test_render.py::test_statusbar_has_refresh_button
- detail: [dashboard shell fragment statusbar field](../dashboard-shell-fragment.md#field-statusbar-fragment)
- component: [statusbar refresh button](../gui/screens/groom-dashboard.md#statusbar-refresh-button)
- does:
  - Counts the supplied workflows by every [workflow state](workflow-state.md) value.
  - Counts distinct repository labels using the same repository-label helper documented by the [operator inbox](../operator-inbox.md#method-render-repository-label).
  - Emits the complete `#statusbar` root with optional out-of-band swap markup, four state-count segments, repository and worker totals, websocket liveness text, refresh button, and command-palette hint.
  - Does not apply the inbox query; status-bar counts always describe the full supplied workflow snapshot.

### method-render-worker-detail

- sig: `render_worker_detail(wf: WorkflowContainer | None) -> str`
- abstract: false
- raises: none intentionally raised for an unknown worker, a worker without gates, or multiple gates; those cases are represented as normal fragments.
- code: groom/groom/render.py::render_worker_detail
- verify: groom/tests/test_render.py::test_gate_question_rendered_as_escaped_data_md_text_node,
  groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form,
  groom/tests/test_render.py::test_worker_detail_has_one_diff_disclosure,
  groom/tests/test_render.py::test_worker_detail_not_found_and_no_gate_states,
  groom/tests/test_render.py::test_exit_code_hint_only_on_finished_with_code
- detail: [worker detail renderer](worker-detail-renderer.md)
- does:
  - Emits the selected-worker `#detail` fragment for an unknown worker, a worker with no open gates, or a worker with one or more open gates.
  - Sorts open gates by file path, renders gate questions as escaped `data-md` text nodes, renders one websocket answer form per gate, and renders one lazy working-tree diff disclosure per gated worker.

### method-render-shell-data

- sig: `render_shell_data(workflows: list[WorkflowContainer], query: str = "", *, oob: bool = True) -> str`
- abstract: false
- raises: none intentionally raised for empty, unmatched, or partially populated workflow snapshots.
- code: groom/groom/render.py::render_shell_data
- verify: groom/tests/test_render.py::test_dynamic_regions_have_stable_ids_and_oob_flag
- detail: [dashboard shell renderer](dashboard-shell-renderer.md)
- format: [dashboard shell fragment](../dashboard-shell-fragment.md)
- does:
  - Renders the [operator inbox](../operator-inbox.md) and status-bar live regions from the same workflow snapshot.
  - Concatenates `#inbox-list` before `#statusbar` with no wrapper, delimiter, notification script, answered-event script, JSON envelope, or transport metadata.

### method-render-notify-script

- sig: `render_notify_script(message: str) -> str`
- abstract: false
- raises: none intentionally raised for empty, unsafe, quote-containing, or non-ASCII messages.
- code: groom/groom/render.py::render_notify_script
- detail: [blocked notification script renderer](blocked-notification-script-renderer.md)
- format: [blocked notification script fragment](../blocked-notification-script-fragment.md)
- does:
  - Emits one inline script fragment that dispatches `groom:blocked` on `document.body` with the caller-supplied message serialized as the event detail.
  - Performs no shell rendering, broadcast, browser permission request, gate mutation, or answer-file write.

### method-render-answered-script

- sig: `render_answered_script(container_id: str, file_path: str) -> str`
- abstract: false
- raises: none intentionally raised for empty, unsafe, quote-containing, or non-ASCII identifiers.
- code: groom/groom/render.py::render_answered_script
- verify: groom/tests/test_render.py::test_render_answered_script_carries_worker_and_file
- detail: [answered notification script renderer](answered-notification-script-renderer.md)
- format: [groom answered script fragment](../groom-answered-script-fragment.md)
- does:
  - Emits one inline script fragment that dispatches `groom:answered` on `document.body` with [groom answered browser event detail](../groom-answered-browser-event-detail.md) containing the answered worker id and gate file path.
  - Performs no gate answering, answer-log append, shell rendering, broadcast, browser toast rendering, or detail-pane refresh itself.

## Invariants

- pure rendering: every public function returns a string or value derived from supplied arguments and documented module state; none has first-party side effects beyond ordinary exception propagation.
- small-fleet replacement: inbox and status-bar live regions are rendered as whole replacement roots; this module does not emit incremental row patches.
- stable root ids: dashboard live-region replacement depends on `#inbox-list`, `#statusbar`, and `#detail` root ids remaining stable across render paths.
- answer safety: typed answer text is never part of shell broadcasts; answer forms appear only in selected worker detail fetched on demand.
- untrusted question handling: gate questions always follow escaped text-node to client-side sanitizer flow and never server-render as trusted markdown HTML.
- state order reuse: inbox row sorting and repository-menu group sorting use the same [field-state-order](#field-state-order) priority so blocked workers are surfaced ahead of running, idle, and finished workers in both places.

## Failure Semantics

- The module defines no domain-specific error envelope, no fallback renderer, and no partial-result status object; ordinary Python exceptions propagate to the caller.
- Empty workflow lists, empty repository-menu entries, unknown workers, no-open-gate workers, unmatched inbox queries, missing optional workflow text, and both out-of-band modes are normal successful render inputs.
- If a renderer raises before returning, it performs no send, broadcast, HTTP response construction, workflow rollback, gate rollback, or browser-side recovery; callers own those effects.
