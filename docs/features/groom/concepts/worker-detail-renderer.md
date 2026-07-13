---
type: concept
slug: worker-detail-renderer
title: Worker detail renderer
---
# Worker detail renderer

Worker detail renderer is the pure HTML-fragment renderer used by the [serve worker detail](../http/groom.md#serve-worker-detail) invocation after the route has looked up an optional [workflow container](workflow-container.md). It turns the selected worker plus its open [gate info](gate-info.md) records into the dashboard `#detail` replacement fragment, including the [detail answer textarea](../gui/screens/groom-dashboard.md#detail-answer-textarea) and [detail send answer button](../gui/screens/groom-dashboard.md#detail-send-answer-button) that produce a [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md), plus the [detail working tree diff toggle](../gui/screens/groom-dashboard.md#detail-working-tree-diff-toggle) that lazily requests [workspace diff data](../workspace-diff-data.md). Its worker header composes the existing [workflow state dot renderer](workflow-state-dot-renderer.md), [workflow type badge renderer](workflow-type-badge-renderer.md), [repository-label helper](../operator-inbox.md#method-render-repository-label), [exit-hint helper](../operator-inbox.md#method-render-exit-hint), and [HTML escape helper](html-escape-helper.md).

- code: groom/groom/render.py::render_worker_detail
- verify: groom/tests/test_render.py::test_gate_question_rendered_as_escaped_data_md_text_node,
  groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form,
  groom/tests/test_render.py::test_worker_detail_has_one_diff_disclosure,
  groom/tests/test_render.py::test_worker_detail_not_found_and_no_gate_states,
  groom/tests/test_render.py::test_exit_code_hint_only_on_finished_with_code

## Contract

- purpose: produce one complete dashboard detail-pane HTML fragment for replacing `#detail` after `GET /worker/{container_id}`.
- input: `wf` is either `None` for an unknown worker id or one in-memory [workflow container](workflow-container.md).
- output: always returns an HTML string whose outer element is `<div id="detail">`; no branch returns a partial sibling fragment, JSON payload, status object, websocket frame, script fragment, out-of-band swap marker, or HTTP metadata.
- unknown worker state: when `wf` is `None`, returns exactly the detail root containing `<div class="detail-empty">Worker not found.</div>` and no worker header, gate block, answer form, hidden answer fields, question markdown node, or diff disclosure.
- no-open-gate state: when `wf.gates` is empty, returns the detail root with the worker header plus one `.detail-empty` message. The message says `No open gate`, includes the escaped workflow state inside `<b>`, and includes ` at node <code>{current_node}</code>` only when `wf.current_node` is non-empty.
- open-gate state: when `wf.gates` is non-empty, returns the detail root with the worker header, a `.detail-body`, one `.gate-block` per open gate sorted ascending by `file_path`, and exactly one working-tree diff disclosure after all gate blocks.
- gate ordering: open gates are rendered from `sorted(wf.gates.values(), key=lambda g: g.file_path)`; insertion order in the gate map, question text, and gate status do not affect detail order.
- gate block: each gate block contains the escaped gate file path in `.gate-path`, escaped gate question markdown in a `.question[data-md]` text node, and one websocket answer form scoped by the selected workflow id and the gate file path.
- answer form: each open gate form has class `answer`, boolean `ws-send`, no explicit `action`, and no explicit HTTP `method`; it contains hidden `cmd=answer`, hidden `workflow_id` from the selected workflow container id, hidden `file_path` from the gate file path, one multiline textarea named `answer` with placeholder `Your answer…` and `rows="4"`, plus one `<div class="answer-actions">` wrapper containing one submit button with class `btn`, `type="submit"`, and visible text `Send answer`.
- diff disclosure: a gated worker receives one `<details class="disclosure" data-diff="{container_id}">` after all gate blocks, with summary text `Working-tree diff` and one empty `.diff-wrap[data-diff-target][data-container]` body for the browser to populate lazily.
- worker header: includes state dot, optional workflow-type badge, repository/branch label, `#` plus the first six characters of the container id, the workflow state value, optional current-node suffix, and optional finished exit-code hint.
- worker header order: the header fragment starts with the visual state marker and optional workflow-type badge, then the escaped repository/branch label, then a `.meta` span containing the escaped short worker id, escaped state value, optional escaped current-node suffix, and finally the finished exit-code hint when present.
- escaping: every dynamic text or attribute value emitted by this renderer or its direct helpers is HTML-escaped before it enters the fragment; gate questions are emitted as escaped text for client-side markdown sanitization rather than as raw HTML.
- accessibility: the rendered answer textarea has no durable accessible name because the code supplies only placeholder text; the send-answer control is a native submit button named `Send answer`; the diff control is a native details summary named `Working-tree diff`; the header, empty states, gate path, hidden inputs, answer-actions wrapper, diff body, and markdown question are display-only or non-interactive support nodes.
- side effects: does not mutate workflow state, remove gates, write answers, contact Docker, contact sidecars, compute diffs, broadcast websocket updates, dispatch browser events, or render markdown.
- failure semantics: unknown workers and no-open-gate workers are successful render states; the renderer defines no domain-specific exception, fallback fragment, or partial-output error branch.

## Methods

### render-worker-detail

- sig: `render_worker_detail(wf: WorkflowContainer | None) -> str`
- abstract: false
- raises: none intentionally raised for an unknown worker, a worker without gates, or multiple gates; those cases are represented as normal fragments.
- code: groom/groom/render.py::render_worker_detail
- summary: render the selected worker detail pane fragment for the dashboard `#detail` region.
- verify: groom/tests/test_render.py::test_gate_question_rendered_as_escaped_data_md_text_node,
  groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form,
  groom/tests/test_render.py::test_worker_detail_has_one_diff_disclosure,
  groom/tests/test_render.py::test_worker_detail_not_found_and_no_gate_states,
  groom/tests/test_render.py::test_exit_code_hint_only_on_finished_with_code
- returns: one HTML fragment string rooted at `<div id="detail">` with the branch-specific contents described by the contract.
- args:
  - `wf`: optional [workflow container](workflow-container.md); `None` selects the unknown-worker empty state.
- does:
  - Selects the unknown-worker, no-open-gate, or open-gate branch from the optional workflow and its current `gates` mapping.
  - Returns the unknown-worker empty state without calling the header, answer-form, or diff-disclosure renderers when the workflow is absent.
  - Sorts open [gate info](gate-info.md) records by `file_path` before rendering gate blocks.
  - Calls [render-detail-head](#render-detail-head) for every known worker before the branch-specific empty-state or gate-body content.
  - Emits escaped gate questions in `data-md` nodes for later dashboard markdown rendering through the sanitized client path.
  - Calls [render-answer-form](#render-answer-form) once per open gate, preserving both the selected workflow id and the gate file path in hidden fields for answer submission.
  - Calls [render-diff-disclosure](#render-diff-disclosure) once per gated worker after all gate blocks, not once per gate.
  - Emits no answer form or diff disclosure for unknown workers or known workers without open gates.

### render-detail-head

- sig: `_detail_head(wf: WorkflowContainer) -> str`
- abstract: false
- raises: none intentionally raised for live, finished, branchless, current-node-less, type-less, or exit-code-less workflow containers.
- returns: one HTML fragment string rooted at `<div class="detail-head">`.
- code: groom/groom/render.py::_detail_head
- summary: render the selected worker's non-interactive header row for the dashboard detail pane.
- verify: groom/tests/test_render.py::test_worker_detail_not_found_and_no_gate_states,
  groom/tests/test_render.py::test_exit_code_hint_only_on_finished_with_code
- args:
  - `wf`: required [workflow container](workflow-container.md) whose state, type, repository metadata, id, current node, and exit-code fields supply the header content.
- does:
  - Reads `state`, `workflow_type`, `repo_name`, `repo_branch`, `container_id`, `current_node`, and `exit_code` from the supplied workflow container.
  - Emits one `.detail-head` fragment containing the [workflow state dot](workflow-state-dot-renderer.md#method-render-workflow-state-dot) followed by the optional [workflow type badge](workflow-type-badge-renderer.md#method-render-workflow-type-badge).
  - Emits the escaped repository/branch label from [method-render-repository-label](../operator-inbox.md#method-render-repository-label) inside `.repo-branch`.
  - Emits `.meta` text containing `#` plus the first six characters of the escaped container id and the escaped workflow state value.
  - Emits ` · node {current_node}` inside `.meta` only when `current_node` is non-empty, escaping the current-node text before insertion.
  - Appends the [exit hint](../operator-inbox.md#method-render-exit-hint) after `.meta` only when that helper returns a non-empty finished-worker hint.
  - Uses the [HTML escape helper](html-escape-helper.md#method-escape-html-value) for the repository label, worker id prefix text, state value, and optional current-node text before those values enter HTML.
  - Does not add a role, accessible name, focusability, or keyboard behavior; the header is display-only context inside the already selected worker detail region.
  - Does not mutate workflow fields, gate records, registry membership, selected worker state, websocket queues, browser DOM state, sidecar state, Docker state, answer files, or gate files.

### render-answer-form

- sig: `_answer_form(wf: WorkflowContainer, file_path: str) -> str`
- abstract: false
- raises: none intentionally raised for empty, unsafe, quote-containing, or slash-containing workflow ids and gate file paths; values are escaped into attributes and submitted values remain caller data.
- returns: one websocket answer form fragment rooted at `<form class="answer" ws-send>`.
- code: groom/groom/render.py::_answer_form
- verify: groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form
- args:
  - `wf`: required [workflow container](workflow-container.md) whose `container_id` becomes the submitted `workflow_id` field.
  - `file_path`: required gate file path string that becomes the submitted `file_path` field.
- does:
  - Emits hidden input `cmd` with literal value `answer` so the dashboard websocket command handler recognizes the submitted frame.
  - Emits hidden input `workflow_id` with the escaped selected workflow container id.
  - Emits hidden input `file_path` with the escaped open gate file path.
  - Emits no explicit form action or form HTTP method; htmx's websocket extension owns form serialization because the root form carries `ws-send`.
  - Emits one multiline textarea named `answer`, placeholder text `Your answer…`, and `rows="4"`; it has no explicit label or `aria-label`, so the textbox lacks a durable accessible name.
  - Emits one `.answer-actions` wrapper containing one native submit button with class `btn`, type `submit`, and visible accessible name `Send answer`.
  - Leaves answer validation, websocket JSON serialization, gate lookup, gate-file writing, answer logging, dashboard broadcast, and answered-event dispatch to the dashboard websocket path.

### render-diff-disclosure

- sig: `_diff_disclosure(wf: WorkflowContainer) -> str`
- abstract: false
- raises: none intentionally raised for empty, unsafe, or quote-containing workflow ids; values are escaped into attributes.
- returns: one working-tree diff disclosure fragment rooted at `<details class="disclosure" data-diff="...">`.
- code: groom/groom/render.py::_diff_disclosure
- verify: groom/tests/test_render.py::test_worker_detail_has_one_diff_disclosure
- args:
  - `wf`: required [workflow container](workflow-container.md) whose `container_id` scopes the lazy diff request.
- does:
  - Emits one native `<details>` disclosure with class `disclosure` and `data-diff` set to the escaped workflow container id.
  - Emits one native `<summary>` with visible and accessible name `Working-tree diff`.
  - Emits one empty `<div class="diff-wrap" data-diff-target data-container="...">` body whose escaped `data-container` value becomes the lazy `GET /diff/{container_id}` target.
  - Emits no preloaded diff text, loading text, error text, open attribute, ARIA override, or nested form.
  - Performs no diff fetch, diff parsing, empty-state rendering, error rendering, or loaded-state caching; browser-side behavior owns those states after the operator expands the disclosure.
