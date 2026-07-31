---
type: screen
slug: groom-dashboard
title: groom dashboard
---
# groom dashboard

- code: groom/groom/app.py::index
- route: `/`; live-verified — selecting a run row, editing the answer textarea, and every activity-mode switch stay on this same landed path with no browser navigation.
- requires: none — the root route is unauthenticated and unguarded; groom serves the shell to anyone who can reach the port.
- params: none — the screen takes no path or query parameter. Everything it shows is chosen after load and held in the browser, never in the URL.
- entry: opened directly at the groom server's root URL. It is the only screen groom serves, so it is entered from outside in-app navigation and never linked to from another screen.
- verify: groom/tests/test_a11y_dynamic.py::test_runs_pane_with_an_open_gate_is_accessible
- verify: groom/tests/test_a11y_dynamic.py::test_the_activity_rail_is_reachable_and_operable_by_keyboard
- verify: groom/tests/test_dashboard_client.py::test_the_client_module_parses
- verify: groom/tests/test_projection.py::test_state_message_is_json_serializable
- vet: docs/specs/groom-dashboard/vet.md

The `groom` dashboard is the browser screen served by the [root dashboard endpoint](../../http/groom.md#get-root-dashboard-html). It is the operator console for the [runs fleet view](../../runs-fleet-view.md), the repository file browser, the working-tree diff view described by [changes view](../../changes-view.md), fleet telemetry, and the manual reconciliation controls for the discovered [workflow containers](../../concepts/workflow-container.md).

Nothing on either side of the wire is HTML. The endpoint ships a static shell — landmarks, live regions, overlays, and the ids the client mounts into — and every visible region is a Preact island rendered from JSON by `groom/groom/assets/dashboard.js`. The screen opens a browser websocket to `/ws` and receives fleet-wide [dashboard state payloads](../../dashboard-state-payload.md) on the server's clock; it subscribes that tab to the one run it has open and receives that run's detail pushed back to it alone; and it fetches per-selection panel data — repositories, files, diffs, traces — over HTTP, because those are one tab's choices and not fleet-wide facts. A socket `state` frame and the body of [GET /api/state](../../http/groom.md#get-dashboard-state) are the same JSON and go through the same apply function, so recovering from a dead socket is not a second rendering path that can rot unobserved.

The visible shell has five activity modes selected by the left activity rail: runs, files, diff, telemetry, and settings. The app starts in **runs** mode. It holds the selected run id, the selected `(container, repo)` pair, per-pane loading state, and transient overlay state for the repository picker and command palette in the [dashboard client store](../../concepts/dashboard-client-store.md), and keeps the source of truth for run rows and counts on the server. Selecting a row follows [select run row](#select-run-row), which marks one [run row](#run-row) current and fills `#detail` from [get run detail](../../http/groom.md#get-run-detail) and the tab's own watch subscription — without changing the active mode.

Connection state is its own visible fact. The [connection chip](#connection-chip) reports `live`, `stale`, `reconnecting`, or `offline`, derived by the [dashboard connection state machine](../../concepts/dashboard-connection-state-machine.md) from **message recency, not `readyState`** — a half-open socket reads OPEN forever and would otherwise show a green dot over a frozen fleet. Anything but `live` starts the [dashboard resync poller](../../concepts/dashboard-resync-poller.md) against `GET /api/state`.

## Layout

- app root: `.app[data-mode]`, connected to `WS /ws`; `data-mode` selects which pane is displayed. Inactive panes are `display:none`, so they are removed from the accessibility tree rather than merely hidden visually.
- activity rail: a left `<nav aria-label="Panels">` landmark with runs, files, diff, telemetry, and settings mode controls; selecting the gear follows [select activity settings mode](#select-activity-settings-mode).
- main region: a `<main id="main">` landmark holding all five panes, opened by the page's single `<h1>`, which is visually hidden but present because a screen reader has no title bar to read.
- runs pane: filter input, the live run list in `#runs-list`, and the open run's detail in `#detail`.
- files pane: repository picker, lazily loaded file tree, and selected-file viewer.
- diff pane: repository picker, lazily loaded changed-file tree, and selected-file diff viewer.
- telemetry pane: a four-field span filter and the fleet trace table with a per-run card strip above it.
- settings pane: manual container rescan and browser notification permission controls.
- status bar: fleet counts, repo/worker totals, the connection chip, the refresh control, and the command-palette open button.
- overlays: shared repository picker in `#repo-menu-wrap`, command palette in `#palette`, and the toast stack in `#toasts`.

## States

- mode: `runs` by default; `files`, `diff`, `telemetry`, and `settings` are mutually exclusive alternatives written to `.app[data-mode]` and to the store together.
- selected run: absent until a run row, palette result, or `j`/`k` row movement writes [dashboard selected worker state](../../dashboard-selected-worker-state.md). Selecting one clears the detail pane, sends this tab's watch subscription, and fetches `GET /worker/{container_id}` once.
- selected repository: absent until a repository menu item is chosen; choosing one writes [dashboard selected repository state](../../dashboard-selected-repository-state.md), updates both picker labels, and loads whichever of the files or diff panes is active.
- repository menu: closed by default with `#repo-menu-wrap` lacking `open`; opening positions it under the invoking picker, fetches `GET /repos`, clears the menu search, and focuses `#repo-search`; closing removes the `open` class, drops `aria-activedescendant`, and returns focus to the invoking picker.
- command palette: closed by default; `Ctrl+K` or `Meta+K` toggles it, and the status-bar button opens it. Opening clears its input, renders the current fleet from the store as results, and focuses `#palette-input`; while open, Tab is trapped on that input.
- discovery: `scanning` is true until the [startup background discovery scan](../../concepts/startup-background-discovery-scan.md) finishes; an empty fleet renders as `Discovering containers…` while it is, and as `No workhorse runs — nothing is running.` after.
- connection: `connecting` on load, then `live` while a frame has arrived within 15s, `stale` when the open socket has been silent longer, `reconnecting` for the first 60s after a close, and `offline` beyond that. Every phase but `live` polls `GET /api/state` on a 5s interval.
- live regions: `#runs-list` (`role="log"`), `#statusbar` and the chip inside it, `#detail`'s run header, and `#toasts` are the announcing regions. Each is a static shell element that an island renders *into*, so the region itself never re-renders and assistive tech keeps tracking the same node. Markdown gate questions are rendered through `marked` and sanitized by DOMPurify before they reach `innerHTML`.

## Components

### activity-rail

- selector: `#activitybar`
- role: navigation
- name: `Panels`
- keyboard: not focusable itself; Tab moves through the five mode buttons it contains, in DOM order.
- parent: [groom dashboard](#groom-dashboard)
- states: static. It is shell markup, never re-rendered; only the `active` class and `aria-pressed` on its buttons change.
- dom: a `<nav>` rather than a `role="toolbar"` div — switching panes *is* this page's navigation, and a toolbar is not a landmark, so its contents would otherwise sit outside every region.
- code: groom/groom/templates/dashboard.html
- verify: groom/tests/test_a11y_dynamic.py::test_the_activity_rail_is_reachable_and_operable_by_keyboard
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-activity-rail.png

### main-region

- selector: `#main`
- role: main
- name: none
- keyboard: not focusable; a landmark, not a control.
- parent: [groom dashboard](#groom-dashboard)
- states: always present; its visible child is whichever pane `.app[data-mode]` selects.
- dom: holds all five panes as siblings. The four inactive ones are `display:none`, so exactly one pane's controls are in the accessibility tree at a time.
- code: groom/groom/templates/dashboard.html
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-main-region.png

### page-heading

- selector: `#main > h1.sr-only`
- role: heading
- name: `groom — workhorse fleet dashboard`
- keyboard: not focusable.
- parent: [main-region](#main-region)
- states: static.
- dom: visually hidden and always rendered. It is the page's one `h1`; without it the document outline would start at `h2` and a screen reader would have nothing to announce the page as.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-page-heading.png

### activity-runs-mode

- selector: `.act-btn[data-mode="runs"]`
- role: button
- name: `Runs`
- keyboard: natively focusable with Tab and Shift+Tab; Enter or Space activates the mode switch.
- parent: [activity-rail](#activity-rail)
- states: active by default, with the `active` class and `aria-pressed="true"`; inactive with `aria-pressed="false"` in any other mode.
- code: groom/groom/assets/dashboard.js::setMode
- props:
  - `data-mode`: literal `runs`; required; the mode value the delegated rail handler passes to the mode switch.
  - `title`: literal `Runs`; required; tooltip text only.
  - `aria-label`: literal `Runs`; required; the durable accessible name for this icon-only button.
  - `aria-pressed`: `true` or `false`; required; recomputed for every rail button on each mode switch.
- dom: icon-only native `<button type="button">` inside the `#activitybar` nav, first of the five; contains only an inline `aria-hidden="true"` SVG and no text node.
- leads-to: [select activity runs mode](#select-activity-runs-mode), which shows the runs pane containing the [runs live region](#runs-live-region) and the open run's detail.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-activity-runs-mode.png

### activity-files-mode

- selector: `.act-btn[data-mode="files"]`
- role: button
- name: `Files`
- keyboard: natively focusable with Tab and Shift+Tab; Enter or Space activates the mode switch.
- parent: [activity-rail](#activity-rail)
- states: inactive with `aria-pressed="false"` in runs, diff, telemetry, or settings mode; active with the `active` class and `aria-pressed="true"` when `.app` has `data-mode="files"`.
- code: groom/groom/assets/dashboard.js::setMode
- dom: icon-only native `<button type="button">`, second in the rail; an inline `aria-hidden` folder SVG and no text node.
- leads-to: [select activity files mode](#select-activity-files-mode), which shows the files pane containing the [files repository picker button](#files-repository-picker-button), `#files-tree`, and `#file-view`.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-activity-files-mode.png

### activity-diff-mode

- selector: `.act-btn[data-mode="diff"]`
- role: button
- name: `Diff`
- keyboard: natively focusable with Tab and Shift+Tab; Enter or Space activates the mode switch.
- parent: [activity-rail](#activity-rail)
- states: inactive with `aria-pressed="false"` in runs, files, telemetry, or settings mode; active with the `active` class and `aria-pressed="true"` when `.app` has `data-mode="diff"`.
- code: groom/groom/assets/dashboard.js::setMode
- dom: icon-only native `<button type="button">`, third in the rail; an inline `aria-hidden` bidirectional-arrows SVG and no text node.
- leads-to: [select activity diff mode](#select-activity-diff-mode), which shows the diff pane containing the [diff repository picker button](#diff-repository-picker-button), `#diff-tree`, and `#diff-view`.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-activity-diff-mode.png

### activity-telemetry-mode

- selector: `.act-btn[data-mode="telemetry"]`
- role: button
- name: `Telemetry`
- keyboard: natively focusable with Tab and Shift+Tab; Enter or Space activates the mode switch.
- parent: [activity-rail](#activity-rail)
- states: inactive with `aria-pressed="false"` in runs, files, diff, or settings mode; active with the `active` class and `aria-pressed="true"` when `.app` has `data-mode="telemetry"`.
- code: groom/groom/assets/dashboard.js::setMode
- dom: icon-only native `<button type="button">`, fourth in the rail and the last before the spacer; an inline `aria-hidden` sparkline SVG and no text node.
- leads-to: [select activity telemetry mode](#select-activity-telemetry-mode), which shows the telemetry pane containing the span filter and [telemetry traces table](#telemetry-traces-table).
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-activity-telemetry-mode.png

### activity-settings-mode

- selector: `.act-btn[data-mode="settings"]`
- role: button
- name: `Settings`
- keyboard: natively focusable with Tab and Shift+Tab; Enter or Space activates the mode switch.
- parent: [activity-rail](#activity-rail)
- states: inactive with `aria-pressed="false"` in runs, files, diff, or telemetry mode; active with the `active` class and `aria-pressed="true"` when `.app` has `data-mode="settings"`.
- code: groom/groom/assets/dashboard.js::setMode
- dom: icon-only native `<button type="button">` after the rail spacer, at the bottom of the rail; an inline `aria-hidden` gear SVG and no text node.
- leads-to: [select activity settings mode](#select-activity-settings-mode), which shows the settings pane containing the [settings rescan button](#settings-rescan-button) and [settings enable notifications button](#settings-enable-notifications-button).
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-activity-settings-mode.png

### runs-filter-input

- selector: `#runs .pane-head input.filter[name="q"]`
- role: searchbox
- name: `Filter runs`
- keyboard: natively focusable with Tab; typing filters as you type; the browser's own search-input clear affordance is available.
- parent: [groom dashboard](#groom-dashboard)
- states: empty by default, showing the whole pushed fleet; non-empty, showing only rows whose haystack contains the query, case-insensitively.
- code: groom/groom/assets/dashboard.js::wireEvents
- code: groom/groom/assets/dashboard.js::rowHaystack
- props:
  - `type`: literal `search`; required; supplies the searchbox role.
  - `name`: literal `q`; required; the field name, retained for form semantics though nothing submits it.
  - `aria-label`: literal `Filter runs`; required; the accessible name — the pane header text is not associated with the input.
  - `placeholder`: literal `Filter runs…`; presentation only.
- dom: shell markup in the runs pane header, beside the `Runs — live & blocked` label. It is never re-rendered, so its value survives every 5s push.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-runs-filter-input.png

### runs-live-region

- selector: `#runs-list`
- role: log
- name: `Workhorse runs`
- keyboard: not focusable itself; Tab reaches the run rows inside it, and `j`/`k` move the selection without focus leaving the document body.
- parent: [groom dashboard](#groom-dashboard)
- states: `Discovering containers…` while the startup scan runs and nothing has been found; `No workhorse runs — nothing is running.` when the fleet is empty and the scan is done; otherwise one [run row](#run-row) per matching run.
- code: groom/groom/assets/dashboard.js::Fleet
- verify: groom/tests/test_projection.py::test_fleet_rows_include_every_instance
- verify: groom/tests/test_projection.py::test_query_filters_the_fleet
- dom: a shell `<div>` carrying `role="log"`, `aria-live="polite"`, and its label. The Preact island renders *into* it, so the region node itself is never replaced and assistive tech keeps tracking one region across every push.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-runs-live-region.png

### run-row

- selector: `#runs-list .row[data-worker-id]`
- role: button
- name: `{repo} #{short_handle} {liveness} {doing}`
- keyboard: natively focusable with Tab; Enter or Space selects the run. `j` and `k` move the selection down and up from anywhere that is not a text field.
- parent: [runs-live-region](#runs-live-region)
- states: blocked rows carry the `blocked` class; the open row carries `selected` and `aria-current="true"`, and every other row omits `aria-current` entirely rather than setting it to `"false"`.
- code: groom/groom/assets/dashboard.js::RunRow
- verify: groom/tests/test_projection.py::test_fleet_rows_order_blocked_then_live_then_dead_then_finished
- verify: groom/tests/test_projection.py::test_run_message_row_matches_the_same_row_in_the_state_message
- props:
  - `data-worker-id`: the [workflow container](../../concepts/workflow-container.md) id; required; read by the delegated click handler and by `j`/`k` row movement, which walks the rendered rows.
  - `data-state`: one of `blocked`, `running`, `idle`, `finished`; required; styling and row-navigation metadata.
  - `data-live`: the liveness class from the projection; required; may be the unknown value when no telemetry has arrived.
  - `aria-current`: `true` on the open row only; absent otherwise.
- dom: a native `<button type="button">`, keyed by run id so a push preserves focus and scroll. Two lines plus an optional question preview: line one is a state dot, a type badge, the repository label, the short handle, and an optional pulse label; line two is the activity text and an optional mini note; the third line, when present, is the [run question preview](../../concepts/run-question-preview.md).
- leads-to: [select run row](#select-run-row), which opens that run in the detail pane without leaving this screen.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-run-row.png

### detail-pane

- selector: `#detail`
- role: none
- name: none
- keyboard: not focusable itself; contains the answer form and the diff disclosure.
- parent: [groom dashboard](#groom-dashboard)
- states: `Select a run to see its activity, answer its gate, and read its metrics and logs.` with nothing selected; `Loading…` between a selection and its first payload; `Run not found.` for an id the server does not know; otherwise the run header, gate blocks or a no-gate note, metrics, logs, and the diff disclosure.
- code: groom/groom/assets/dashboard.js::Detail
- verify: groom/tests/test_projection.py::test_run_detail_carries_gates_head_metrics_and_logs
- dom: a shell `<div>` the detail island renders into. It is refreshed by pushed `detail` frames for the watched run, not by re-fetching.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-detail-pane.png

### detail-run-header

- selector: `#detail .detail-head`
- role: status
- name: `Selected run`
- keyboard: not focusable.
- parent: [detail-pane](#detail-pane)
- states: shows a state dot, type badge, repository label, an optional pulse label, the meta line (`#handle · state · node · pid`), an optional exit hint for a finished run, and an optional current-activity line.
- code: groom/groom/assets/dashboard.js::RunHead
- verify: groom/tests/test_projection.py::test_exit_hint_only_on_finished_with_a_code
- dom: one of three `role="status"` regions on this page. Each carries its own `aria-label` — this one, the [status bar region](#statusbar-region), and the [connection chip](#connection-chip) — so a screen reader and `getByRole` can tell them apart.
- screenshot: docs/specs/groom-dashboard/vet/run-detail-detail-run-header.png

### detail-gate-question

- selector: `#detail .gate-block .question`
- role: none
- name: none
- keyboard: not focusable; rendered prose.
- parent: [detail-pane](#detail-pane)
- states: one block per open gate, keyed by gate file path; absent for a run with no open gate, which instead renders a note naming the run's state and node.
- code: groom/groom/assets/dashboard.js::GateBlock
- code: groom/groom/assets/dashboard.js::Markdown
- verify: groom/tests/test_projection.py::test_gate_question_travels_as_data_not_markup
- dom: the gate's question travels as data, never as markup. The client renders it with `marked` and sanitizes the result with DOMPurify before it reaches `innerHTML`; the gate's file path is shown above it as a plain text node.
- screenshot: docs/specs/groom-dashboard/vet/run-detail-detail-gate-question.png

### detail-answer-textarea

- selector: `#detail form[data-answer] textarea[name="answer"]`
- role: textbox
- name: `Your answer`
- keyboard: natively focusable with Tab; multi-line text entry; Enter inserts a newline rather than submitting.
- parent: [detail-pane](#detail-pane)
- states: empty on render; cleared only after a successfully sent answer, so a rejected send leaves the text in the box.
- code: groom/groom/assets/dashboard.js::AnswerForm
- verify: groom/tests/test_a11y_dynamic.py::test_the_answer_form_is_reachable_and_submittable_by_keyboard
- dom: four rows, inside a form carrying hidden `cmd`, `workflow_id`, and `file_path` fields. The form is re-rendered on every 5s push, but the gate block is keyed by file path, so Preact reuses the same `<textarea>` DOM node and a half-typed answer survives.
- screenshot: docs/specs/groom-dashboard/vet/run-detail-detail-answer-textarea.png

### detail-send-answer-button

- selector: `#detail form[data-answer] button[type="submit"]`
- role: button
- name: `Send answer`
- keyboard: natively focusable with Tab; Enter or Space submits the form, as does Enter from any single-line field in it.
- parent: [detail-pane](#detail-pane)
- states: always enabled. The result is reported by a toast, not by a disabled state.
- code: groom/groom/assets/dashboard.js::AnswerForm
- leads-to: [send detail answer](#send-detail-answer), which serializes the form and sends it over the dashboard websocket.
- screenshot: docs/specs/groom-dashboard/vet/run-detail-detail-send-answer-button.png

### detail-working-tree-diff-toggle

- selector: `#detail details.disclosure > summary`
- role: button
- name: `Working-tree diff`
- keyboard: natively focusable with Tab; Enter or Space toggles the disclosure.
- parent: [detail-pane](#detail-pane)
- states: collapsed on render; the first expansion fetches the diff and shows `Loading diff…`, then either the rendered diff, `(no changes)`, or `failed to load diff`. Re-collapsing and re-expanding does not re-fetch.
- code: groom/groom/assets/dashboard.js::DiffDisclosure
- dom: a native `<details>`/`<summary>` pair, keyed by run id so switching runs resets the disclosure rather than showing the previous run's diff.
- leads-to: [toggle detail working tree diff](#toggle-detail-working-tree-diff), which lazily loads that run's [workspace diff data](../../workspace-diff-data.md).
- screenshot: docs/specs/groom-dashboard/vet/run-detail-detail-working-tree-diff-toggle.png

### detail-metrics-grid

- selector: `#detail .live-sec .metrics-grid`
- role: none
- name: none
- keyboard: not focusable.
- parent: [detail-pane](#detail-pane)
- states: `No telemetry for this run — it is either pre-OTel or exporting to another collector.` when the run has none; otherwise a grid of key/value cells in the projection's order, followed by an optional footer of fired alert-rule chips and the run directory.
- code: groom/groom/assets/dashboard.js::Metrics
- verify: groom/tests/test_projection.py::test_run_metrics_cell_order_is_the_layout
- verify: groom/tests/test_projection.py::test_run_metrics_merges_hot_cache_and_durable_facts

### detail-log-trail

- selector: `#detail .live-sec .log-line`
- role: none
- name: none
- keyboard: not focusable.
- parent: [detail-pane](#detail-pane)
- states: `No log lines for this run (workhorse ships in-process script logs over OTLP).` when empty; otherwise capped, newest-first lines, each a timestamp, severity, node, and body.
- code: groom/groom/assets/dashboard.js::LogTrail
- verify: groom/tests/test_projection.py::test_log_trail_newest_first_with_severity_classes
- verify: groom/tests/test_projection.py::test_log_trail_is_capped

### files-repository-picker-button

- selector: `#files-pane .repo-picker[data-picker="files"]`
- role: button
- name: `Select container / repo…`
- keyboard: natively focusable with Tab; Enter or Space toggles the shared repository menu.
- parent: [groom dashboard](#groom-dashboard)
- exclusive-with: [diff-repository-picker-button](#diff-repository-picker-button)
- states: label text is replaced on both pickers whenever a repository is chosen, so the two never disagree.
- code: groom/groom/assets/dashboard.js::openRepoMenu
- code: groom/groom/assets/dashboard.js::wireEvents
- dom: the two pickers are identical controls in two panes. Only one pane is in the DOM's accessibility tree at a time — the inactive pane is `display:none` — which is why they can share a computed name without being ambiguous.
- leads-to: [open files repository picker](#open-files-repository-picker), which opens the shared menu below this button.
- screenshot: docs/specs/groom-dashboard/vet/files-files-repository-picker-button.png

### diff-repository-picker-button

- selector: `#diff-pane .repo-picker[data-picker="diff"]`
- role: button
- name: `Select container / repo…`
- keyboard: natively focusable with Tab; Enter or Space toggles the shared repository menu.
- parent: [groom dashboard](#groom-dashboard)
- exclusive-with: [files-repository-picker-button](#files-repository-picker-button)
- states: identical to the files picker; both labels are written together by the repository selector.
- code: groom/groom/assets/dashboard.js::openRepoMenu
- code: groom/groom/assets/dashboard.js::wireEvents
- leads-to: [open diff repository picker](#open-diff-repository-picker), which opens the shared menu below this button.
- screenshot: docs/specs/groom-dashboard/vet/diff-diff-repository-picker-button.png

### repository-menu-search-input

- selector: `#repo-search`
- role: combobox
- name: `Search container / repo`
- keyboard: focused automatically when the menu opens; ArrowDown and ArrowUp move the active option, Enter chooses it, Escape closes the menu and returns focus to the invoking picker.
- parent: [groom dashboard](#groom-dashboard)
- states: `aria-expanded` is `true` while the menu is open and `false` otherwise; `aria-activedescendant` points at the active option's id while one exists and is removed when the filtered list is empty or the menu closes. The value is cleared on every open.
- code: groom/groom/assets/dashboard.js::openRepoMenu
- code: groom/groom/assets/dashboard.js::closeRepoMenu
- code: groom/groom/assets/dashboard.js::RepoMenu
- props:
  - `role`: literal `combobox`; required.
  - `aria-controls`: literal `repo-menu`; required; associates the input with the listbox it drives.
  - `aria-autocomplete`: literal `list`; required.
  - `aria-expanded`: `true` or `false`; required; toggled by the open and close handlers.
  - `aria-activedescendant`: `repo-opt-{index}`; present only while an active option exists. It is published by the menu island rather than by the keyboard handler, because that is the one place that knows which row ended up where.
- screenshot: docs/specs/groom-dashboard/vet/repository-menu-repository-menu-search-input.png

### repository-menu-listbox

- selector: `#repo-menu`
- role: listbox
- name: `Containers and repositories`
- keyboard: not focusable itself; driven entirely from the search input via `aria-activedescendant`.
- parent: [groom dashboard](#groom-dashboard)
- states: `Loading…` while the fetch is in flight; `No repositories available.` when the response is empty or the search matches nothing; otherwise one option per repository, grouped per container by the server and flattened for the keyboard.
- code: groom/groom/assets/dashboard.js::RepoMenu
- dom: a shell `<div>` the menu island renders into, positioned under whichever picker invoked it.
- screenshot: docs/specs/groom-dashboard/vet/repository-menu-repository-menu-listbox.png

### repository-menu-option

- selector: `#repo-menu .repo-item[role="option"]`
- role: option
- name: `{container} / {repo}`
- keyboard: not individually focusable; reached with ArrowDown and ArrowUp from the search input and chosen with Enter. Pointer click selects it directly.
- parent: [repository-menu-listbox](#repository-menu-listbox)
- states: `aria-selected="true"` on the active option and `"false"` on the rest; the active option is scrolled into view on each render.
- code: groom/groom/assets/dashboard.js::RepoMenu
- code: groom/groom/assets/dashboard.js::repoItems
- props:
  - `id`: `repo-opt-{index}`; required; the target of the search input's `aria-activedescendant`.
  - `data-container`: the container id; required.
  - `data-repo`: the repository path, possibly empty for the container's own checkout; required.
  - `data-label`: the display label; required.
- dom: keyed by `container/repo`, so filtering re-uses rows rather than recreating them. Filtering is done by rebuilding the list, not by hiding rows with inline styles — a hidden row would still be in the accessibility tree.
- leads-to: [select repository menu option](#select-repository-menu-option), which sets the selected repository and loads the active pane.
- screenshot: docs/specs/groom-dashboard/vet/repository-menu-repository-menu-option.png

### files-directory-toggle

- selector: `#files-tree .tree-dir-head`
- role: button
- name: `{directory}`
- keyboard: natively focusable with Tab; Enter or Space collapses and expands the directory.
- parent: [groom dashboard](#groom-dashboard)
- exclusive-with: [diff-directory-toggle](#diff-directory-toggle)
- states: expanded by default with `aria-expanded="true"`; collapsed with `aria-expanded="false"` and the `collapsed` class on its wrapper. The collapse state is component-local and survives a re-render because the node is keyed by name; it is deliberately not in the store, since nothing else reads it.
- code: groom/groom/assets/dashboard.js::TreeDir
- code: groom/groom/assets/dashboard.js::buildTree
- dom: a native `<button type="button">` with an `aria-hidden` chevron; the nesting is a pure function of the flat path list the server sends, computed by the [dashboard tree builder](../../concepts/dashboard-tree-builder.md).
- leads-to: [toggle files directory](#toggle-files-directory).
- screenshot: docs/specs/groom-dashboard/vet/files-files-directory-toggle.png

### files-file-row

- selector: `#files-tree button.tree-file`
- role: button
- name: `{filename}`
- keyboard: natively focusable with Tab; Enter or Space opens the file in the viewer.
- parent: [groom dashboard](#groom-dashboard)
- exclusive-with: [diff-file-row](#diff-file-row)
- states: the open file's row carries the `active` class and `aria-current="true"`; every other row omits `aria-current`.
- code: groom/groom/assets/dashboard.js::FilesTree
- dom: a native `<button type="button">` keyed by full path, holding only the base name. The full path is closed over by the click handler rather than written to a data attribute.
- leads-to: [select files file row](#select-files-file-row), which fetches that file's [workspace file content data](../../workspace-file-content-data.md).
- screenshot: docs/specs/groom-dashboard/vet/files-files-file-row.png

### file-view-region

- selector: `#file-view`
- role: none
- name: none
- keyboard: not focusable; the code block is selectable text.
- parent: [groom dashboard](#groom-dashboard)
- states: `Select a file to view it.` when idle; `Loading…` in flight; `failed to load` on rejection; `(empty or binary file)` under the path header when the content is empty; otherwise the path header and the highlighted source.
- code: groom/groom/assets/dashboard.js::FileView
- code: groom/groom/assets/dashboard.js::highlight
- dom: highlighting is applied by highlight.js, whose output is escaped HTML; when the library is absent or throws, the content is rendered as a plain text node instead. The language comes from the server so the extension table lives next to the rest of the presentation policy.
- screenshot: docs/specs/groom-dashboard/vet/files-file-view-region.png

### diff-directory-toggle

- selector: `#diff-tree .tree-dir-head`
- role: button
- name: `{directory}`
- keyboard: natively focusable with Tab; Enter or Space collapses and expands the directory.
- parent: [groom dashboard](#groom-dashboard)
- exclusive-with: [files-directory-toggle](#files-directory-toggle)
- states: expanded by default with `aria-expanded="true"`; collapsed with `aria-expanded="false"`. Same component as the files tree uses, over the changed-file list put through the same [dashboard tree builder](../../concepts/dashboard-tree-builder.md).
- code: groom/groom/assets/dashboard.js::TreeDir
- leads-to: [toggle diff directory](#toggle-diff-directory).
- screenshot: docs/specs/groom-dashboard/vet/diff-diff-directory-toggle.png

### diff-file-row

- selector: `#diff-tree button.tree-file`
- role: button
- name: `{filename} +{added} -{deleted}`
- keyboard: natively focusable with Tab; Enter or Space shows that file's diff.
- parent: [groom dashboard](#groom-dashboard)
- exclusive-with: [files-file-row](#files-file-row)
- states: the shown file's row carries the `active` class and `aria-current="true"`; every other row omits `aria-current`.
- code: groom/groom/assets/dashboard.js::DiffTree
- dom: keyed by its index into the [dashboard parsed diff file cache](../../dashboard-parsed-diff-file-cache.md); the index is closed over by the click handler rather than written to a data attribute. A file added or deleted in the diff is addressed by its non-`/dev/null` name.
- leads-to: [select diff file row](#select-diff-file-row).
- screenshot: docs/specs/groom-dashboard/vet/diff-diff-file-row.png

### diff-view-region

- selector: `#diff-view`
- role: none
- name: none
- keyboard: not focusable; the rendered diff is selectable text.
- parent: [groom dashboard](#groom-dashboard)
- states: `Select a changed file to see its diff.` until a changed file is chosen; otherwise that one file's rendered diff.
- code: groom/groom/assets/dashboard.js::DiffView
- code: groom/groom/assets/dashboard.js::diffMarkup
- dom: diff2html both parses the unified text and renders it, and escapes what it emits — which is why the raw diff rides the wire unsplit rather than having half a parser reimplemented server-side.
- screenshot: docs/specs/groom-dashboard/vet/diff-diff-view-region.png

### telemetry-run-filter-input

- selector: `#traces-filter input[name="run"]`
- role: searchbox
- name: `Filter by run id`
- keyboard: natively focusable with Tab; typing re-queries.
- parent: [groom dashboard](#groom-dashboard)
- states: empty by default; any value narrows the query to matching run ids.
- code: groom/groom/assets/dashboard.js::loadTraces
- screenshot: docs/specs/groom-dashboard/vet/telemetry-telemetry-run-filter-input.png

### telemetry-node-filter-input

- selector: `#traces-filter input[name="node"]`
- role: searchbox
- name: `Filter by node`
- keyboard: natively focusable with Tab; typing re-queries.
- parent: [groom dashboard](#groom-dashboard)
- states: empty by default; any value narrows the query to matching workflow nodes.
- code: groom/groom/assets/dashboard.js::loadTraces
- screenshot: docs/specs/groom-dashboard/vet/telemetry-telemetry-node-filter-input.png

### telemetry-status-filter-select

- selector: `#traces-filter select[name="status"]`
- role: combobox
- name: `Filter by span status`
- keyboard: natively focusable with Tab; ArrowUp and ArrowDown or typing choose an option; changing the value re-queries.
- parent: [groom dashboard](#groom-dashboard)
- states: `any status` by default, with an empty value; `ERROR`, `OK`, and `UNSET` are the alternatives.
- code: groom/groom/assets/dashboard.js::loadTraces
- dom: a native single-select `<select>`, which computes to `combobox` — not `listbox` — because it is closed and shows one value at a time.
- screenshot: docs/specs/groom-dashboard/vet/telemetry-telemetry-status-filter-select.png

### telemetry-slower-than-input

- selector: `#traces-filter input[name="slower_than"]`
- role: searchbox
- name: `Minimum duration in seconds`
- keyboard: natively focusable with Tab; typing re-queries.
- parent: [groom dashboard](#groom-dashboard)
- states: empty by default; a numeric value drops spans faster than that many seconds.
- code: groom/groom/assets/dashboard.js::loadTraces
- screenshot: docs/specs/groom-dashboard/vet/telemetry-telemetry-slower-than-input.png

### telemetry-show-ended-checkbox

- selector: `#traces-filter input[name="show_ended"]`
- role: checkbox
- name: `show ended`
- keyboard: natively focusable with Tab; Space toggles it, which re-queries.
- parent: [groom dashboard](#groom-dashboard)
- states: unchecked by default, which is the connected-runs-only view; checked sends `show_ended=1` and the pane also shows runs that have finished or gone silent.
- code: groom/groom/assets/dashboard.js::loadTraces
- dom: a native `<input type="checkbox">` inside its own `<label>`, so the visible text is the accessible name and clicking the text toggles it. Unchecked, the field is simply absent from the serialized form — which is the same thing an omitted query parameter means to the server, so the default view needs no client-side special case.

### telemetry-traces-table

- selector: `#traces-list table.traces`
- role: table
- name: none
- keyboard: not focusable; the cells are selectable text.
- parent: [groom dashboard](#groom-dashboard)
- states: `No telemetry yet.` before the first query; `failed to load` on rejection; `No run is connected right now. Tick show ended to read the runs that already finished.` when the connected-only view is empty; a run-card strip with `No spans match — …` when runs are known but no span matches; otherwise the strip plus a six-column table of started, run, node, span, duration, and status.
- code: groom/groom/assets/dashboard.js::Traces
- code: groom/groom/assets/dashboard.js::RunCard
- dom: a real `<table>` with a `<thead>` row of `<th>` cells, so the columns are announced as headers rather than as a grid of unlabelled text. Rows with an `ERROR` status carry an extra class on the status cell only.
- screenshot: docs/specs/groom-dashboard/vet/telemetry-telemetry-traces-table.png

### settings-rescan-button

- selector: `#btn-refresh`
- role: button
- name: `Rescan containers`
- keyboard: natively focusable with Tab; Enter or Space triggers the rescan.
- parent: [groom dashboard](#groom-dashboard)
- states: idle; while a rescan is in flight it carries `data-busy` and the `spinning` class, and further activations are ignored until the request settles.
- code: groom/groom/assets/dashboard.js::doRefresh
- dom: a text button in the settings pane, beside the explanatory line `Re-run the docker discovery pass.`
- leads-to: [rescan containers from settings](#rescan-containers-from-settings).
- screenshot: docs/specs/groom-dashboard/vet/settings-settings-rescan-button.png

### settings-enable-notifications-button

- selector: `#btn-notify`
- role: button
- name: `Enable notifications`
- keyboard: natively focusable with Tab; Enter or Space requests the browser permission.
- parent: [groom dashboard](#groom-dashboard)
- states: static — the label does not change with the permission state; the browser owns the prompt and the answer.
- code: groom/groom/assets/dashboard.js::wireEvents
- dom: a ghost button in the settings pane, beside `Browser alerts when a worker blocks.`
- leads-to: [enable browser notifications from settings](#enable-browser-notifications-from-settings), which asks for [browser notification permission](../../concepts/browser-notification-permission.md).
- screenshot: docs/specs/groom-dashboard/vet/settings-settings-enable-notifications-button.png

### statusbar-region

- selector: `#statusbar`
- role: status
- name: `Fleet status`
- keyboard: not focusable itself; contains the refresh and palette buttons.
- parent: [groom dashboard](#groom-dashboard)
- states: four state counts in the order blocked, running, idle, finished, then the repo and worker totals, the connection chip, the refresh control, and the palette button.
- code: groom/groom/assets/dashboard.js::StatusBar
- verify: groom/tests/test_projection.py::test_status_bar_counts_states
- dom: a shell `<div>` with `role="status"`, `aria-live="polite"`, and its own `aria-label`. It is one of three `role="status"` regions on this page; each is named so they are distinguishable.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-statusbar-region.png

### connection-chip

- selector: `#statusbar .stat.conn`
- role: status
- name: `Connection: ` followed by the current phase word — `live`, `stale`, `reconnecting`, or `offline`.
- keyboard: not focusable; it is a report, not a control.
- parent: [statusbar-region](#statusbar-region)
- states: `live` while a frame has arrived within the last 15 seconds; `stale` when the socket is open but has been silent longer; `reconnecting` for the first 60 seconds after the socket closes, while backoff is in flight; `offline` beyond that. `connecting` is the value the store starts with, before the first evaluation.
- code: groom/groom/assets/dashboard.js::ConnectionChip
- code: groom/groom/assets/dashboard.js::deriveConnection
- verify: groom/tests/test_connection_state.py::test_the_full_live_to_stale_to_offline_progression
- verify: groom/tests/test_connection_state.py::test_open_but_silent_socket_goes_stale_and_starts_resyncing
- props:
  - `data-conn`: the phase word; required; the only styling hook, so the four states differ visually as well as in their name.
  - `role`: literal `status`; required; the phase changing is exactly the kind of thing that should be announced, and it changes independently of the counts beside it.
  - `aria-label`: `Connection: {phase}`; required; the word is the accessible name and the dot is `aria-hidden`, so a degraded socket does not depend on colour to be legible.
  - `title`: one of four sentences explaining the phase — that updates are live, that the socket has gone quiet and polling has taken over, that it dropped and is reconnecting, or that there is no socket at all.
- dom: derived from message recency, **not** from `readyState`. A half-open TCP socket reads OPEN forever and will never deliver another frame; the server ticks every `GROOM_LIVE_TICK_S` whether or not anything changed, so silence is information. The phase is computed by the [dashboard connection state machine](../../concepts/dashboard-connection-state-machine.md), and every phase but `live` runs the [dashboard resync poller](../../concepts/dashboard-resync-poller.md).
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-connection-chip.png

### statusbar-refresh-button

- selector: `#btn-refresh-bar`
- role: button
- name: `Rescan containers (reconcile + prune)`
- keyboard: natively focusable with Tab; Enter or Space triggers the rescan.
- parent: [statusbar-region](#statusbar-region)
- states: idle; `data-busy` and the `spinning` class while a rescan is in flight, during which further activations are ignored.
- code: groom/groom/assets/dashboard.js::doRefresh
- dom: an icon-only button holding an `aria-hidden` glyph, named longer than the settings-pane control it duplicates so the two are distinguishable when settings mode puts both on screen at once.
- leads-to: [rescan containers from statusbar](#rescan-containers-from-statusbar).
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-statusbar-refresh-button.png

### command-palette-open-button

- selector: `#btn-palette`
- role: button
- name: `Open command palette`
- keyboard: natively focusable with Tab; Enter or Space opens the palette. `Ctrl+K` or `Meta+K` opens it from anywhere on the page.
- parent: [statusbar-region](#statusbar-region)
- states: static. Opening records the invoker so focus returns here on close.
- code: groom/groom/assets/dashboard.js::openPalette
- dom: shows the `⌘K` hint as an `aria-hidden` glyph beside the word `palette`; the accessible name comes from `aria-label` so the shortcut glyph is never read out as text.
- leads-to: [toggle command palette shortcut](#toggle-command-palette-shortcut).
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-command-palette-open-button.png

### command-palette-dialog

- selector: `#palette`
- role: dialog
- name: `Command palette`
- keyboard: Escape closes it; while it is open Tab is trapped on its input, which is its only focusable element.
- parent: [groom dashboard](#groom-dashboard)
- states: closed by default; `open` on the wrapper while shown. Closing returns focus to whatever opened it rather than dropping it to `<body>`.
- code: groom/groom/assets/dashboard.js::openPalette
- code: groom/groom/assets/dashboard.js::closePalette
- dom: `aria-modal="true"`. The trap is one element wide on purpose — there is nothing else in the dialog to reach.
- screenshot: docs/specs/groom-dashboard/vet/command-palette-command-palette-dialog.png

### command-palette-input

- selector: `#palette-input`
- role: combobox
- name: `Jump to a worker or blocked gate`
- keyboard: focused automatically on open; ArrowDown and ArrowUp move the active result, Enter chooses it, Escape closes the palette.
- parent: [command-palette-dialog](#command-palette-dialog)
- states: cleared on every open; `aria-expanded` tracks the palette's open state; `aria-activedescendant` points at the active result and is removed when nothing matches.
- code: groom/groom/assets/dashboard.js::PaletteResults
- code: groom/groom/assets/dashboard.js::movePaletteActive
- screenshot: docs/specs/groom-dashboard/vet/command-palette-command-palette-input.png

### command-palette-results-listbox

- selector: `#palette-results`
- role: listbox
- name: `Workers`
- keyboard: not focusable itself; driven from the palette input via `aria-activedescendant`.
- parent: [command-palette-dialog](#command-palette-dialog)
- states: every run in the fleet when the query is empty; the matching subset otherwise; empty when nothing matches.
- code: groom/groom/assets/dashboard.js::PaletteResults
- screenshot: docs/specs/groom-dashboard/vet/command-palette-command-palette-results-listbox.png

### command-palette-result

- selector: `#palette-results .presult[role="option"]`
- role: option
- name: `{repo} #{short_handle} {doing} {hint}`
- keyboard: not individually focusable; reached with ArrowDown and ArrowUp and chosen with Enter. Pointer click chooses it directly.
- parent: [command-palette-results-listbox](#command-palette-results-listbox)
- states: `aria-selected="true"` on the active result and `"false"` on the rest; the active result is scrolled into view on each render.
- code: groom/groom/assets/dashboard.js::PaletteResults
- code: groom/groom/assets/dashboard.js::paletteHits
- props:
  - `id`: `presult-{index}`; required; the target of the palette input's `aria-activedescendant`.
- dom: keyed by run id. The hit list is computed from the fleet **in the store**, not from the rendered rows, so the palette finds a run the runs-pane filter is currently hiding.
- leads-to: [select command palette result](#select-command-palette-result).
- screenshot: docs/specs/groom-dashboard/vet/command-palette-command-palette-result.png

### toast-region

- selector: `#toasts`
- role: alert
- name: none
- keyboard: not focusable; toasts are not dismissible by hand and expire on their own.
- parent: [groom dashboard](#groom-dashboard)
- states: empty most of the time; one entry per blocked notification or answer confirmation, removed on its own timer — seven seconds for a block, three and a half for a confirmation.
- code: groom/groom/assets/dashboard.js::pushToast
- dom: `aria-live="assertive"`, because a worker blocking is the one thing on this page worth interrupting for. Titles and bodies are set as text nodes, never as markup.

## Interactions

### select-activity-runs-mode

- on: [activity-runs-mode](#activity-runs-mode)
- trigger: pointer click, tap, Enter, or Space on the runs rail button or its SVG, captured by the delegated `#activitybar` click handler.
- role: button
- name: `Runs`
- keyboard: Tab and Shift+Tab reach the button; Enter or Space activates it.
- when:
  - The shell is loaded and the rail contains the runs control.
  - The click target or an ancestor matches `.act-btn`, and that control's `data-mode` is `runs`.
  - The prior mode may be any of the five.
- does:
  - Writes `runs` to the root `.app` element's `data-mode`, showing the runs pane and removing the other four panes from the accessibility tree.
  - Recomputes the `active` class and `aria-pressed` on every rail button by comparing its `data-mode` to `runs`.
  - Writes the mode to the store, so components that branch on it agree with the DOM.
  - Closes the repository menu, idempotently; menu contents, search text, picker labels, and the selected repository are all retained.
  - Takes no loader branch: runs is neither `files`, `diff`, nor `telemetry`, so no request is issued and the cached files, diff, and traces state is left as-is.
  - Leaves the selected run, the fleet, the detail pane, the palette, the status bar, the socket, and all server state untouched.
  - Performs no HTTP request, websocket send, navigation, focus move, or permission prompt.
- code: groom/groom/assets/dashboard.js::setMode
- code: groom/groom/assets/dashboard.js::closeRepoMenu

### select-activity-files-mode

- on: [activity-files-mode](#activity-files-mode)
- trigger: pointer click, tap, Enter, or Space on the files rail button or its SVG, captured by the delegated `#activitybar` click handler.
- role: button
- name: `Files`
- keyboard: Tab and Shift+Tab reach the button; Enter or Space activates it.
- when:
  - The click target or an ancestor matches `.act-btn` with `data-mode="files"`.
  - A selected repository may be absent, or may hold a container id plus an optional repository path in [dashboard selected repository state](../../dashboard-selected-repository-state.md).
- does:
  - Writes `files` to `.app[data-mode]`, recomputes `active` and `aria-pressed` across the rail, writes the mode to the store, and closes the repository menu.
  - Enters the files loader — even when files mode was already active, so reselecting the control reloads the pane.
  - Returns immediately without a request when no repository container is selected; the tree keeps its `Pick a container / repo above.` prompt.
  - Otherwise resets the files slice to a loading state with an empty path list, no open path, and an idle viewer, so a previous repository's file and tree are cleared before the new load.
  - Sends `GET /files/{container_id}?repo={repo}` to [get workspace file list](../../http/groom.md#get-workspace-file-list), URL-encoding both the container id and the repository path; an unset repository path is sent as an empty value.
  - Parses the response as JSON [workspace file list data](../../workspace-file-list-data.md) and stores its path array, rendering `(no files)` when it is empty.
  - Groups the flat repo-relative paths into a [dashboard path tree](../../dashboard-path-tree.md) at render time, sorting directories and then files by name; directories start expanded.
  - Stores an error status on a rejected fetch, which the tree renders as `failed to load`.
  - Leaves the selected run, the fleet, the detail pane, the palette, the status bar, and the socket untouched.
- code: groom/groom/assets/dashboard.js::setMode
- code: groom/groom/assets/dashboard.js::loadFiles
- code: groom/groom/assets/dashboard.js::FilesTree
- code: groom/groom/assets/dashboard.js::buildTree

### select-activity-diff-mode

- on: [activity-diff-mode](#activity-diff-mode)
- trigger: pointer click, tap, Enter, or Space on the diff rail button or its SVG, captured by the delegated `#activitybar` click handler.
- role: button
- name: `Diff`
- keyboard: Tab and Shift+Tab reach the button; Enter or Space activates it.
- when:
  - The click target or an ancestor matches `.act-btn` with `data-mode="diff"`.
  - A selected repository may be absent or present.
- does:
  - Writes `diff` to `.app[data-mode]`, recomputes `active` and `aria-pressed` across the rail, writes the mode to the store, and closes the repository menu.
  - Enters the diff loader, unconditionally, so reselecting the control reloads the pane.
  - Returns without a request when no repository container is selected.
  - Otherwise resets the diff slice to a loading state with no parsed files and no selected index.
  - Sends `GET /diff/{container_id}?repo={repo}` to [get working tree diff](../../http/groom.md#get-working-tree-diff) and reads the JSON body's raw unified diff.
  - Parses that text into a [dashboard parsed diff file cache](../../dashboard-parsed-diff-file-cache.md) with diff2html, storing an empty list for an empty diff, and leaves the selected index unset so the viewer shows its prompt.
  - Stores an error status on a rejected fetch, which the tree renders as `failed to load`.
  - Leaves the selected run, the fleet, the detail pane, the palette, the status bar, and the socket untouched.
- code: groom/groom/assets/dashboard.js::setMode
- code: groom/groom/assets/dashboard.js::loadDiff
- code: groom/groom/assets/dashboard.js::DiffTree

### select-activity-telemetry-mode

- on: [activity-telemetry-mode](#activity-telemetry-mode)
- trigger: pointer click, tap, Enter, or Space on the telemetry rail button or its SVG, captured by the delegated `#activitybar` click handler.
- role: button
- name: `Telemetry`
- keyboard: Tab and Shift+Tab reach the button; Enter or Space activates it.
- when:
  - The click target or an ancestor matches `.act-btn` with `data-mode="telemetry"`.
  - The span-filter fields hold whatever the operator last typed or ticked; they are shell markup and are not cleared by a mode switch.
- does:
  - Writes `telemetry` to `.app[data-mode]`, recomputes `active` and `aria-pressed` across the rail, writes the mode to the store, and closes the repository menu.
  - Enters the traces loader, unconditionally, so reselecting the control re-queries.
  - Serializes the filter fields into a query string and sends `GET /traces` with it.
  - Stores the response's run cards and span rows, which the pane renders as the card strip and the traces table; an empty span list renders the no-match note under the strip, or the not-connected note when `show ended` is unticked and no run came back.
  - Stores an error status on a rejected fetch, which the pane renders as `failed to load`.
  - Leaves the selected run, the fleet, the detail pane, the files and diff caches, the palette, and the socket untouched.
- code: groom/groom/assets/dashboard.js::setMode
- code: groom/groom/assets/dashboard.js::loadTraces
- code: groom/groom/assets/dashboard.js::Traces

### select-activity-settings-mode

- on: [activity-settings-mode](#activity-settings-mode)
- trigger: pointer click, tap, Enter, or Space on the settings rail button or its SVG, captured by the delegated `#activitybar` click handler.
- role: button
- name: `Settings`
- keyboard: Tab and Shift+Tab reach the button; Enter or Space activates it.
- when:
  - The click target or an ancestor matches `.act-btn` with `data-mode="settings"`.
- does:
  - Writes `settings` to `.app[data-mode]`, recomputes `active` and `aria-pressed` across the rail, writes the mode to the store, and closes the repository menu.
  - Takes no loader branch, issues no request, and prompts for no permission — entering settings mode is inert.
  - Leaves every other piece of browser and server state untouched.
- code: groom/groom/assets/dashboard.js::setMode
- screenshot: docs/features/groom/gui/screenshots/operator-refreshes-workflow-fleet-settings-idle.png

### filter-runs

- on: [runs-filter-input](#runs-filter-input)
- trigger: an `input` event on the runs filter field — typing, pasting, or using the search field's clear affordance.
- role: searchbox
- name: `Filter runs`
- keyboard: Tab reaches the field; every keystroke fires the handler.
- when:
  - The runs pane is loaded; the fleet may be empty, mid-discovery, or populated.
- does:
  - Writes the field's raw value to the store's query, with no debounce — filtering happens on the client over a few dozen already-pushed rows, so there is nothing to wait for.
  - Re-renders the run list to only those rows whose haystack — name, repository, type, node, activity, current doing line, question, and run id, lowercased and joined — contains the trimmed lowercased query.
  - Renders `No workhorse runs — nothing is running.` when the query matches nothing, rather than the discovery message; the discovery message is shown only for an empty *unfiltered* fleet.
  - Does not filter server-side. A server-filtered list would be clobbered by the next 5s push, which is the whole reason the fleet is sent whole.
  - Leaves the selected run, the detail pane, and the command palette's own hit list untouched — the palette reads the fleet from the store, so it still finds a run this filter is hiding.
  - Performs no HTTP request and no websocket send.
- code: groom/groom/assets/dashboard.js::wireEvents
- code: groom/groom/assets/dashboard.js::Fleet
- code: groom/groom/assets/dashboard.js::rowHaystack
- verify: groom/tests/test_projection.py::test_query_filters_the_fleet

### select-run-row

- on: [run-row](#run-row)
- trigger: pointer click, tap, Enter, or Space anywhere in a run row, captured by the delegated body click handler that looks for the nearest `[data-worker-id]` ancestor.
- role: button
- name: `{repo} #{short_handle} {liveness} {doing}`
- keyboard: Tab reaches the row; Enter or Space activates it.
- when:
  - The click did not originate inside a form, the repository menu, a repository picker, or a file tree — those have their own handlers.
  - The nearest matching ancestor carries a `data-worker-id`.
- does:
  - Takes the next selection sequence number, so a slower reply for an older selection cannot land.
  - Writes the run id and a null detail to the store in one update, so no render pairs the new selection with the previous run's pane; that pair is what the detail pane renders as `Loading…`.
  - Sends this tab's watch subscription for the id over the dashboard websocket, replacing whatever it was watching. A tab watches at most one run, and a refused send is not retried because the next selection or reconnect re-sends it.
  - Fetches [GET /worker/{container_id}](../../http/groom.md#get-run-detail) once and stores the parsed body — but only if this is still the newest selection *and* no pushed detail has landed meanwhile, since a `detail` frame that arrived first is the fresher truth.
  - Swallows a rejected fetch; the pane stays in its loading state and is filled by the subscription's next push, so a transient failure costs a tick rather than an error message.
  - Renders selection rather than applying it: the row emits `selected` and `aria-current="true"` from the store on every render, so a fleet push already agrees with the selection and nothing walks the document repainting rows.
  - Does not move focus, change the active mode, or mutate any server state beyond the subscription.
- code: groom/groom/assets/dashboard.js::select
- code: groom/groom/assets/dashboard.js::onDetail
- code: groom/groom/assets/dashboard.js::RunRow
- verify: groom/tests/test_app.py::test_watch_registers_the_tab_and_pushes_that_run_immediately
- verify: groom/tests/test_app.py::test_a_detail_push_reaches_only_the_tabs_watching_that_run
- screenshot: docs/features/groom/gui/screenshots/operator-answers-blocked-gate-detail-selected.png

### keyboard-select-run-row

- on: [run-row](#run-row)
- trigger: pressing `j` or `k` anywhere on the page while focus is not in an input or textarea.
- role: button
- name: `{repo} #{short_handle} {liveness} {doing}`
- keyboard: `j` moves the selection one row down, `k` one row up; both clamp at the ends of the list rather than wrapping.
- when:
  - The command palette is closed — while it is open, the same keys type into its input.
  - The active element is not an `INPUT` or `TEXTAREA`, so typing a `j` into the filter box never moves the selection.
- does:
  - Reads the currently rendered rows out of `#runs-list` and finds the index of the selected run by its `data-worker-id`; an unselected fleet starts from the first row.
  - Clamps the neighbouring index into range and, if a row is there, switches to runs mode and selects that run through the same selector the click path uses.
  - Moves through the *rendered* rows, so an active filter narrows what the keys traverse.
  - Does nothing when the list is empty.
- code: groom/groom/assets/dashboard.js::wireEvents
- code: groom/groom/assets/dashboard.js::select
- code: groom/groom/assets/dashboard.js::setMode

### open-files-repository-picker

- on: [files-repository-picker-button](#files-repository-picker-button)
- trigger: pointer click, tap, Enter, or Space on the files pane's picker.
- role: button
- name: `Select container / repo…`
- keyboard: Tab reaches the button; Enter or Space toggles the menu.
- when:
  - The files pane is the active pane; the menu may be open or closed.
- does:
  - Closes the menu and returns when it is already open, so the picker toggles rather than re-opening.
  - Otherwise records this button as the invoker, positions the menu box under it at least as wide as the button, and adds `open` to the wrapper.
  - Sets `aria-expanded="true"` on the menu search input and clears its value.
  - Resets the repository slice to loading with no groups, no query, and the first row active.
  - Fetches `GET /repos` from [get repository menu](../../http/groom.md#get-repository-menu) and stores the returned [repository menu data](../../repository-menu-data.md) groups; a rejection stores an empty list, which the menu renders as `No repositories available.`
  - Focuses the menu search input.
  - Leaves the previously selected repository, both picker labels, and the loaded files pane untouched until an option is chosen.
- code: groom/groom/assets/dashboard.js::openRepoMenu
- code: groom/groom/assets/dashboard.js::closeRepoMenu
- code: groom/groom/assets/dashboard.js::wireEvents
- screenshot: docs/features/groom/gui/screenshots/operator-browses-workspace-file-repo-menu-open.png

### open-diff-repository-picker

- on: [diff-repository-picker-button](#diff-repository-picker-button)
- trigger: pointer click, tap, Enter, or Space on the diff pane's picker.
- role: button
- name: `Select container / repo…`
- keyboard: Tab reaches the button; Enter or Space toggles the menu.
- when:
  - The diff pane is the active pane; the menu may be open or closed.
- does:
  - Behaves identically to the files picker — the menu, its data, and its handlers are shared; only the recorded invoker differs, which is what decides where the box is positioned and where focus returns on close.
  - Fetches `GET /repos` fresh on every open, so a container that appeared or vanished since the last open is reflected.
- code: groom/groom/assets/dashboard.js::openRepoMenu
- code: groom/groom/assets/dashboard.js::wireEvents

### filter-repository-menu-options

- on: [repository-menu-search-input](#repository-menu-search-input)
- trigger: an `input` event on the menu search field.
- role: combobox
- name: `Search container / repo`
- keyboard: Tab is not needed — the field is focused on open; ArrowDown and ArrowUp move the active option and Enter chooses it.
- when:
  - The repository menu is open; its groups may still be loading.
- does:
  - Writes the raw query to the repository slice and resets the active index to the first row, so the keyboard never points past the end of a shortened list.
  - Re-flattens the server's per-container groups into a single ordered list, keeping only entries whose label contains the trimmed lowercased query — the list the keyboard actually moves through.
  - Rebuilds the rendered options rather than hiding non-matching rows, so a filtered-out repository is out of the accessibility tree rather than merely invisible.
  - Republishes `aria-activedescendant` on the search input to the surviving active option, or removes it when nothing matches, and scrolls that option into view.
  - Issues no request; the groups were fetched once when the menu opened.
- code: groom/groom/assets/dashboard.js::wireEvents
- code: groom/groom/assets/dashboard.js::repoItems
- code: groom/groom/assets/dashboard.js::RepoMenu
- code: groom/groom/assets/dashboard.js::moveRepoActive

### select-repository-menu-option

- on: [repository-menu-option](#repository-menu-option)
- trigger: pointer click or tap on an option, or Enter from the menu search input with an active option.
- role: option
- name: `{container} / {repo}`
- keyboard: ArrowDown and ArrowUp move the active option; Enter chooses it; Escape abandons the menu without choosing.
- when:
  - The menu is open and the flattened option list is non-empty.
- does:
  - Writes the chosen container id, repository path, and label to [dashboard selected repository state](../../dashboard-selected-repository-state.md).
  - Replaces the label text on *both* repository pickers, so the files and diff panes never disagree about what is selected.
  - Loads whichever pane is active through the [dashboard active pane loader](../../concepts/dashboard-active-pane-loader.md) — the files tree in files mode, the diff tree in diff mode, and nothing at all in any other mode.
  - Closes the menu: removes `open`, sets `aria-expanded="false"`, drops `aria-activedescendant`, and returns focus to the invoking picker rather than dropping it to `<body>`.
  - Retains the loaded groups and the search text; the next open clears them itself.
- code: groom/groom/assets/dashboard.js::selectRepo
- code: groom/groom/assets/dashboard.js::loadActivePane
- code: groom/groom/assets/dashboard.js::closeRepoMenu

### toggle-files-directory

- on: [files-directory-toggle](#files-directory-toggle)
- trigger: pointer click, tap, Enter, or Space on a directory row in the files tree.
- role: button
- name: `{directory}`
- keyboard: Tab reaches the row; Enter or Space toggles it.
- when:
  - The files tree has rendered at least one directory level.
- does:
  - Flips that directory node's local open state and its `aria-expanded`, adding or removing the `collapsed` class on its wrapper.
  - Keeps the state component-local rather than in the store: it belongs to this directory in this tab and nothing else reads it, and it survives a re-render because the node is keyed by name.
  - Leaves the open file, the viewer, and every other directory untouched, and issues no request.
- code: groom/groom/assets/dashboard.js::TreeDir

### select-files-file-row

- on: [files-file-row](#files-file-row)
- trigger: pointer click, tap, Enter, or Space on a file row in the files tree.
- role: button
- name: `{filename}`
- keyboard: Tab reaches the row; Enter or Space opens the file.
- when:
  - A repository is selected and the files tree has rendered at least one file.
- does:
  - Records the clicked path as the open path and puts the viewer into its loading state under that path, so the previous file's body is gone before the new one arrives.
  - Sends `GET /file/{container_id}?repo={repo}&path={path}` to [get workspace file content](../../http/groom.md#get-workspace-file-content), URL-encoding the container, repository, and path.
  - Discards the reply — success or failure — when a later click has already changed the open path, so a slow response cannot overwrite a newer file.
  - Stores the returned [workspace file content data](../../workspace-file-content-data.md): the resolved path, the content, and the server-decided language, whose extension table lives with the rest of the presentation policy.
  - Renders `(empty or binary file)` under the path header for empty content.
  - Highlights the content with highlight.js when it is available, falling back to a plain text node when the library is absent or throws — the highlighted output is escaped HTML, which is why it may be set as markup at all.
  - Marks this row `active` with `aria-current="true"` and clears the marking from the previously open row.
  - Stores an error status on rejection, rendered as `failed to load`.
- code: groom/groom/assets/dashboard.js::openFile
- code: groom/groom/assets/dashboard.js::FileView
- code: groom/groom/assets/dashboard.js::highlight
- screenshot: docs/features/groom/gui/screenshots/operator-browses-workspace-file-file-loaded.png

### toggle-diff-directory

- on: [diff-directory-toggle](#diff-directory-toggle)
- trigger: pointer click, tap, Enter, or Space on a directory row in the diff tree.
- role: button
- name: `{directory}`
- keyboard: Tab reaches the row; Enter or Space toggles it.
- when:
  - The diff tree has rendered at least one directory level.
- does:
  - Flips that directory node's local open state and its `aria-expanded`, exactly as the files tree does — the two trees are one component over two entry lists.
  - Leaves the shown diff, the parsed diff cache, and every other directory untouched, and issues no request.
- code: groom/groom/assets/dashboard.js::TreeDir

### select-diff-file-row

- on: [diff-file-row](#diff-file-row)
- trigger: pointer click, tap, Enter, or Space on a changed-file row in the diff tree.
- role: button
- name: `{filename} +{added} -{deleted}`
- keyboard: Tab reaches the row; Enter or Space shows that file's diff.
- when:
  - A repository is selected and the parsed diff holds at least one changed file.
- does:
  - Writes that file's index into the [dashboard parsed diff file cache](../../dashboard-parsed-diff-file-cache.md) to the diff slice; nothing is fetched, because the whole diff was parsed when the pane loaded.
  - Renders that one parsed file with diff2html into the viewer, line by line, in the dark colour scheme and with no file-list header.
  - Marks this row `active` with `aria-current="true"` and clears the previous row's marking.
  - Renders nothing but the selection prompt when the index points at no file.
- code: groom/groom/assets/dashboard.js::DiffTree
- code: groom/groom/assets/dashboard.js::DiffView
- screenshot: docs/features/groom/gui/screenshots/operator-inspects-working-tree-diff-file-selected.png

### edit-detail-answer-textarea

- on: [detail-answer-textarea](#detail-answer-textarea)
- trigger: typing, pasting, or otherwise editing the answer field.
- role: textbox
- name: `Your answer`
- keyboard: Tab reaches the field; Enter inserts a newline; Tab moves on to the send button.
- when:
  - The open run has at least one open gate, so the answer form is rendered.
- does:
  - Changes nothing but the field's own value — there is no input handler, no draft written to the store, and no request.
  - Survives the fleet's 5-second push: the gate block is keyed by gate file path, so Preact reuses the same `<textarea>` DOM node across re-renders and neither the text nor the caret is lost.
  - Survives a pushed `detail` frame for the same run for the same reason, including one carrying a newly opened gate for a different file.
- code: groom/groom/assets/dashboard.js::AnswerForm
- code: groom/groom/assets/dashboard.js::GateBlock
- screenshot: docs/features/groom/gui/screenshots/operator-answers-blocked-gate-answer-typed.png

### send-detail-answer

- on: [detail-send-answer-button](#detail-send-answer-button)
- trigger: submitting the answer form — clicking the button, or Enter from within it — captured by a delegated document-level submit handler.
- role: button
- name: `Send answer`
- keyboard: Tab reaches the button; Enter or Space submits.
- when:
  - The submit target is inside a `form[data-answer]`.
  - The websocket may be open or closed; the outcome differs and is reported either way.
- does:
  - Prevents the browser's own form submission, so the page never navigates.
  - Serializes the form's fields into a [dashboard websocket answer frame](../../dashboard-websocket-answer-frame.md) — the `answer` command, the workflow id, the gate file path, and the typed answer — and sends it over the dashboard websocket. The client serializes the frame itself, which is what lets a failed send *say* it failed.
  - Clears the textarea on a successful send and leaves it untouched otherwise, so a rejected answer is still in the box.
  - Pushes the `✗ not sent` toast, naming the lost connection, when the send is refused.
  - Does not re-fetch the pane. The server's [gate answering layer](../../concepts/gate-answering-layer.md) broadcasts a [dashboard answered message](../../dashboard-answered-message.md) to every tab, which only raises the `✓ answer sent` confirmation; the pane itself is refreshed by the `detail` push the same command triggers, which carries the gates — so no tab re-fetches and a half-typed answer against a different run is never touched.
  - Delegates from the document rather than binding per form, because the form is re-rendered on every push and a delegated handler outlives every one of them.
- code: groom/groom/assets/dashboard.js::wireAnswerForm
- code: groom/groom/assets/dashboard.js::sendCommand
- code: groom/groom/assets/dashboard.js::onAnswered
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_an_answered_event
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch
- verify: groom/tests/test_a11y_dynamic.py::test_the_answer_form_is_reachable_and_submittable_by_keyboard
- screenshot: docs/features/groom/gui/screenshots/operator-answers-blocked-gate-answer-drafted.png

### toggle-detail-working-tree-diff

- on: [detail-working-tree-diff-toggle](#detail-working-tree-diff-toggle)
- trigger: a `toggle` event on the detail pane's `<details>` disclosure, from a click, tap, Enter, or Space on its summary.
- role: button
- name: `Working-tree diff`
- keyboard: Tab reaches the summary; Enter or Space expands and collapses it.
- when:
  - A run is open in the detail pane.
  - The disclosure is being opened, and it has neither loaded nor failed before.
- does:
  - Returns immediately when the disclosure is closing, when the diff is already loaded, or when a previous attempt failed — so collapsing and re-expanding never re-fetches, and a failure is not retried on every toggle.
  - Otherwise fetches `GET /diff/{container_id}` from [get working tree diff](../../http/groom.md#get-working-tree-diff) for the open run's container and stores the JSON body's raw unified diff, treating a missing field as empty.
  - Shows `Loading diff…` until the reply lands, then the rendered diff, `(no changes)` for an empty or whitespace-only diff, or `failed to load diff` on rejection.
  - Renders with diff2html, which parses the unified text and escapes what it emits.
  - Resets when the open run changes, because the disclosure is keyed by run id — a newly opened run never shows the previous run's diff.
- code: groom/groom/assets/dashboard.js::DiffDisclosure
- code: groom/groom/assets/dashboard.js::diffMarkup
- screenshot: docs/features/groom/gui/screenshots/operator-inspects-working-tree-diff-detail-disclosure-expanded.png

### rescan-containers-from-settings

- on: [settings-rescan-button](#settings-rescan-button)
- trigger: pointer click, tap, Enter, or Space on the settings pane's rescan button, captured by the delegated body click handler.
- role: button
- name: `Rescan containers`
- keyboard: Tab reaches the button; Enter or Space activates it.
- when:
  - Settings mode is active. A rescan may already be in flight.
- does:
  - Returns immediately when the button already carries `data-busy`, so a double click issues one request.
  - Marks the button busy and spinning, then sends `POST /refresh` to [post refresh](../../http/groom.md#post-refresh).
  - Clears the busy marking and the spinner when the request settles, on success or failure alike.
  - Renders nothing from the reply. The server reconciles the fleet, prunes vanished containers, and broadcasts the resulting state on the socket, so the run list and status bar update through the same path as every other push.
  - Leaves the selected run, the detail pane, the files and diff caches, and the palette untouched.
- code: groom/groom/assets/dashboard.js::doRefresh
- verify: groom/tests/test_app.py::test_refresh_prunes_vanished_containers
- verify: groom/tests/test_app.py::test_refresh_skips_prune_when_docker_unavailable

### rescan-containers-from-statusbar

- on: [statusbar-refresh-button](#statusbar-refresh-button)
- trigger: pointer click, tap, Enter, or Space on the status bar's refresh control, captured by the same delegated body click handler.
- role: button
- name: `Rescan containers (reconcile + prune)`
- keyboard: Tab reaches the button; Enter or Space activates it.
- when:
  - Any mode is active — the status bar is outside the panes and always visible.
- does:
  - Runs the identical rescan the settings control runs; the two share one handler and one busy guard per button.
  - Spins its own icon while in flight, which is the only feedback until the resulting state broadcast arrives.
  - Is named longer than the settings control on purpose: both are on screen together in settings mode, and two buttons computing to the same role and name would be indistinguishable to a screen reader and to `getByRole`.
- code: groom/groom/assets/dashboard.js::doRefresh
- code: groom/groom/assets/dashboard.js::StatusBar
- screenshot: docs/features/groom/gui/screenshots/operator-refreshes-workflow-fleet-post-scan.png

### enable-browser-notifications-from-settings

- on: [settings-enable-notifications-button](#settings-enable-notifications-button)
- trigger: pointer click, tap, Enter, or Space on the settings pane's notifications button.
- role: button
- name: `Enable notifications`
- keyboard: Tab reaches the button; Enter or Space activates it.
- when:
  - The browser exposes the Notification API. Where it does not, the click is ignored entirely.
- does:
  - Requests [browser notification permission](../../concepts/browser-notification-permission.md), which shows the browser's own prompt when the permission is still at its default and resolves silently when it has already been granted or denied.
  - Changes no dashboard state: the label does not change, nothing is stored, and no request is sent.
  - Determines only what a later block does — with permission granted, a blocked-run notification raises a system notification alongside its toast; without it, only the toast.
  - Is not the only path: the first click anywhere on the page also asks once, because an unprompted permission dialog is a dark pattern and browsers ignore one without a user gesture anyway.
- code: groom/groom/assets/dashboard.js::wireEvents
- code: groom/groom/assets/dashboard.js::onNotify

### toggle-command-palette-shortcut

- on: [command-palette-open-button](#command-palette-open-button)
- trigger: `Ctrl+K` or `Meta+K` anywhere on the page, or pointer click, tap, Enter, or Space on the status bar's palette button.
- role: button
- name: `Open command palette`
- keyboard: `Ctrl+K` and `Meta+K` toggle the palette from anywhere, including from inside a text field; Escape closes it.
- when:
  - The dashboard is loaded. The palette may be open or closed; the shortcut toggles, the button only opens.
- does:
  - Suppresses the browser's default for the shortcut, then closes the palette if it is open and opens it otherwise.
  - On open: records the invoker — the button, or whatever had focus when the shortcut fired — adds `open`, sets `aria-expanded="true"`, clears the input, resets the query and active index in the store, and focuses the input.
  - Renders the current fleet from the store as results, so the palette lists runs the runs-pane filter is hiding.
  - Traps Tab on the input while open, since that input is the dialog's only focusable element.
  - On close: removes `open`, sets `aria-expanded="false"`, drops `aria-activedescendant`, marks the palette closed in the store, and returns focus to the recorded invoker rather than to `<body>`.
  - Sends no request and touches no server state.
- code: groom/groom/assets/dashboard.js::openPalette
- code: groom/groom/assets/dashboard.js::closePalette
- code: groom/groom/assets/dashboard.js::wireEvents

### filter-command-palette-results

- on: [command-palette-input](#command-palette-input)
- trigger: an `input` event on the palette field, or ArrowDown/ArrowUp to move the active result.
- role: combobox
- name: `Jump to a worker or blocked gate`
- keyboard: the field is focused on open; ArrowDown and ArrowUp move the active result and are prevented from scrolling the page; Enter chooses; Escape closes.
- when:
  - The palette is open. The fleet may be empty.
- does:
  - Writes the raw query to the palette slice and resets the active index to the first hit.
  - Computes hits from the fleet **in the store** — not from the rendered rows — filtering on the same haystack the runs filter uses, so a run hidden by that filter is still reachable here.
  - Clamps the active index into the hit list on every move, so it never points past the end of a shortened list, and does nothing at all when there are no hits.
  - Republishes `aria-activedescendant` on the input to the active result, or removes it when nothing matches, and scrolls that result into view.
  - Sends no request; the fleet is already in the browser.
- code: groom/groom/assets/dashboard.js::paletteHits
- code: groom/groom/assets/dashboard.js::PaletteResults
- code: groom/groom/assets/dashboard.js::movePaletteActive

### select-command-palette-result

- on: [command-palette-result](#command-palette-result)
- trigger: pointer click or tap on a result, or Enter from the palette input with an active result.
- role: option
- name: `{repo} #{short_handle} {doing} {hint}`
- keyboard: ArrowDown and ArrowUp move the active result; Enter chooses it; Escape abandons the palette.
- when:
  - The palette is open and at least one result matches.
- does:
  - Switches to runs mode first, so the row the operator just chose is on screen — the palette is reachable from files, diff, telemetry, and settings alike.
  - Selects that run through the same selector the row click and the `j`/`k` keys use: store write, watch subscription, one detail fetch.
  - Closes the palette and returns focus to whatever opened it.
  - Chooses by run id rather than by rendered position, so the result list re-rendering under a concurrent push cannot open the wrong run.
- code: groom/groom/assets/dashboard.js::choosePaletteHit
- code: groom/groom/assets/dashboard.js::select
- code: groom/groom/assets/dashboard.js::setMode

### filter-telemetry-spans

- on: [telemetry-status-filter-select](#telemetry-status-filter-select)
- trigger: an `input`, `change`, or `submit` event anywhere in the telemetry filter form — typing in any of the three text fields, changing the status select, ticking the `show ended` checkbox, or pressing Enter.
- role: combobox
- name: `Filter by span status`
- keyboard: Tab reaches each field in turn; ArrowUp and ArrowDown change the select; Enter submits, which is intercepted rather than navigating.
- when:
  - Telemetry mode is active.
- does:
  - Prevents the form's default submission, so the page never navigates.
  - Serializes the fields — run id, node, span status, minimum duration in seconds, and the `show ended` checkbox when it is ticked — into a query string and sends `GET /traces` with it. Empty fields are sent as empty values and ignored by the server; an unticked checkbox is not sent at all, which the server reads as the connected-runs-only default.
  - Stores the returned run cards and span rows, replacing the previous result wholesale.
  - Renders the run-card strip above the table, and beneath it the no-match note when runs are known but no span survives the filter, or the not-connected note when the connected-only view came back empty.
  - Stores an error status on rejection, rendered as `failed to load`.
  - Re-queries on every keystroke, without debounce; the query is served from groom's local span store rather than from a remote backend.
  - Leaves the selected run, the fleet, and the detail pane untouched.
- code: groom/groom/assets/dashboard.js::loadTraces
- code: groom/groom/assets/dashboard.js::Traces
- code: groom/groom/assets/dashboard.js::RunCard
