---
type: screen
slug: groom-dashboard
title: groom dashboard
---
# groom dashboard

- route: `/`; live-verified — selecting a run row, editing the answer textarea, and every activity-mode switch stay on this same landed path with no browser navigation.
- requires:
  - none — the root route is unauthenticated and unguarded; groom serves the shell to anyone who can reach the port.
- params:
  - none — the screen takes no path or query parameter. Everything it shows is chosen after load and held in the browser, never in the URL.
- entry: opened directly at the groom server's root URL. It is the only screen groom serves, so it is entered from outside in-app navigation and never linked to from another screen.

The `groom` dashboard is the browser screen served by the [root dashboard endpoint](../../http/groom.md#get-root-dashboard-html), whose handler is `groom/groom/app.py::index`. It is the operator console for the [runs fleet view](../../runs-fleet-view.md), the run's file browser and working-tree diff, both tabs of the run's detail and described by [changes view](../../changes-view.md), and the manual reconciliation controls for the discovered [workflow containers](../../concepts/workflow-container.md).

The dashboard's automated coverage includes the open-gate accessibility path (`groom/tests/test_a11y_dynamic.py::test_runs_pane_with_an_open_gate_is_accessible`), client-module parsing (`groom/tests/test_dashboard_client.py::test_the_client_module_parses`), and JSON serialization of state messages (`groom/tests/test_projection.py::test_state_message_is_json_serializable`). Its visual review evidence is recorded in `docs/specs/groom-dashboard/vet.md`.

Nothing on either side of the wire is HTML. The endpoint ships a static shell — landmarks, live regions, overlays, and the ids the client mounts into — and every visible region is a Preact island rendered from JSON by `groom/groom/assets/dashboard.js`. The screen opens a browser websocket to `/ws` and receives fleet-wide [dashboard state payloads](../../formats/dashboard-state-payload.md) on the server's clock; it subscribes that tab to the one run it has open and receives that run's detail pushed back to it alone; and it fetches per-selection panel data — a run's files and diff — over HTTP, because those are one tab's choices and not fleet-wide facts. A socket `state` frame and the body of [GET /api/state](../../http/groom.md#get-dashboard-state) are the same JSON and go through the same apply function, so recovering from a dead socket is not a second rendering path that can rot unobserved.

The visible shell has four activity modes selected by the left activity rail: runs, attendant, dispatch, and settings. A run's files and diff are not rail modes: they are tabs inside the open run, so the rail carries no Files or Diff control and no repository picker. The app starts in **runs** mode. It holds the selected run id, the checkout chosen for each run, per-tab loading state, and transient overlay state for the command palette in the [dashboard client store](../../concepts/dashboard-client-store.md), and keeps the source of truth for run rows and counts on the server. Selecting a row follows [select run row](#select-run-row), which marks one [run row](#run-row) current and fills `#detail` from [get run detail](../../http/groom.md#get-run-detail) and the tab's own watch subscription — without changing the active mode.

Connection state is its own visible fact. The [connection chip](#connection-chip) reports `live`, `stale`, `reconnecting`, or `offline`, derived by the [dashboard connection state machine](../../concepts/dashboard-connection-state-machine.md) from **message recency, not `readyState`** — a half-open socket reads OPEN forever and would otherwise show a green dot over a frozen fleet. Anything but `live` starts the [dashboard resync poller](../../concepts/dashboard-resync-poller.md) against `GET /api/state`.

## Layout

- app root: `.app[data-mode]`, connected to `WS /ws`; `data-mode` selects which pane is displayed. Inactive panes are `display:none`, so they are removed from the accessibility tree rather than merely hidden visually.
- activity rail: a left `<nav aria-label="Panels">` landmark with runs, attendant, dispatch, and settings mode controls; selecting the gear follows [select activity settings mode](#select-activity-settings-mode).
- main region: a `<main id="main">` landmark holding all four panes, opened by the page's single `<h1>`, which is visually hidden but present because a screen reader has no title bar to read.
- runs pane: filter input, the live run list in `#runs-list`, and the open run's detail in `#detail`. With no run selected the list takes the full width and `#detail` is hidden. Selecting a run narrows the list to a column and opens `#detail` beside it.
- settings pane: manual container rescan and browser notification permission controls.
- status bar: fleet counts, repo/worker totals, the connection chip, the refresh control, and the command-palette open button.
- overlays: command palette in `#palette` and the toast stack in `#toasts`.

## States

- mode: `runs` by default; `attend`, `dispatch`, and `settings` are mutually exclusive alternatives written to `.app[data-mode]` and to the store together. A mode with no pane in the page, such as the retired `files` or `diff`, lands on `runs`.
- selected run: absent until a run row, palette result, or `j`/`k` row movement writes [dashboard selected worker state](../../formats/dashboard-selected-worker-state.md). Selecting one clears the detail pane, opens it on the Overview tab, narrows the list, sends this tab's watch subscription, and fetches `GET /worker/{container_id}` once. [close run detail](#close-run-detail) clears the selection, widens the list to full width, and keeps the filter text.
- selected checkout: held per run in the page's memory beside the tab state, for the life of the page. A run selected for the first time shows its first checkout, selecting another run and coming back restores the earlier choice, and a reload starts at the first checkout again. One choice governs the run's Files and Diff tabs. See [detail-checkout-select](#detail-checkout-select).
- command palette: closed by default; `Ctrl+K` or `Meta+K` toggles it, and the status-bar button opens it. Opening clears its input, renders the current fleet from the store as results, and focuses `#palette-input`; while open, Tab is trapped on that input.
- discovery: `scanning` is true until the [startup background discovery scan](../../concepts/startup-background-discovery-scan.md) finishes; an empty fleet renders as `Discovering containers…` while it is, and as `No workhorse runs — nothing is running.` after.
- connection: `connecting` on load, then `live` while a frame has arrived within 15s, `stale` when the open socket has been silent longer, `reconnecting` for the first 60s after a close, and `offline` beyond that. Every phase but `live` polls `GET /api/state` on a 5s interval.
- live regions: `#runs-list` (`role="log"`), `#statusbar` and the chip inside it, `#detail`'s run header, and `#toasts` are the announcing regions. Each is a static shell element that an island renders *into*, so the region itself never re-renders and assistive tech keeps tracking the same node. Markdown gate questions are rendered through `marked` and sanitized by DOMPurify before they reach `innerHTML`.

## Components

### activity-rail

- selector: `#activitybar`
- role: navigation
- name: `Panels`
- placement: width 0-20%, x 0-20%
- keyboard: not focusable itself.
- verify: visible(locator="#activitybar", text="Panels")
- keyboard: Tab moves through the four mode buttons it contains, in DOM order.
- verify: visible(locator="#activitybar .act-btn", text="Runs")
- parent: [groom dashboard](#groom-dashboard)
- states: static.
- verify: visible(locator="#activitybar", text="Panels")
- states: It is shell markup, never re-rendered.
- verify: visible(locator="#activitybar", text="Panels")
- states: Only the `active` class and `aria-pressed` on its buttons change, as the mode switch toggles them per button.
- states: the Runs button carries a badge with the blocked-run count while another pane is open.
- states: the badge is hidden on the Runs pane.
- states: the badge is hidden while no run is blocked.
- states: the button's accessible name says the count in words, such as `Runs, 2 blocked runs`.
- verify: visible(locator="#activity-rail", text="2")
- verify: json_path(path="activity_rail.buttons.active.aria_pressed", equals="true")
- code: groom/groom/templates/dashboard.html@65323b15e0f8
- code: groom/groom/assets/dashboard.js::paintRunsBadge@bd8cea76ff7e
- tests: groom/tests/test_a11y_dynamic.py::test_the_activity_rail_is_reachable_and_operable_by_keyboard
- tests: groom/tests/test_gate_strip_dynamic.py::test_the_runs_button_carries_a_counted_badge_while_another_pane_is_open_and_clears_with_the_last_block
- dom: the badge is an `aria-hidden` span inside the Runs button, so the count is spoken once, through the button's own name. A `<nav>` rather than a `role="toolbar"` div — switching panes *is* this page's navigation, and a toolbar is not a landmark, so its contents would otherwise sit outside every region. `groom/groom/assets/dashboard.css` assigns it to the left `act` grid area, whose first column is fixed at 48px.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-activity-rail.png

### main-region

- selector: `#main`
- role: main
- name: none
- placement: width 60-100%, x 0-20%
- keyboard: not focusable.
- verify: json_path(path="keyboard.focusable", equals=false)
- keyboard: a landmark, not a control.
- verify: json_path(path="keyboard.kind", equals="landmark")
- parent: [groom dashboard](#groom-dashboard)
- states: always present.
- verify: json_path(path="states.present", equals=true)
- states: its visible child is whichever pane `.app[data-mode]` selects.
- verify: json_path(path="states.visible_child", equals="pane selected by .app[data-mode]")
- code: groom/groom/templates/dashboard.html@65323b15e0f8
- dom: holds all four panes as siblings. The three inactive ones are `display:none`, so exactly one pane's controls are in the accessibility tree at a time. `groom/groom/assets/dashboard.css` gives `.app` a fixed 48px activity column and assigns `#main` the remaining `main` grid area.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-main-region.png

### page-heading

- selector: `#main > h1.sr-only`
- role: heading
- verify: visible(locator="#main > h1.sr-only", text="groom — workhorse fleet dashboard")
- name: `groom — workhorse fleet dashboard`
- verify: json_path(path="accessibility.name", equals="groom — workhorse fleet dashboard")
- keyboard: not focusable.
- verify: json_path(path="keyboard.focusable", equals=false)
- parent: [main-region](#main-region)
- states: static.
- verify: json_path(path="states.present", equals=true)
- dom: visually hidden and always rendered. It is the page's one `h1`; without it the document outline would start at `h2` and a screen reader would have nothing to announce the page as.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-page-heading.png

### activity-runs-mode

- selector: `.act-btn[data-mode="runs"]`
- role: button
- name: `Runs`
- keyboard: natively focusable with Tab and Shift+Tab.
- verify: visible(locator=".act-btn[data-mode='runs']:focus", text="Runs")
- keyboard: Enter or Space activates the mode switch.
- verify: visible(locator=".app[data-mode='runs']", text="Runs")
- parent: [activity-rail](#activity-rail)
- states: active by default, with the `active` class and `aria-pressed="true"`.
- verify: visible(locator=".act-btn[data-mode='runs'].active[aria-pressed='true']", text="Runs")
- states: inactive with `aria-pressed="false"` in any other mode.
- verify: visible(locator=".act-btn[data-mode='runs'][aria-pressed='false']", text="Runs")
- states: this is a real, data-dependent accessibility ambiguity, not a mislabeling: any tree row in a run's Files or Diff tab whose name happens to be the literal text `Runs` — a directory or a file ([detail-files-file-row](#detail-files-file-row), [detail-diff-file-row](#detail-diff-file-row)) named `Runs` — renders with the identical `role=button name="Runs"` pair as this always-present rail button, so `getByRole('button', {name: 'Runs'})` cannot distinguish them.
- states: the collision is left standing rather than papered over with an invented distinguishing label, because the rail button's name cannot be changed without changing the product's navigation label.
- states: the collision is left standing rather than papered over with an invented distinguishing label, because a repository's file and directory names are arbitrary user data this doc cannot constrain.
- code: groom/groom/assets/dashboard.js::setMode@d01c7d7c3d9c
- props:
  - `data-mode`: literal `runs`; required; the mode value the delegated rail handler passes to the mode switch.
  - `title`: literal `Runs`; required; tooltip text only.
  - `aria-label`: literal `Runs`; required; the durable accessible name for this icon-only button.
  - `aria-pressed`: `true` or `false`; required; recomputed for every rail button on each mode switch.
- dom: icon-only native `<button type="button">` inside the `#activitybar` nav, first of the four; contains only an inline `aria-hidden="true"` SVG and no text node.
- leads-to: [select activity runs mode](#select-activity-runs-mode), which shows the runs pane containing the [runs live region](#runs-live-region) and the open run's detail.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-activity-runs-mode.png
- known-defect: stablemate-01M20X2HWR7MDGSZG3XJSKRYQ0 ambiguous-locator — TreeDir tree-row buttons in the run Files and Diff tabs expose only the bare file/directory name as their accessible name, with no distinguishing prefix, so a repo entry named 'Runs' collides role=button name='Runs' with the always-present activity-rail button — the same defect already seeded for the 'Files' and 'Diff' collisions on this screen (stablemate-01M20X0XEEFYDZQRAKKYET9H4Z, stablemate-01M20WYV4PDZDZQMW55XEA47X4).

### activity-settings-mode

- selector: `.act-btn[data-mode="settings"]`
- role: button
- name: `Settings`
- keyboard: natively focusable with Tab and Shift+Tab.
- verify: visible(locator=".act-btn[data-mode='settings']:focus", text="Settings")
- keyboard: Enter or Space activates the mode switch.
- verify: visible(locator=".app[data-mode='settings']", text="Settings")
- parent: [activity-rail](#activity-rail)
- states: inactive with `aria-pressed="false"` in any other mode.
- verify: visible(locator=".act-btn[data-mode='settings'][aria-pressed='false']", text="Settings")
- states: active with the `active` class and `aria-pressed="true"` when `.app` has `data-mode="settings"`.
- verify: visible(locator=".act-btn[data-mode='settings'].active[aria-pressed='true']", text="Settings")
- states: this is a real, data-dependent accessibility ambiguity, not a mislabeling: any tree row in a run's Files or Diff tab whose name happens to be the literal text `Settings` — a directory or a file ([detail-files-file-row](#detail-files-file-row), [detail-diff-file-row](#detail-diff-file-row)) named `Settings` — renders with the identical `role=button name="Settings"` pair as this always-present rail button, so `getByRole('button', {name: 'Settings'})` cannot distinguish them. The rail button's name cannot be changed without changing the product's navigation label. A repository's file and directory names are arbitrary user data this doc cannot constrain. The collision is therefore left standing rather than papered over with an invented distinguishing label.
- code: groom/groom/assets/dashboard.js::setMode@d01c7d7c3d9c
- dom: icon-only native `<button type="button">` after the rail spacer, at the bottom of the rail; an inline `aria-hidden` gear SVG and no text node.
- leads-to: [select activity settings mode](#select-activity-settings-mode), which shows the settings pane containing the [settings rescan button](#settings-rescan-button) and [settings enable notifications button](#settings-enable-notifications-button).
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-activity-settings-mode.png
- known-defect: stablemate-01M20X4DPRXNNG3RDZEDGSSQHD ambiguous-locator — TreeDir tree-row buttons in the run Files and Diff tabs use the bare file/directory name as their sole accessible name, so a repo entry named 'Settings' collides role=button name='Settings' with the activity-rail's Settings button — already covered by existing seeds stablemate-01M20X2HWR7MDGSZG3XJSKRYQ0 / stablemate-01M20X0XEEFYDZQRAKKYET9H4Z / stablemate-01M20WYV4PDZDZQMW55XEA47X4; activity-settings-mode just needs the matching known-defect bullet.

### runs-filter-input

- selector: `#runs .pane-head input.filter[name="q"]`
- role: searchbox
- name: `Filter runs`
- keyboard: natively focusable with Tab.
- verify: visible(locator="#runs .pane-head input.filter[name='q']:focus", text="Filter runs")
- keyboard: typing filters as you type.
- verify: visible(locator="#runs-list", text="author-002")
- keyboard: the browser's own search-input clear affordance is available.
- verify: visible(locator="#runs .pane-head input.filter[type='search']")
- parent: [groom dashboard](#groom-dashboard)
- states: empty by default.
- verify: visible(locator="#runs .pane-head input.filter[name='q']", text="Filter runs")
- states: an empty query shows the whole pushed fleet.
- verify: visible(locator="#runs-list", text="author-002")
- states: a non-empty query shows only rows whose haystack contains it.
- verify: visible(locator="#runs-list", text="author-002")
- states: haystack matching is case-insensitive.
- verify: visible(locator="#runs-list", text="author-002")
- code: groom/groom/assets/dashboard.js::wireEvents@99f073783401
- code: groom/groom/assets/dashboard.js::rowHaystack@484f5d24f89a
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
- keyboard: not focusable itself.
- verify: absent(subject="#runs-list:focus")
- keyboard: Tab reaches the run rows inside it.
- verify: visible(locator="#runs-list .row[data-worker-id]:focus")
- keyboard: `j`/`k` move the selection without focus leaving the document body.
- verify: visible(locator="#runs-list .row[aria-current='true']")
- parent: [groom dashboard](#groom-dashboard)
- states: `Discovering containers…` while the startup scan runs and nothing has been found.
- verify: visible(locator="#runs-list .empty.loading", text="Discovering containers…")
- states: `No workhorse runs — nothing is running.` when the fleet is empty and the scan is done.
- verify: visible(locator="#runs-list .empty", text="No workhorse runs — nothing is running.")
- states: one [run row](#run-row) per matching run.
- verify: count(subject="#runs-list .row[data-worker-id]", equals=3)
- code: groom/groom/assets/dashboard.js::Fleet@b1dc450f276a
- tests: groom/tests/test_projection.py::test_fleet_rows_include_every_instance
- tests: groom/tests/test_projection.py::test_query_filters_the_fleet
- dom: a shell `<div>` carrying `role="log"`, `aria-live="polite"`, and its label. The Preact island renders *into* it, so the region node itself is never replaced and assistive tech keeps tracking one region across every push.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-runs-live-region.png

### run-row

- selector: `#runs-list .row[data-worker-id]`
- role: button
- one-per: `run` — one row per run in Fleet's filtered `shown` collection.
- name: `{run.repo} #{run.row_id} {run.live_label} {run.doing}`
- unique-by: `run.id` — the distinct Preact `key` assigned by Fleet.
- keyboard: natively focusable with Tab.
- verify: visible(locator="#runs-list .row[data-worker-id]:focus", text="{run.repo} #{run.row_id} {run.live_label} {run.doing}")
- keyboard: Enter or Space selects the run.
- verify: visible(locator="#runs-list .row[data-worker-id].selected[aria-current='true']", text="{run.repo} #{run.row_id} {run.live_label} {run.doing}")
- keyboard: `j` and `k` move the selection down and up from anywhere that is not a text field.
- verify: visible(locator="#runs-list .row[data-worker-id].selected[aria-current='true']", text="{repo} #{short_handle} {liveness} {doing}")
- parent: [runs-live-region](#runs-live-region)
- states: blocked rows carry the `blocked` class.
- verify: visible(locator="#runs-list .row[data-worker-id].blocked", text="{run.repo} #{run.row_id} {run.live_label} {run.doing}")
- states: the open row carries `selected` and `aria-current="true"`.
- verify: visible(locator="#runs-list .row[data-worker-id].selected[aria-current='true']", text="{run.repo} #{run.row_id} {run.live_label} {run.doing}")
- states: every other row omits `aria-current` entirely rather than setting it to `"false"`.
- verify: omits(subject="#runs-list .row[data-worker-id]:not(.selected)", matches="aria-current")
- code: groom/groom/assets/dashboard.js::RowFigures@3c877ee5e531
- code: groom/groom/assets/dashboard.js::RunRow@703c0edbc1b1
- detail: [workflow type badge style rules](../../concepts/workflow-type-badge-style-rules.md)
- tests: `groom/tests/test_dashboard_client.py::test_a_run_row_prints_its_figures_in_words_and_keeps_the_coverage_when_narrowed`
- tests: `groom/tests/test_projection.py::test_fleet_rows_order_blocked_then_live_then_dead_then_finished`
- tests: `groom/tests/test_projection.py::test_run_message_row_matches_the_same_row_in_the_state_message`
- props:
  - `data-worker-id`: the [workflow container](../../concepts/workflow-container.md) id; required; read by the delegated click handler and by `j`/`k` row movement, which walks the rendered rows.
  - `data-state`: one of `blocked`, `running`, `idle`, `finished`; required; styling and row-navigation metadata.
  - `data-live`: the liveness class from the projection; required; may be the unknown value when no telemetry has arrived.
  - `aria-current`: `true` on the open row only; absent otherwise.
- dom: a native `<button type="button">`, keyed by run id so a push preserves focus and scroll. Two lines plus an optional question preview: line one is a state dot, a type badge, the repository label, the short handle, and an optional pulse label; line two is the activity text and an optional mini note that counts up every second from the run's `clock`; the third line, when present, is the [run question preview](../../concepts/run-question-preview.md). A figures line follows it once the run's figures are known: the cost so far with its priced turns out of total turns, the active time and the items done out of the total, as described in [run row figures](../../concepts/run-row-figures.md). The narrowed column beside an open detail keeps the figures line and drops the word `priced`.
- leads-to: [select run row](#select-run-row), which opens that run in the detail pane without leaving this screen.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-run-row.png

### run-row-type-badge

- selector: `#runs-list .row[data-worker-id] .badge[data-type='coder']`
- role: none
- parent: [run-row](#run-row)
- code: groom/groom/assets/dashboard.js::TypeBadge@3d0cdcd50eee
- detail: [workflow type badge style rules](../../concepts/workflow-type-badge-style-rules.md)

### run-row-type-badge-hue

- selector: `#runs-list .row[data-worker-id] .badge[data-type='coder'][style*='--type-hue']`
- role: none
- parent: [run-row-type-badge](#run-row-type-badge)
- code: groom/groom/assets/dashboard.js::TypeBadge@3d0cdcd50eee
- detail: [workflow type badge style rules](../../concepts/workflow-type-badge-style-rules.md)

### detail-pane

- selector: `#detail`
- role: none
- name: none
- keyboard: not focusable itself.
- verify: json_path(path="keyboard.tab_reachable", equals=false)
- keyboard: contains the close control, the answer form and the tabs.
- parent: [groom dashboard](#groom-dashboard)
- states: when nothing is selected, `#detail` is hidden and the run list takes the full width.
- verify: absent(subject="#detail in the accessibility tree while no run is selected")
- states: `Loading telemetry history…` between a selection and its first payload.
- states: `Run not found.` for an id the server does not know.
- states: otherwise the run header renders.
- verify: visible(locator="#detail .detail-head")
- states: otherwise a close control, then the [gate strip](#detail-gate-strip) when a gate is open, then the [detail tabs](#detail-tabs), then the tab's panel.
- verify: visible(locator="#detail-close-button")
- states: the Overview tab is selected first and shows the [run now strip](../../concepts/run-now-strip.md) for a run with a running node, then the [overview tiles](#detail-cost-tile) and the [breakdown table](#detail-flow-table).
- verify: visible(locator="#detail-flow-table", text="Retries")
- states: the Details tab shows the state note, the metrics and the recent telemetry history.
- verify: visible(locator="#detail .live-sec .metrics-grid")
- verify: absent(subject="a working-tree diff disclosure on the Details tab")
- states: a live container run with a connected sidecar, or one whose sidecar dropped after this page read its diff, also has a [Diff tab](#detail-diff-tab) with the run's uncommitted change or its change since the branch started, and a [Files tab](#detail-files-tab) before it with a read-only view of the checkout.
- states: the chosen breakdown view and sort stay across a Details round trip and every live refresh.
- states: the chosen breakdown view and sort reset when another run opens.
- code: groom/groom/assets/dashboard.js::Detail@563f7e2cc72a
- code: groom/groom/assets/dashboard.js::NowStrip@5e02e693e272
- tests: groom/tests/test_projection.py::test_run_detail_carries_gates_head_metrics_and_logs
- dom: a shell `<div>` the detail island renders into. It is refreshed by pushed `detail` frames for the watched run, not by re-fetching.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-detail-pane.png

### detail-run-header

- selector: `#detail .detail-head`
- role: status
- name: `Selected run`
- keyboard: not focusable.
- parent: [detail-pane](#detail-pane)
- states: shows a state dot, type badge, repository label, an optional pulse label, the meta line (`#handle · state · node · pid`), an optional exit hint for a finished run, and an optional current-activity line.
- verify: visible(locator="#detail .detail-head", text="exited")
- states: a container run with a connected sidecar also shows a `docker · sidecar` chip after the run id, and the chip reads `docker` alone when the sidecar drops while a kept diff shows.
- verify: visible(locator="#detail-run-header", text="docker · sidecar")
- code: groom/groom/assets/dashboard.js::RunHead@ffc2c446b5ec
- detail: [workflow type badge style rules](../../concepts/workflow-type-badge-style-rules.md)
- tests: groom/tests/test_diff_tab_dynamic.py::test_the_run_header_carries_a_docker_sidecar_chip_only_while_the_sidecar_is_connected
- tests: groom/tests/test_projection.py::test_exit_hint_only_on_finished_with_a_code
- dom: one of three `role="status"` regions on this page. Each carries its own `aria-label` — this one, the [status bar region](#statusbar-region), and the [connection chip](#connection-chip) — so a screen reader and `getByRole` can tell them apart.
- screenshot: docs/specs/groom-dashboard/vet/run-detail-detail-run-header.png

### detail-gate-question

- selector: `#detail .gate-block .question`
- role: none
- name: none
- keyboard: not focusable; rendered prose.
- parent: [detail-pane](#detail-pane)
- states: one block per open gate, keyed by gate file path, inside the [gate strip](#detail-gate-strip) above the tabs.
- verify: visible(locator="#detail .gate-block .question", text="Use ?")
- states: absent for a run with no open gate.
- states: a no-gate note naming the run's state and node renders on the Details tab when no gate is open.
- verify: visible(locator="#detail .no-gate", text="Nothing to answer")
- code: groom/groom/assets/dashboard.js::GateBlock@0b60fdd379ab
- code: groom/groom/assets/dashboard.js::Markdown@668ebcf50e2b
- tests: groom/tests/test_projection.py::test_gate_question_travels_as_data_not_markup
- tests: groom/tests/test_gate_strip_dynamic.py::test_an_unsafe_question_is_sanitized_before_it_reaches_the_strip
- dom: the gate's question travels as data, never as markup. The client renders it with `marked` and sanitizes the result with DOMPurify before it reaches `innerHTML`, so a script, a frame or an event handler in a question never runs. The gate's node, wait time and file path are plain text on the line above it.
- screenshot: docs/specs/groom-dashboard/vet/run-detail-detail-gate-question.png

### detail-answer-textarea

- selector: `#detail form[data-answer] textarea[name="answer"]`
- role: textbox
- name: `Your answer`
- keyboard: Tab reaches the button.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- keyboard: supports multi-line text entry.
- verify: json_path(path="keyboard.multiline", equals=true)
- keyboard: Enter inserts a newline rather than submitting.
- verify: created(subject="a newline in the textarea")
- parent: [detail-pane](#detail-pane)
- states: empty on render, unless the operator typed into this run's gate box earlier in this page and selected another run, in which case the kept text returns.
- verify: json_path(path="states.on_render.value", equals="")
- states: cleared after a successfully sent answer, and its kept draft goes with it.
- states: keeps what was typed for this run's gate while another run is selected, and shows it again when the operator comes back.
- verify: json_path(path="states.after_reselect.value", equals="draft answer")
- verify: json_path(path="states.after_success.value", equals="")
- states: a rejected send leaves the text in the box.
- verify: json_path(path="states.after_rejected.value", equals="draft answer")
- code: groom/groom/assets/dashboard.js::AnswerForm@8a9e54c1b5c4
- tests: groom/tests/test_a11y_dynamic.py::test_the_answer_form_is_reachable_and_submittable_by_keyboard
- tests: groom/tests/test_gate_above_diff_dynamic.py::test_selecting_another_run_keeps_what_was_typed_for_this_runs_gate_until_it_is_sent
- tests: groom/tests/test_gate_above_diff_dynamic.py::test_the_answer_box_and_send_control_have_roles_names_and_keyboard_operation_and_pass_axe_on_diff_and_files
- dom: two rows, inside a form carrying hidden `cmd`, `workflow_id`, and `file_path` fields. The form is re-rendered on every push, but the gate block is keyed by file path, so Preact reuses the same `<textarea>` DOM node and a half-typed answer survives. Each gate's draft belongs to that gate alone. The text is also kept in a page-held draft keyed by run and gate, and a newly mounted box restores it.
- screenshot: docs/specs/groom-dashboard/vet/run-detail-detail-answer-textarea.png

### detail-send-answer-button

- selector: `#detail form[data-answer] button[type="submit"]`
- role: button
- name: `Send answer`
- verify: visible(locator="#detail form[data-answer] button[type='submit']", text="Send answer")
- keyboard: natively focusable with Tab.
- verify: visible(locator="#detail form[data-answer] button[type='submit']:focus", text="Send answer")
- keyboard: Enter or Space submits the form, as does Enter from any single-line field in it.
- verify: count(subject="WebSocket sends after Enter or Space submits the answer form", equals=1)
- parent: [detail-pane](#detail-pane)
- exclusive-with: [detail-files-file-row](#detail-files-file-row), [detail-diff-file-row](#detail-diff-file-row)
- states: always enabled. The result is reported by a toast, not by a disabled state.
- verify: json_path(path="answer_button.disabled", equals=false)
- states: this button lives in the runs pane, one of the four `data-mode` panes described in [Layout](#layout).
- verify: visible(locator=".app[data-mode='runs'] #runs-pane #detail form[data-answer] button[type='submit']", text="Send answer")
- states: `data-mode` selects a single active pane, and inactive panes are `display:none`, removed from the accessibility tree entirely — so this button disappears whenever `data-mode` is not `runs`.
- verify: absent(subject="#detail form[data-answer] button[type='submit'] in the accessibility tree when `data-mode` is not `runs`")
- states: it can never co-render with the run Files tab's [detail-files-file-row](#detail-files-file-row) or the run Diff tab's [detail-diff-file-row](#detail-diff-file-row) — the mode exclusivity, not a coincidence of naming, is what `getByRole('button', {name: 'Send answer'})` can rely on.
- verify: count(subject="elements matching role=button name='Send answer' in the rendered DOM", equals=1)
- code: groom/groom/assets/dashboard.js::AnswerForm@8a9e54c1b5c4
- leads-to: [send detail answer](#send-detail-answer), which serializes the form and sends it over the dashboard websocket.
- screenshot: docs/specs/groom-dashboard/vet/run-detail-detail-send-answer-button.png

### detail-metrics-grid

- selector: `#detail .live-sec .metrics-grid`
- role: none
- name: none
- keyboard: not focusable.
- verify: json_path(path="keyboard.tab_reachable", equals=false)
- parent: [detail-pane](#detail-pane)
- states: this grid lives on the Details tab and is absent while the Overview tab is selected.
- states: `No telemetry for this run — it is either pre-OTel or exporting to another collector.` when the run has none.
- verify: visible(locator="#detail .live-sec .fd-empty", text="No telemetry for this run — it is either pre-OTel or exporting to another collector.")
- states: a grid of key/value cells in the projection's order, followed by an optional footer of fired alert-rule chips and the run directory when telemetry is present.
- verify: visible(locator="#detail .live-sec .metrics-grid .metric:first-child .m-k", text="node")
- verify: visible(locator="#detail .live-sec .metrics-grid", text="review")
- code: groom/groom/assets/dashboard.js::Metrics@569f79650c93
- tests: groom/tests/test_projection.py::test_run_metrics_cell_order_is_the_layout
- tests: groom/tests/test_projection.py::test_run_metrics_merges_hot_cache_and_durable_facts

### detail-log-trail

- selector: `#detail .live-sec .log-line`
- role: none
- name: none
- keyboard: not focusable.
- parent: [detail-pane](#detail-pane)
- states: `No log lines for this run (workhorse ships in-process script logs over OTLP).` when empty.
- verify: visible(locator="#detail .live-sec .log-trail .fd-empty", text="No log lines for this run (workhorse ships in-process script logs over OTLP).")
- states: capped, newest-first lines, each a timestamp, severity, node, and body when logs are present.
- verify: visible(locator="#detail .live-sec .log-line:first-child .lt-body", text="boom")
- verify: count(subject="#detail .live-sec .log-line", equals=60)
- code: groom/groom/assets/dashboard.js::LogTrail@07025b1cc4e9
- tests: groom/tests/test_projection.py::test_log_trail_newest_first_with_severity_classes
- tests: groom/tests/test_projection.py::test_log_trail_is_capped

### detail-close-button

- selector: `button.close-detail`
- role: button
- name: `Close run detail`
- verify: visible(locator="#detail-close-button", text="Close")
- keyboard: natively focusable with Tab.
- keyboard: Enter or Space activates it.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- parent: [detail-pane](#detail-pane)
- states: always enabled while a run is open.
- states: it stays at the top right of the head's first row, with the run's doing line on the row below it.
- code: groom/groom/assets/dashboard.js::RunHead@13be7a1c6eb7
- tests: groom/tests/test_a11y_dynamic.py::test_selecting_a_run_narrows_the_list_and_close_restores_it_with_its_filter
- leads-to: [close run detail](#close-run-detail), which clears the selection and returns the list to full width.

### detail-tabs

- selector: `div.dtablist`
- role: tablist
- name: `Run detail`
- keyboard: the selected tab is the one tab stop. ArrowLeft and ArrowRight move to the other tab, select it and move focus to it.
- verify: json_path(path="keyboard.arrow_keys_switch_tabs", equals=true)
- parent: [detail-pane](#detail-pane)
- states: two tabs, `Overview` and `Details`, each with role tab and `aria-selected`, plus a `Files` tab and a `Diff` tab after them, while the run is a live container run with a connected sidecar. Overview is selected when a run opens.
- verify: visible(locator="#detail-tabs", text="Overview")
- states: the selected tab controls the single tabpanel `#detail-panel`, whose accessible name is the selected tab's.
- states: the Diff tab adds the [diff view switch](#detail-diff-view-switch) at the right of the bar.
- states: the Files and Diff tabs add the [checkout selector](#detail-checkout-select) for a run with several checkouts.
- code: groom/groom/assets/dashboard.js::DetailTabs@7758bd0de773
- tests: groom/tests/test_a11y_dynamic.py::test_tabs_switch_with_the_arrow_keys_and_details_keeps_todays_content
- tests: groom/tests/test_diff_tab_dynamic.py::test_diff_tab_controls_have_roles_names_and_keyboard_operation_and_pass_axe
- leads-to: [switch detail tab](#switch-detail-tab), which swaps the panel's content.

### detail-gate-strip

- selector: `div.gate-strip`
- role: region
- name: `Open gates`
- placement: width 60-80%, x 20-40%
- keyboard: contains each gate's answer form, reachable with Tab in document order before the tabs.
- keyboard: the `Collapse` button folds the strip to one line, and the `Answer` button on that line unfolds it.
- verify: json_path(path="keyboard.collapse_button_folds", equals=true)
- keyboard: collapsing moves focus to `Answer`.
- keyboard: expanding moves focus to the first answer box.
- parent: [detail-pane](#detail-pane)
- states: present only while the run has an open gate, above the tabs and outside the tab's scrolling region, so it stays in view while either tab scrolls.
- verify: visible(locator="#detail-gate-strip", text="Send answer")
- states: lists the selected run's open gates and no others. A gate renders here only, never also inside a tab.
- states: each block is the [gate question](#detail-gate-question) with its [answer textarea](#detail-answer-textarea) and [send button](#detail-send-answer-button), so the operator answers without leaving the tab they are on. Two open gates show two blocks, with one `Collapse` button for the whole strip in the first block's header row.
- states: collapsed, it is one line with a state dot, `Waiting on you`, the start of the first question, the time waited when known, and an `Answer` button.
- verify: visible(locator="#detail-gate-strip", text="Answer")
- states: with more than one open gate the collapsed line says how many are open.
- states: a gate that opens while the strip is collapsed raises that count.
- states: the collapsed state stays while the same run stays selected and resets when another run opens or the detail closes.
- states: when the strip appears, grows, collapses or clears, the open tab's content stays where it was on screen, because the scroll position moves by the strip's height change.
- states: its height is capped at half the pane and it scrolls inside that cap.
- code: groom/groom/assets/dashboard.js::GateStrip@5921a2b7243b
- code: groom/groom/assets/dashboard.js::useHoldPlace@5e6b749cb8ef
- detail: [run gate strip](../../concepts/run-gate-strip.md)
- tests: groom/tests/test_a11y_dynamic.py::test_a_blocked_runs_gate_sits_above_the_tabs_and_can_be_answered_there
- tests: groom/tests/test_gate_strip_dynamic.py::test_the_strip_stays_above_the_tabs_while_a_tab_scrolls
- tests: groom/tests/test_gate_strip_dynamic.py::test_a_gate_that_opens_while_the_operator_reads_leaves_the_text_where_it_was
- tests: groom/tests/test_gate_strip_dynamic.py::test_two_open_gates_both_show_with_their_own_question_and_box
- tests: groom/tests/test_gate_strip_dynamic.py::test_the_strip_collapses_to_one_line_with_the_start_of_the_question_and_expands_again
- tests: groom/tests/test_gate_strip_dynamic.py::test_a_gate_that_opens_while_collapsed_is_counted_on_the_collapsed_line

### detail-cost-tile

- selector: `div.kpis`
- role: none
- name: none
- keyboard: not focusable.
- verify: json_path(path="keyboard.tab_reachable", equals=false)
- parent: [detail-pane](#detail-pane)
- states: on the Overview tab, shows the cost so far, the priced turns out of the total turns (`2 of 3 turns priced`), and `as of the last finished turn`.
- verify: visible(locator="#detail-cost-tile", text="2 of 3 turns priced")
- verify: visible(locator="#detail-cost-tile", text="as of the last finished turn")
- states: the tiles are Cost so far, Active time, Work items, Agent turns and Attention, as described by [overview tiles](../../concepts/overview-tiles.md).
- verify: visible(locator="#detail-active-tile", text="wall")
- verify: visible(locator="#detail-turns-tile", text="backend retry")
- verify: visible(locator="#detail-attention-tile", text="problem")
- states: the cost tile adds `per active hour`, and the attention tile counts its waiting time up every second beside the tree's waiting mark.
- verify: visible(locator="#detail-cost-tile", text="per active hour")
- states: a backend that reports no cost says `reports no cost` and shows no dollar figure, never `$0` and never a blank. It may show the estimate as `est $X at list price`.
- verify: visible(locator="#detail-cost-tile", text="reports no cost")
- states: a run with no finished node says `Figures appear when the first node finishes` and shows its running node.
- states: that run shows no tiles, no problem count and none of the run clock sections.
- states: that run still shows the Run facts list, so a native run's checkout path is there from its first moment.
- states: below the tiles, the Overview shows the wall clock bar with its legend of six segments, the Models table, the Run facts list with a copy button per fact, and the Sessions table, as described by [run clock sections](../../concepts/run-clock-sections.md).
- states: a copy button answers `Copied run id` in text a status region announces, or `Could not copy run id` when the write fails.
- verify: visible(locator="#detail-cost-tile", text="Figures appear when the first node finishes")
- states: while the figures load, a status named `Reading this run's figures…` shows and clears when they arrive.
- states: when a span batch commits, the cost, its coverage and the flow table update in place with no action from the operator.
- states: a refresh keeps the scroll position and does not blank the figures it replaces.
- states: the `ago` after `as of the last finished turn` counts up every second in the browser.
- code: groom/groom/assets/dashboard.js::CostTile@56646cae6525
- code: groom/groom/assets/dashboard.js::OverviewTiles@1e3959a72410
- detail: [run clock sections](../../concepts/run-clock-sections.md)
- detail: [run flow tree](../../concepts/run-flow-tree.md)
- tests: groom/tests/test_a11y_dynamic.py::test_new_telemetry_updates_the_open_overview_and_keeps_the_operators_place
- tests: groom/tests/test_a11y_dynamic.py::test_the_time_since_the_last_finished_turn_counts_up_every_second
- tests: groom/tests/test_a11y_dynamic.py::test_overview_shows_real_cost_coverage_and_the_flow_tree

### detail-flow-table

- selector: `table.tt`
- role: table
- name: `Time and cost per flow`
- keyboard: each expandable row has a toggle button, reachable with Tab, activated with Enter or Space.
- parent: [detail-pane](#detail-pane)
- states: the name follows the chosen view: `Time and cost per node` for By node and `Time and cost per work item` for By work item.
- states: a button group named `Breakdown view` switches the table between By flow, By node and By work item, with By flow the default. By work item appears only when the run has a work item. Each button exposes its pressed state and works from the keyboard.
- verify: visible(locator="#detail-flow-table", text="By node")
- states: a second group named `Sort by` orders By flow and By node by time or by cost, with no fetch. By work item has no sort.
- states: By node lists each node with kind, visits, time, mean, longest visit, cost, cost share and retries.
- states: By node compares each mean with the workflow's median under a heading `vs median of N`.
- states: By node leaves the comparison blank under a heading `vs median: N runs, under five` when fewer than five runs compare.
- states: By work item lists each item with passes, agent time, cost and outcome.
- states: By work item marks the open item.
- states: By work item ends with an `outside any work item` row and a Total row.
- states: rows follow the [run flow tree](../../concepts/run-flow-tree.md): flow, state, node, with visits, time and cost on each. A Retries column counts that node's backend retries. Flows start expanded and states collapsed. Each Time cell shows the duration with a thin bar for its share of the run's time.
- states: a refresh keeps every row the operator expanded or collapsed, and keeps the table's rows mounted, so nothing flashes.
- verify: visible(locator="#detail-flow-table", text="Retries")
- states: when the run reports no cost the cost column is replaced by an `Output tokens` column.
- verify: visible(locator="#detail-flow-table", text="Output tokens")
- states: finished work whose parent flow or state never ended sits under a row labelled `Unfinished flow or state`, one row per missing parent.
- verify: visible(locator="#detail-flow-table", text="Unfinished flow or state")
- states: the running node is a top-level row marked `running` with its running time, which counts up every second. A node held at an operator gate is marked `waiting on the operator` with the time waited, not as running.
- verify: visible(locator="#detail-flow-table", text="waiting on the operator")
- code: groom/groom/assets/dashboard.js::FlowTree@e745c6d8a91d
- detail: [run breakdown views](../../concepts/run-breakdown-views.md)
- detail: [run flow tree](../../concepts/run-flow-tree.md)
- tests: groom/tests/test_a11y_dynamic.py::test_the_node_waiting_on_the_operator_is_marked_in_words_not_as_running
- tests: groom/tests/test_a11y_dynamic.py::test_a_running_node_is_marked_running_with_its_time
- tests: groom/tests/test_a11y_dynamic.py::test_the_time_cell_carries_a_proportional_bar_beside_the_duration

### detail-overview-retry-button

- selector: `button.retry-overview`
- role: button
- name: `Retry now`
- keyboard: natively focusable with Tab.
- keyboard: Enter or Space activates it.
- verify: visible(locator="#detail-overview-retry-button", text="Retry now")
- parent: [detail-pane](#detail-pane)
- states: shown inside an alert, only while the Overview read has failed. The Details tab keeps working meanwhile, and the alert clears on the next successful read.
- code: groom/groom/assets/dashboard.js::Overview@f656729cd4fc
- tests: groom/tests/test_a11y_dynamic.py::test_overview_says_it_is_reading_then_offers_a_retry_when_the_read_fails
- leads-to: [get run overview](../../http/get-run-overview.md), requested again.

### settings-rescan-button

- selector: `#btn-refresh`
- role: button
- name: `Rescan containers`
- keyboard: natively focusable with Tab.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- keyboard: Enter or Space triggers the rescan.
- verify: json_path(path="keyboard.enter_or_space_triggers_rescan", equals=true)
- parent: [groom dashboard](#groom-dashboard)
- exclusive-with: [detail-files-file-row](#detail-files-file-row), [detail-diff-file-row](#detail-diff-file-row)
- states: idle.
- verify: json_path(path="states.idle", equals=true)
- states: while a rescan is in flight it carries `data-busy`.
- verify: json_path(path="states.in_flight.data_busy", equals=true)
- states: while a rescan is in flight it carries the `spinning` class.
- verify: json_path(path="states.in_flight.spinning", equals=true)
- states: further activations are ignored until the request settles.
- verify: json_path(path="states.in_flight.activations_ignored", equals=true)
- states: this control lives in the settings pane, one of the four `data-mode` panes described in [Layout](#layout).
- verify: absent(subject="#btn-refresh in the accessibility tree when `data-mode` is not `settings`")
- states: `data-mode` selects a single active pane and inactive panes are `display:none`, removed from the accessibility tree entirely. So it can never co-render with the run Files tab's [detail-files-file-row](#detail-files-file-row) or the run Diff tab's [detail-diff-file-row](#detail-diff-file-row) — the mode exclusivity, not a coincidence of naming, is what `getByRole('button', {name: 'Rescan containers'})` can rely on.
- verify: count(subject="elements matching role=button name='Rescan containers' in the rendered DOM", equals=1)
- code: groom/groom/assets/dashboard.js::doRefresh@622b51370ad0
- detail: [dashboard rescan control selection](../../concepts/dashboard-rescan-control-selection.md)
- dom: a text button in the settings pane, beside the explanatory line `Re-run the docker discovery pass.`
- leads-to: [rescan containers from settings](#rescan-containers-from-settings).
- screenshot: docs/specs/groom-dashboard/vet/settings-settings-rescan-button.png

### settings-enable-notifications-button

- selector: `#btn-notify`
- role: button
- name: `Enable notifications`
- keyboard: natively focusable with Tab.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- keyboard: Enter or Space requests the browser permission.
- verify: json_path(path="keyboard.enter_or_space_requests_permission", equals=true)
- parent: [groom dashboard](#groom-dashboard)
- exclusive-with: [detail-files-file-row](#detail-files-file-row), [detail-diff-file-row](#detail-diff-file-row)
- states: static — the label does not change with the permission state.
- verify: json_path(path="states.label", equals="static across permission states")
- states: the browser owns the permission prompt and the answer.
- verify: json_path(path="states.permission_prompt_owner", equals="browser")
- states: this control lives in the settings pane, one of the four `data-mode` panes described in [Layout](#layout).
- verify: visible(locator=".app[data-mode='settings'] #btn-notify", text="Enable notifications")
- states: `data-mode` selects a single active pane and inactive panes are `display:none`, removed from the accessibility tree entirely — so this control disappears whenever `data-mode` is not `settings`.
- verify: absent(subject="#btn-notify in the accessibility tree when `data-mode` is not `settings`")
- states: it can never co-render with the run Files tab's [detail-files-file-row](#detail-files-file-row) or the run Diff tab's [detail-diff-file-row](#detail-diff-file-row) — the mode exclusivity, not a coincidence of naming, is what `getByRole('button', {name: 'Enable notifications'})` can rely on.
- verify: count(subject="elements matching role=button name='Enable notifications' in the rendered DOM", equals=1)
- code: groom/groom/assets/dashboard.js::wireEvents@99f073783401
- dom: a ghost button in the settings pane, beside `Browser alerts when a worker blocks.`
- leads-to: [enable browser notifications from settings](#enable-browser-notifications-from-settings), which asks for [browser notification permission](../../concepts/browser-notification-permission.md).
- screenshot: docs/specs/groom-dashboard/vet/settings-settings-enable-notifications-button.png

### statusbar-region

- selector: `#statusbar`
- role: status
- name: `Fleet status`
- keyboard: not focusable itself.
- verify: json_path(path="keyboard.focusable", equals=false)
- keyboard: contains the refresh and palette buttons.
- verify: json_path(path="keyboard.child_controls", equals="refresh and palette buttons")
- parent: [groom dashboard](#groom-dashboard)
- states: four state counts in the order blocked, running, idle, finished.
- verify: visible(locator="#statusbar", text="1 blocked 2 running 1 idle 0 finished")
- states: the repo and worker totals.
- verify: visible(locator="#statusbar", text="repos · workers")
- states: the connection chip.
- verify: visible(locator="#statusbar .stat.conn", text="Connection:")
- states: the refresh control.
- verify: visible(locator="#btn-refresh-bar", text="Rescan containers")
- states: the palette button.
- verify: visible(locator="#btn-palette", text="Open command palette")
- code: groom/groom/assets/dashboard.js::StatusBar@e4ee89746df9
- tests: `groom/tests/test_projection.py::test_status_bar_counts_states`
- dom: a shell `<div>` with `role="status"`, `aria-live="polite"`, and its own `aria-label`. It is one of three `role="status"` regions on this page; each is named so they are distinguishable.
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-statusbar-region.png

### connection-chip

- selector: `#statusbar .stat.conn`
- role: status
- name: `Connection: ` followed by the current phase word — `live`, `stale`, `reconnecting`, or `offline`.
- keyboard: not focusable.
- verify: visible(locator="#statusbar .stat.conn", text="live")
- keyboard: it is a report, not a control.
- verify: visible(locator="#statusbar .stat.conn", text="Connection:")
- parent: [statusbar-region](#statusbar-region)
- states: `live` while a frame has arrived within the last 15 seconds.
- verify: visible(locator="#statusbar .stat.conn", text="live")
- states: `stale` when the socket is open but has been silent longer.
- verify: visible(locator="#statusbar .stat.conn", text="stale")
- states: `reconnecting` for the first 60 seconds after the socket closes, while backoff is in flight.
- verify: visible(locator="#statusbar .stat.conn", text="reconnecting")
- states: `offline` beyond that.
- verify: visible(locator="#statusbar .stat.conn", text="offline")
- states: `connecting` is the value the store starts with, before the first evaluation.
- verify: visible(locator="#statusbar .stat.conn", text="connecting")
- code: groom/groom/assets/dashboard.js::ConnectionChip@757d408bd3e5
- code: groom/groom/assets/dashboard.js::deriveConnection@691102b69424
- tests: groom/tests/test_connection_state.py::test_the_full_live_to_stale_to_offline_progression
- tests: groom/tests/test_connection_state.py::test_open_but_silent_socket_goes_stale_and_starts_resyncing
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
- keyboard: natively focusable with Tab.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- keyboard: Enter or Space triggers the rescan.
- verify: json_path(path="keyboard.enter_or_space_triggers_rescan", equals=true)
- parent: [statusbar-region](#statusbar-region)
- states: idle.
- verify: json_path(path="states.idle", equals=true)
- states: `data-busy` and the `spinning` class while a rescan is in flight, during which further activations are ignored.
- verify: json_path(path="states.busy_ignores_further_activations", equals=true)
- states: this is a real, data-dependent accessibility ambiguity, not a mislabeling: any tree row in a run's Files or Diff tab whose name happens to be the literal text `Rescan containers (reconcile + prune)` — a directory or a file ([detail-files-file-row](#detail-files-file-row), [detail-diff-file-row](#detail-diff-file-row)) named `Rescan containers (reconcile + prune)` — renders with the identical `role=button name="Rescan containers (reconcile + prune)"` pair as this always-present statusbar button, and `getByRole('button', {name: 'Rescan containers (reconcile + prune)'})` cannot distinguish them.
- verify: count(subject="elements matching role=button name='Rescan containers (reconcile + prune)'", equals=2)
- states: the button's name cannot be changed without changing the product's rescan-control label.
- states: a repository's file and directory names are arbitrary user data this doc cannot constrain, so the collision is left standing rather than papered over with an invented distinguishing label.
- code: groom/groom/assets/dashboard.js::doRefresh@622b51370ad0
- detail: [dashboard rescan control selection](../../concepts/dashboard-rescan-control-selection.md)
- dom: an icon-only button holding an `aria-hidden` glyph, named longer than the settings-pane control it duplicates so the two are distinguishable when settings mode puts both on screen at once.
- leads-to: [rescan containers from statusbar](#rescan-containers-from-statusbar).
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-statusbar-refresh-button.png
- known-defect: stablemate-01M20XNEBBV75RW14AR65GRJ0K ambiguous-locator — TreeDir and the run tabs' leaf buttons name tree-row buttons with only the bare directory/file text and no aria-label, so an entry literally named 'Rescan containers (reconcile + prune)' collides role=button+name with statusbar-refresh-button — same defect already seeded as stablemate-01M20X2HWR7MDGSZG3XJSKRYQ0 / stablemate-01M20X0XEEFYDZQRAKKYET9H4Z / stablemate-01M20WYV4PDZDZQMW55XEA47X4 / stablemate-01M20X67QXFMXFWTHH9P1HXGNR / stablemate-01M20X4DPRXNNG3RDZEDGSSQHD / stablemate-01M20XKJESQCSY28H8B7EAM7CX / stablemate-01M20XBE01AW90EEXHSYVP8J1J for the same screen's other collision targets.

### command-palette-open-button

- selector: `#btn-palette`
- role: button
- name: `Open command palette`
- keyboard: Tab reaches the button.
- verify: json_path(path="$.activeElement", equals="#btn-palette")
- keyboard: Enter or Space opens the palette.
- verify: visible(locator="#palette", text="Command palette")
- keyboard: `Ctrl+K` or `Meta+K` opens it from anywhere on the page.
- verify: visible(locator="#palette", text="Command palette")
- parent: [statusbar-region](#statusbar-region)
- states: static. Opening records the invoker so focus returns here on close.
- states: this is a real, data-dependent accessibility ambiguity, not a mislabeling: any tree row in a run's Files or Diff tab whose name happens to be the literal text `Open command palette` — a directory or a file ([detail-files-file-row](#detail-files-file-row), [detail-diff-file-row](#detail-diff-file-row)) named `Open command palette` — renders with the identical `role=button name="Open command palette"` pair as this always-present statusbar button, and `getByRole('button', {name: 'Open command palette'})` cannot distinguish them.
- verify: count(subject="elements matching role=button name='Open command palette'", equals=2)
- states: the button's name cannot be changed without changing the product's shortcut-hint label, and a repository's file or directory name is arbitrary data outside this doc's control, so the collision is left standing rather than papered over with an invented distinguishing label.
- code: groom/groom/assets/dashboard.js::openPalette@ab1a5517a248
- detail: [command palette opening](../../concepts/command-palette-opening.md)
- dom: shows the `⌘K` hint as an `aria-hidden` glyph beside the word `palette`; the accessible name comes from `aria-label` so the shortcut glyph is never read out as text.
- leads-to: [toggle command palette shortcut](#toggle-command-palette-shortcut).
- screenshot: docs/specs/groom-dashboard/vet/post-discovery-command-palette-open-button.png
- known-defect: stablemate-01M20X81BGCYQRWEAS1BX191P3 ambiguous-locator — Run Files and Diff tab tree rows (TreeDir and the leaf buttons in groom/groom/assets/dashboard.js) expose the bare path segment as their only accessible name on role=button, letting a repo file/directory literally named after a static control's label (e.g. "Open command palette", "Rescan containers (reconcile + prune)") collide with that control under getByRole; needs a scoped accessible name (prefix or a distinguishing role) on tree rows.

### command-palette-dialog

- selector: `#palette`
- role: dialog
- name: `Command palette`
- placement: width 95-100%, x 0-5%
- keyboard: Escape closes it.
- verify: absent(subject="command palette dialog")
- keyboard: while it is open Tab is trapped on its input, which is its only focusable element.
- verify: json_path(path="$.activeElement", equals="#palette-input")
- parent: [groom dashboard](#groom-dashboard)
- states: closed by default.
- verify: absent(subject="command palette dialog on initial load")
- states: `open` on the wrapper while shown.
- verify: visible(locator="#palette", text="Command palette")
- states: closing returns focus to whatever opened it rather than dropping it to `<body>`.
- verify: json_path(path="$.activeElement", equals="#btn-palette")
- code: groom/groom/assets/dashboard.js::openPalette@ab1a5517a248
- code: groom/groom/assets/dashboard.js::closePalette@039308c89fc9
- detail: [command palette opening](../../concepts/command-palette-opening.md)
- dom: `aria-modal="true"`. The trap is one element wide on purpose — there is nothing else in the dialog to reach. `groom/groom/assets/dashboard.css` fixes the dialog wrapper to all viewport edges, so it spans the viewport rather than only the centered palette box inside it.
- screenshot: docs/specs/groom-dashboard/vet/command-palette-command-palette-dialog.png

### command-palette-input

- selector: `#palette-input`
- role: combobox
- name: `Jump to a worker or blocked gate`
- keyboard: focused automatically on open.
- verify: json_path(path="$.activeElement", equals="#palette-input")
- keyboard: ArrowDown and ArrowUp move the active result.
- verify: json_path(path="$.aria-activedescendant", equals="presult-1")
- keyboard: Enter chooses the active result.
- verify: visible(locator="#detail .detail-head", text="{repo} #{short_handle}")
- keyboard: Escape closes the palette.
- verify: absent(subject="command palette dialog")
- parent: [command-palette-dialog](#command-palette-dialog)
- states: cleared on every open.
- verify: json_path(path="$.value", equals="")
- states: `aria-expanded` is true while the palette is open.
- verify: json_path(path="$.aria-expanded", equals="true")
- states: `aria-expanded` is false while the palette is closed.
- verify: json_path(path="$.aria-expanded", equals="false")
- states: `aria-activedescendant` points at the active result.
- verify: json_path(path="$.aria-activedescendant", matches="^presult-[0-9]+$")
- states: `aria-activedescendant` is removed when nothing matches.
- verify: json_path(path="$.aria-activedescendant", absent=true)
- code: groom/groom/assets/dashboard.js::PaletteResults@fb2140639a3c
- code: groom/groom/assets/dashboard.js::movePaletteActive@75aa0822155a
- detail: [command palette result presentation](../../concepts/command-palette-result-presentation.md)
- screenshot: docs/specs/groom-dashboard/vet/command-palette-command-palette-input.png

### command-palette-results-listbox

- selector: `#palette-results`
- role: listbox
- name: `Workers`
- keyboard: not focusable itself.
- verify: json_path(path="$.activeElement", equals="#palette-input")
- keyboard: driven from the palette input via `aria-activedescendant`.
- verify: json_path(path="$.aria-activedescendant", matches="^presult-[0-9]+$")
- parent: [command-palette-dialog](#command-palette-dialog)
- states: every run in the fleet when the query is empty.
- verify: visible(locator="#palette-results", text="{repo} #{short_handle}")
- states: the matching subset when the query is non-empty.
- verify: visible(locator="#palette-results", text="{repo} #{short_handle}")
- states: empty when nothing matches.
- verify: count(subject="command palette results", equals=0)
- code: groom/groom/assets/dashboard.js::PaletteResults@fb2140639a3c
- detail: [command palette result presentation](../../concepts/command-palette-result-presentation.md)
- screenshot: docs/specs/groom-dashboard/vet/command-palette-command-palette-results-listbox.png

### command-palette-result

- selector: `#palette-results .presult[role="option"]`
- role: option
- one-per: `run` — one result per run in the store-backed palette hit list.
- name: `{run.repo} #{run.row_id} {run.doing} {run.hint}`
- unique-by: `run.id` — the `key` used for each rendered result.
- keyboard: not individually focusable.
- verify: json_path(path="$.activeElement", equals="#palette-input")
- keyboard: reached with ArrowDown and ArrowUp.
- verify: json_path(path="$.aria-activedescendant", equals="presult-1")
- keyboard: chosen with Enter.
- verify: visible(locator="#detail .detail-head", text="{repo} #{short_handle}")
- keyboard: pointer click chooses it directly.
- verify: visible(locator="#detail .detail-head", text="{repo} #{short_handle}")
- parent: [command-palette-results-listbox](#command-palette-results-listbox)
- states: the hint is `gate` for blocked runs.
- states: the hint is the run's live value when present, or its state otherwise.
- states: `aria-selected="true"` on the active result.
- verify: json_path(path="$.aria-selected", equals="true")
- states: `aria-selected="false"` on the rest.
- verify: json_path(path="$.aria-selected", equals="false")
- states: the active result is scrolled into view on each render.
- verify: visible(locator="#palette-results .presult[aria-selected='true']", text="{repo} #{short_handle}")
- code: groom/groom/assets/dashboard.js::PaletteResults@fb2140639a3c
- code: groom/groom/assets/dashboard.js::paletteHits@8c050d08b6fa
- detail: [command palette result presentation](../../concepts/command-palette-result-presentation.md)
- props:
  - `id`: `presult-{index}`; required; the target of the palette input's `aria-activedescendant`.
- dom: keyed by run id. The hit list is computed from the fleet **in the store**, not from the rendered rows, so the palette finds a run the runs-pane filter is currently hiding.
- leads-to: [select command palette result](#select-command-palette-result).
- screenshot: docs/specs/groom-dashboard/vet/command-palette-command-palette-result.png

### toast-region

- selector: `#toasts`
- role: alert
- name: none
- keyboard: not focusable.
- verify: json_path(path="keyboard.focusable", equals=false)
- keyboard: not dismissible by hand.
- verify: json_path(path="keyboard.dismissible", equals=false)
- parent: [groom dashboard](#groom-dashboard)
- states: empty most of the time.
- verify: json_path(path="states.empty_most_of_time", equals=true)
- states: one entry per blocked notification, answer confirmation or refused answer.
- verify: json_path(path="states.entries", equals="one per blocked notification, answer confirmation or refused answer")
- states: removed on its own timer — seven seconds for a block.
- verify: json_path(path="states.expiration.blocked_seconds", equals=7)
- states: removed on its own timer — three and a half seconds for a confirmation.
- verify: json_path(path="states.expiration.confirmation_seconds", equals=3.5)
- code: groom/groom/assets/dashboard.js::pushToast@f1678abc58fe
- dom: `aria-live="assertive"`, because a worker blocking is the one thing on this page worth interrupting for. Titles and bodies are set as text nodes, never as markup.

### detail-active-tile

- selector: `#detail-active-tile`
- role: none
- name: none
- keyboard: not focusable.
- verify: json_path(path="keyboard.tab_reachable", equals=false)
- parent: [detail-pane](#detail-pane)
- states: the Active time tile shows the active time and, beside it, the wall time and the session count, as `<wall> wall, N sessions`.
- detail: [overview tiles](../../concepts/overview-tiles.md)

### detail-turns-tile

- selector: `#detail-turns-tile`
- role: none
- name: none
- keyboard: not focusable.
- verify: json_path(path="keyboard.tab_reachable", equals=false)
- parent: [detail-pane](#detail-pane)
- states: the Agent turns tile shows the turn count and the backend retries.
- detail: [overview tiles](../../concepts/overview-tiles.md)

### detail-attention-tile

- selector: `#detail-attention-tile`
- role: none
- name: none
- keyboard: not focusable.
- verify: json_path(path="keyboard.tab_reachable", equals=false)
- parent: [detail-pane](#detail-pane)
- states: the Attention tile shows the gates, the time spent waiting on them and the problem count.
- detail: [overview tiles](../../concepts/overview-tiles.md)

### detail-diff-tab

- selector: `#tab-diff`
- role: tab
- name: Diff
- keyboard: ArrowLeft and ArrowRight reach it from Details.
- verify: json_path(path="keyboard.arrow_keys_reach_diff", equals=true)
- keyboard: Enter or Space on it selects it.
- verify: json_path(path="keyboard.enter_selects_diff", equals=true)
- parent: [detail-tabs](#detail-tabs)
- states: present for a live container run whose row says a sidecar is connected, and, while the sidecar is down, for a run whose diff this page already read.
- states: a native run, an ended run and a container run without a connected sidecar and without a diff read in this page have no Diff tab.
- verify: visible(locator="#detail-diff-tab", text="Diff")
- verify: absent(subject="#detail-diff-tab for a native run, an ended run, or a container run without a connected sidecar")
- states: the tab appears within 5 seconds of the sidecar connecting, without a reload.
- states: the tab goes when the run ends, and the Overview tab shows if Diff was open.
- states: when the sidecar disconnects and this page holds a diff it read for the run, the tab stays and carries a `stale` chip.
- states: the stale tab's accessible name reads `Diff, stale`.
- states: with no diff held, the tab goes as for a run without a sidecar.
- verify: visible(locator="#detail-diff-tab", text="stale")
- states: a run first selected after its sidecar dropped, and a run after a reload, show no Diff tab.
- states: the tab shows the diff of the checkout chosen with the [checkout selector](#detail-checkout-select), in the view chosen with the [diff view switch](#detail-diff-view-switch), and its size follows both choices.
- states: the accessible name reads `Diff, N lines added, M lines removed` while the tracked change is not empty.
- states: a clean checkout, or one with only untracked files, shows no count on the tab. So does a Since branch start view that is loading, empty, unreadable, or without a base.
- verify: absent(subject="#detail-diff-count for a clean checkout")
- states: Diff content goes through diff2html, which escapes file content, so a changed file cannot inject markup.
- verify: omits(subject="rendered run diff", matches="<script")
- code: groom/groom/assets/dashboard.js::DetailTabs@c23c8518540f
- code: groom/groom/assets/dashboard.js::useRunDiff@42e89852f3e2
- code: groom/groom/assets/dashboard.js::loadRunDiff@6b1e2d0423d6
- code: groom/groom/projection.py::run_row@f4041c085d72
- detail: [run Diff tab](../../concepts/run-diff-tab.md)
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_container_run_with_a_connected_sidecar_has_a_diff_tab_beside_overview_and_details
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_native_run_an_ended_run_and_a_run_without_a_sidecar_have_no_diff_tab
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_diff_tab_appears_within_five_seconds_of_the_sidecar_connecting_and_reads_once
- tests: groom/tests/test_diff_tab_dynamic.py::test_diff_tab_controls_have_roles_names_and_keyboard_operation_and_pass_axe
- tests: groom/tests/test_diff_tab_dynamic.py::test_diff_content_cannot_inject_markup

### detail-diff-count

- selector: `#detail-diff-count`
- role: none
- name: none
- keyboard: not focusable.
- verify: json_path(path="keyboard.tab_reachable", equals=false)
- parent: [detail-diff-tab](#detail-diff-tab)
- states: shows `+N −M`, the added and removed lines of the tracked change of the chosen checkout in the view in force, before the tab is opened.
- verify: visible(locator="#detail-diff-count", text="+8 −6")
- states: the change size is figures and words in the accessible name, never colour alone.
- states: untracked files are not counted.
- states: it is absent when the tracked change is empty.
- code: groom/groom/assets/dashboard.js::DetailTabs@7758bd0de773
- tests: groom/tests/test_diff_tab_dynamic.py::test_the_diff_tab_shows_the_size_of_the_change_before_it_is_opened_after_exactly_one_read
- tests: groom/tests/test_diff_tab_dynamic.py::test_untracked_files_sit_in_their_own_group_and_are_not_counted_in_the_tab

### detail-diff-read

- selector: `#detail-diff-read`
- role: group
- name: none
- keyboard: contains the `Read the diff again` button, reached with Tab.
- parent: [detail-tabs](#detail-tabs)
- states: shown only while the Diff tab is selected and a first read has landed.
- states: hidden, with its button, while the Since branch start view has no branch start to show.
- states: says `read HH:MM:SS` with an age that ticks each second.
- verify: visible(locator="#detail-diff-read", text="read")
- states: says `reading…` and disables the button while a read runs.
- verify: visible(locator="#detail-diff-read", text="reading…")
- states: hidden while the [stale strip](#detail-diff-stale-strip) shows, because the strip carries the read time and the retry.
- code: groom/groom/assets/dashboard.js::DiffRead@4ceebad9cc73
- tests: groom/tests/test_diff_tab_dynamic.py::test_the_tab_says_when_the_diff_was_read_and_refresh_reads_again_and_updates_the_counts

### detail-diff-stale-strip

- selector: `#detail-stale-strip`
- role: group
- name: Sidecar not answering
- keyboard: contains the `Retry now` button, reached with Tab and operated with Enter or Space.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- parent: [detail-tabs](#detail-tabs)
- states: shown above the diff only while the Diff tab is kept after the sidecar dropped and a diff is on screen.
- states: says `The sidecar stopped answering` with an age that ticks each second, says the run may still be working, and says `This is the diff from HH:MM:SS`.
- verify: visible(locator="#detail-diff-stale-strip", text="The run may still be working")
- states: the age is not a live region, so the ticking is not announced.
- states: `Retry now` takes the place of the `Read the diff again` control of the [read time](#detail-diff-read) while the strip shows.
- states: `Retry now` shows `reading…` while a read runs.
- states: a retry that finds no sidecar leaves the diff and its read time alone and the strip says `The sidecar is still not answering.`
- verify: visible(locator="#detail-diff-stale-strip", text="still not answering")
- states: when the sidecar returns, the diff is read again and the strip and the `stale` chip clear.
- states: after that read the selected file stays if it is still in the diff.
- states: the diff, the selected file and the scroll position stay as they were.
- states: the stale view is not dimmed.
- code: groom/groom/assets/dashboard.js::StaleStrip@39951b23e3bf
- code: groom/groom/assets/dashboard.js::DiffTab@8ed2100fd582
- detail: [kept run diff](../../concepts/kept-run-diff.md)
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_drop_keeps_the_diff_tab_marked_stale_in_words_with_a_strip_naming_the_read_time
- tests: groom/tests/test_diff_stale_dynamic.py::test_the_strip_counts_how_long_ago_on_the_shared_clock_without_a_live_region
- tests: groom/tests/test_diff_stale_dynamic.py::test_the_diff_selected_file_and_scroll_stay_as_they_were
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_retry_replaces_the_refresh_control_while_the_mark_shows_and_works_from_the_keyboard
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_retry_that_finds_no_sidecar_leaves_the_diff_and_its_time_alone_and_says_so
- tests: groom/tests/test_diff_stale_dynamic.py::test_a_reconnect_reads_again_clears_the_mark_and_keeps_the_selected_file
- tests: groom/tests/test_diff_stale_dynamic.py::test_the_strip_and_marks_pass_the_accessibility_scan

### detail-checkout-select

- selector: `#detail-checkout`
- role: combobox
- name: `Checkout`
- keyboard: Tab reaches it.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- keyboard: ArrowUp and ArrowDown change the checkout.
- verify: json_path(path="keyboard.arrow_keys_change_checkout", equals=true)
- parent: [detail-tabs](#detail-tabs)
- states: shown only while the Files or Diff tab is selected and the run has more than one checkout, at the right of the tab bar before the read time and the refresh button.
- states: a run with one checkout shows none.
- states: a sidecar that names no checkouts shows none.
- states: the Overview and Details tabs show none.
- verify: absent(subject="#detail-checkout for a run with one checkout")
- states: its options are the run's checkouts by name alone, and the workspace root reads `(workspace root)`.
- verify: visible(locator="#detail-checkout", text="api-service")
- states: it shows the run's chosen checkout, the first one for a run selected for the first time.
- states: it stays while a read of the chosen checkout fails, so the operator can choose another.
- states: checkout names are set as text, never as markup.
- code: groom/groom/assets/dashboard.js::CheckoutSelect@1dec79549bbb
- code: groom/groom/assets/dashboard.js::checkoutFor@4efc2c003f44
- detail: [run checkout selection](../../concepts/run-checkout-selection.md)
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_run_with_several_checkouts_shows_a_selector_on_files_and_diff_only
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_run_with_one_checkout_shows_no_selector
- tests: groom/tests/test_checkout_selector_dynamic.py::test_the_selector_has_a_role_and_a_name_works_from_the_keyboard_and_passes_axe
- tests: groom/tests/test_checkout_selector_dynamic.py::test_checkout_names_are_text_and_never_markup
- leads-to: [select detail checkout](#select-detail-checkout), which reads the chosen checkout.

### detail-diff-panel

- selector: `#detail-panel`
- role: tabpanel
- name: Diff
- keyboard: not focusable itself.
- verify: json_path(path="keyboard.tab_reachable", equals=false)
- parent: [detail-pane](#detail-pane)
- states: while the Diff tab is selected it holds the changed-file tree with an untracked group, and the selected file's diff beside it.
- states: while the first read runs it says `Reading the diff…` with `aria-busy`.
- verify: visible(locator="#detail-diff-panel", text="Reading the diff…")
- states: in the Since branch start view the message names the view, as the [diff view switch](#detail-diff-view-switch) lists.
- states: for a clean checkout it says there are no uncommitted changes.
- verify: visible(locator="#detail-diff-panel", text="no uncommitted changes")
- states: for a checkout with only untracked files it says `No tracked file has changed in this checkout.`
- states: while the sidecar is down, a view this page did not read before the drop says `This view was not read before the sidecar stopped answering`, and a run whose sidecar dropped before any diff was read says `The sidecar stopped answering before a diff was read`. Each offers `Retry now`.
- verify: visible(locator="#detail-diff-panel", text="stopped answering")
- verify: visible(locator="#detail-diff-panel", text="No tracked file has changed in this checkout.")
- states: for an empty diff from a sidecar too old to report failure it says it cannot confirm there are no changes.
- verify: visible(locator="#detail-diff-panel", text="cannot confirm")
- states: selecting an untracked file says it has no diff because git does not track it yet.
- code: groom/groom/assets/dashboard.js::DiffTab@8ed2100fd582
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_clean_checkout_says_so_and_the_tab_shows_no_count
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_checkout_with_only_untracked_files_lists_them_and_says_no_tracked_file_changed
- tests: groom/tests/test_diff_tab_dynamic.py::test_while_the_diff_is_read_the_tab_says_so_and_the_state_clears_when_it_arrives
- tests: groom/tests/test_diff_tab_dynamic.py::test_an_empty_diff_from_a_sidecar_too_old_to_report_failure_cannot_be_confirmed

### detail-diff-file-row

- selector: `button.tree-file`
- role: button
- one-per: changed or untracked file
- name: the file's basename and counts
- unique-by: path
- keyboard: reached with Tab, operated with Enter or Space.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- parent: [detail-diff-panel](#detail-diff-panel)
- states: tracked rows show per-file `+N` and `−M` counts, in a folder tree.
- states: a chain of single-child folders shows as one row, such as `services/api`.
- states: a folder with two children keeps its own row.
- verify: visible(locator="#detail-diff-file-row", text="sign_in.py")
- states: exactly one row is `active`, the first changed file until another is selected.
- verify: count(subject="active rows in the run Diff tab", equals=1)
- states: untracked rows sit in the `Not tracked by git yet` group and show no counts.
- code: groom/groom/assets/dashboard.js::DiffTab@ed8babf5c628
- code: groom/groom/assets/dashboard.js::diffEntries@ffb64254c8fd
- code: groom/groom/assets/dashboard.js::compactDirs@3a253a447ec9
- tests: groom/tests/test_diff_tab_dynamic.py::test_opening_diff_lists_changed_files_in_a_tree_with_counts_and_shows_the_first_file
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_chain_of_single_child_folders_is_one_row_and_a_folder_with_two_children_is_not

### detail-diff-file-head

- selector: `#detail-diff-file-head`
- role: none
- name: none
- keyboard: not focusable.
- parent: [detail-diff-panel](#detail-diff-panel)
- states: shows the selected file's path, its `+N` and `−M` counts and, on the right, the word `uncommitted`, or `since <7-character base> on <default branch>` in the Since branch start view, with the full commit and ref in its hover title.
- verify: visible(locator="#detail-diff-file-head", text="uncommitted")
- states: a new file says `new file`, a deleted file says `deleted file` and a renamed file says where it was renamed from, in words.
- verify: visible(locator="#detail-diff-file-head", text="deleted file")
- code: groom/groom/assets/dashboard.js::RunFileDiff@139e9580d270
- tests: groom/tests/test_diff_tab_dynamic.py::test_opening_diff_lists_changed_files_in_a_tree_with_counts_and_shows_the_first_file
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_new_file_says_so_in_the_header_above_its_lines

### detail-diff-body

- selector: `div.d2h-file-wrapper`
- role: none
- name: none
- keyboard: the rendered diff is selectable text.
- verify: json_path(path="keyboard.text_selectable", equals=true)
- parent: [detail-diff-panel](#detail-diff-panel)
- states: shows the selected file's lines, rendered by diff2html under the tab's own file header.
- states: scrolls inside a region the keyboard reaches, with the role `region` and the name `Changes in <path>`.
- verify: visible(locator="#detail-diff-body")
- states: diff2html escapes the file content, so it cannot inject markup.
- code: groom/groom/assets/dashboard.js::fileDiffMarkup@1286720f9b96
- tests: groom/tests/test_diff_tab_dynamic.py::test_diff_content_cannot_inject_markup

### detail-diff-unreadable

- selector: `#detail-diff-unreadable`
- role: alert
- name: none
- keyboard: contains the `Retry now` button, reached with Tab.
- parent: [detail-diff-panel](#detail-diff-panel)
- states: says `This diff could not be read` and `This does not mean there are no changes.`
- verify: visible(locator="#detail-diff-unreadable", text="This diff could not be read")
- states: it fills the width of the pane, with `Retry now` after the message on the same line, as the panel for a branch start that was not found does.
- states: it clears when a read succeeds.
- code: groom/groom/assets/dashboard.js::DiffTab@ed8babf5c628
- tests: groom/tests/test_diff_tab_dynamic.py::test_an_unreadable_diff_says_so_offers_a_retry_and_clears_when_a_read_succeeds

### detail-files-tab

- selector: `#tab-files`
- role: tab
- name: Files
- keyboard: ArrowLeft and ArrowRight reach it from Diff.
- verify: json_path(path="keyboard.arrow_keys_reach_files", equals=true)
- keyboard: Enter or Space on it selects it.
- verify: json_path(path="keyboard.enter_selects_files", equals=true)
- parent: [detail-tabs](#detail-tabs)
- states: present under the same condition as the Diff tab, directly before it.
- states: a native run, an ended run and a container run without a connected sidecar and without a diff read in this page have no Files tab.
- verify: visible(locator="#detail-files-tab", text="Files")
- verify: absent(subject="#detail-files-tab for a native run, an ended run, or a container run without a connected sidecar")
- states: the tab appears within 5 seconds of the sidecar connecting, without a reload.
- states: the tab goes when the run ends, and the Overview tab shows if Files was open.
- states: when the sidecar disconnects and this page holds a diff for the run, the tab stays and shows the sidecar-stopped state of the Files panel.
- states: selecting a run reads no tree, and the first open of the tab for that selection reads it once.
- states: moving to another tab and back keeps the tree and the selected file and reads nothing new.
- states: selecting another run resets the tree and the selected file.
- states: choosing another checkout clears the selected file and reads that checkout's tree.
- code: groom/groom/assets/dashboard.js::DetailTabs@c23c8518540f
- code: groom/groom/assets/dashboard.js::useRunFiles@9ef89b78abfa
- code: groom/groom/assets/dashboard.js::loadRunFiles@0928854e5520
- detail: [run Files tab](../../concepts/run-files-tab.md)
- tests: groom/tests/test_files_tab_dynamic.py::test_a_run_that_shows_a_diff_tab_shows_a_files_tab_before_it_and_other_runs_show_neither
- tests: groom/tests/test_files_tab_dynamic.py::test_files_tab_controls_have_roles_names_and_keyboard_operation_and_pass_axe

### detail-files-panel

- selector: `#detail-panel`
- role: tabpanel
- name: Files
- keyboard: not focusable itself.
- verify: json_path(path="keyboard.tab_reachable", equals=false)
- parent: [detail-pane](#detail-pane)
- states: while the Files tab is selected it holds the chosen checkout's folder tree, and the selected file beside it.
- states: while the tree is read it says `Reading the checkout…` with `aria-busy`.
- verify: visible(locator="#detail-files-panel", text="Reading the checkout…")
- states: before a file is selected it says `Select a file to read it.`
- verify: visible(locator="#detail-files-panel", text="Select a file to read it.")
- states: for a checkout with no files it says `This checkout has no files.`
- verify: visible(locator="#detail-files-panel", text="This checkout has no files.")
- states: for an empty listing from a sidecar too old to report failure it says it cannot confirm the checkout has no files.
- verify: visible(locator="#detail-files-panel", text="cannot confirm")
- states: the tab has no edit, save, delete or refresh control.
- states: while the sidecar is down and the Diff tab is kept, it says `The sidecar stopped answering` with how long ago and that the run may still be working.
- states: that state offers `Retry now`, and a retry that finds no sidecar adds `The sidecar is still not answering.`
- states: the tree is not kept, and the state clears when the sidecar returns.
- verify: visible(locator="#detail-files-panel", text="The sidecar stopped answering")
- code: groom/groom/assets/dashboard.js::FilesTab@44ffdf1c1d9a
- tests: groom/tests/test_files_tab_dynamic.py::test_opening_files_lists_the_checkout_in_a_folder_tree_and_a_folder_collapses_and_expands
- tests: groom/tests/test_files_tab_dynamic.py::test_a_checkout_with_no_files_says_so
- tests: groom/tests/test_files_tab_dynamic.py::test_before_a_file_is_selected_the_tab_asks_for_one
- tests: groom/tests/test_files_tab_dynamic.py::test_nothing_on_the_tab_can_change_a_file
- tests: groom/tests/test_files_tab_dynamic.py::test_while_the_tree_and_a_file_are_read_the_tab_says_so_and_each_state_clears_when_it_arrives
- tests: groom/tests/test_files_tab_dynamic.py::test_an_empty_answer_from_a_sidecar_too_old_to_report_failure_cannot_be_confirmed

### detail-files-file-row

- selector: `button.tree-file`
- role: button
- one-per: file in the checkout
- name: the file's basename
- unique-by: path
- keyboard: reached with Tab, operated with Enter or Space.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- parent: [detail-files-panel](#detail-files-panel)
- states: folders are collapsible rows, and a chain of single-child folders shows as one row, such as `services/api`.
- verify: visible(locator="#detail-files-file-row", text="sign_in.py")
- states: the selected file's row carries the `active` class and `aria-current="true"`.
- states: no row is active before a file is selected.
- verify: count(subject="active rows in the run Files tab before a file is selected", equals=0)
- states: the folders `.git`, `node_modules`, `__pycache__` and `.venv` never appear.
- states: a folder the operator collapsed stays collapsed while they move between the tabs of the same run, and every folder is open again once another run or another checkout is selected.
- code: groom/groom/assets/dashboard.js::FilesTab@6bf5e97b9175
- code: groom/groom/assets/dashboard.js::openRunFile@aa3dd1ae20a1
- tests: groom/tests/test_files_tab_dynamic.py::test_opening_files_lists_the_checkout_in_a_folder_tree_and_a_folder_collapses_and_expands
- tests: groom/tests/test_files_tab_dynamic.py::test_folders_the_operator_collapsed_stay_collapsed_across_tabs_of_the_same_run_and_reset_on_another_run

### detail-files-file-head

- selector: `#detail-files-file-head`
- role: none
- name: none
- keyboard: not focusable.
- parent: [detail-files-panel](#detail-files-panel)
- states: shows the selected file's path, its line count and its language.
- verify: visible(locator="#detail-files-file-head", text="services/api/sign_in.py")
- states: an empty file shows only the path and says `This file is empty.` beneath it.
- verify: visible(locator="#detail-files-panel", text="This file is empty.")
- states: an empty file from a sidecar too old to report failure says it cannot confirm the file is empty.
- code: groom/groom/assets/dashboard.js::RunFileView@91777ea958ea
- tests: groom/tests/test_files_tab_dynamic.py::test_an_empty_file_reads_as_empty_and_never_as_a_file_that_could_not_be_read

### detail-files-file-body

- selector: `div.code-view`
- role: none
- name: none
- keyboard: the source is selectable text.
- verify: json_path(path="keyboard.text_selectable", equals=true)
- parent: [detail-files-panel](#detail-files-panel)
- states: scrolls inside a region the keyboard reaches, with the role `region` and the name `Contents of <path>`.
- states: shows line numbers in a 44 px gutter that is hidden from the accessibility tree, beside the highlighted source.
- states: the code sits on a band darker than the pane that is as tall as the code, so the rest of the pane keeps the pane's own colour.
- states: the source is highlighted by the dashboard's own code renderer, so its text is escaped.
- verify: omits(subject="rendered run file", matches="<script")
- code: groom/groom/assets/dashboard.js::RunFileView@91777ea958ea
- code: groom/groom/assets/dashboard.js::fileCode@1925f7dd181c
- tests: groom/tests/test_files_tab_dynamic.py::test_selecting_a_file_shows_its_content_with_line_numbers_and_syntax_coloring
- tests: groom/tests/test_files_tab_dynamic.py::test_the_code_sits_on_a_darker_band_than_the_pane_with_a_44px_gutter
- tests: groom/tests/test_files_tab_dynamic.py::test_file_content_and_paths_cannot_inject_markup

### detail-files-unreadable

- selector: `#detail-files-unreadable`
- role: alert
- name: none
- keyboard: contains the `Retry now` button, reached with Tab.
- parent: [detail-files-panel](#detail-files-panel)
- states: says `This checkout could not be read`, and a read that did not happen is never shown as no files.
- verify: visible(locator="#detail-files-unreadable", text="This checkout could not be read")
- states: it clears when a read succeeds.
- code: groom/groom/assets/dashboard.js::FilesTab@6bf5e97b9175
- code: groom/groom/assets/dashboard.js::ReadFailed@c688a54f6211
- tests: groom/tests/test_files_tab_dynamic.py::test_a_tree_that_cannot_be_read_says_so_offers_a_retry_and_clears_when_a_read_succeeds

### detail-file-unreadable

- selector: `#detail-file-unreadable`
- role: alert
- name: none
- keyboard: contains the `Retry now` button, reached with Tab.
- parent: [detail-files-panel](#detail-files-panel)
- states: says `<path> could not be read` and `This does not mean the file is empty.` beside the tree, which stays usable.
- verify: visible(locator="#detail-file-unreadable", text="could not be read")
- states: it clears when a read succeeds.
- code: groom/groom/assets/dashboard.js::RunFileView@91777ea958ea
- tests: groom/tests/test_files_tab_dynamic.py::test_a_file_that_cannot_be_read_says_so_offers_a_retry_and_clears_when_a_read_succeeds

### detail-diff-view-switch

- selector: `#detail-diff-view-switch`
- role: group
- name: `Diff view`
- keyboard: Tab reaches each of its two buttons.
- keyboard: Enter or Space presses the focused button.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- parent: [detail-tabs](#detail-tabs)
- states: shown only while the Diff tab is selected, at the right of the tab bar before the checkout selector and the read time. The Overview, Details and Files tabs show none.
- states: each button exposes `aria-pressed`, and exactly one is pressed. Uncommitted is pressed for a run selected for the first time.
- verify: visible(locator="#detail-diff-view-switch", text="Since branch start")
- states: the pressed button is also set apart by a heavier weight and an underline, so its position is never colour alone.
- states: the position is held per run in the page's memory for the life of the page.
- states: a refresh, a tab change and a checkout change keep the position.
- states: selecting another run and coming back restores that run's own position.
- states: a reload starts at Uncommitted.
- states: pressing the other button reads `GET /diff/{container_id}` once for the chosen checkout, with `view=branch` for Since branch start and without `view` for Uncommitted.
- states: pressing the pressed button reads nothing.
- states: Since branch start shows the whole change since the branch started, the tab's `+N −M` follows it, and the file header says `since <7-character base> on <default branch>`.
- states: while that view is read the panel says `Reading the change since the branch started…` with `aria-busy`, and the tab shows no count.
- states: a branch with no change says `This branch has no change since it started at <base> on <branch>.` and shows no count.
- states: a checkout on its default branch says so.
- states: a checkout whose branch start cannot be found says so and offers `Retry now`.
- states: a sidecar too old for the view says `This view needs a newer sidecar. Uncommitted still works.`
- states: none of those three shows a count or shows another view's diff as this one.
- states: an unreadable read says `This view could not be read` and `This does not mean there is no change.` with `Retry now`.
- verify: absent(subject="#detail-diff-count for a branch with no change since it started")
- code: groom/groom/assets/dashboard.js::DiffViewSwitch@6de2b73f3db9
- code: groom/groom/assets/dashboard.js::selectDiffView@3a2b2daaeae5
- code: groom/groom/assets/dashboard.js::Segment@d29ccddabf83
- code: groom/groom/assets/dashboard.js::BranchStartNotice@95b98f3f8489
- detail: [branch start diff](../../concepts/branch-start-diff.md)
- detail: [run Diff tab](../../concepts/run-diff-tab.md)
- tests: groom/tests/test_diff_since_branch_dynamic.py::test_the_diff_tab_opens_on_uncommitted_with_a_switch_that_sends_the_sidecar_no_new_parameter
- tests: groom/tests/test_diff_since_branch_dynamic.py::test_the_switch_is_on_the_diff_tab_only
- tests: groom/tests/test_diff_since_branch_dynamic.py::test_the_switch_keeps_its_position_when_the_diff_is_refreshed
- tests: groom/tests/test_diff_since_branch_dynamic.py::test_selecting_another_run_and_coming_back_keeps_each_runs_own_position
- tests: groom/tests/test_diff_since_branch_dynamic.py::test_the_switch_has_a_role_a_name_keyboard_operation_and_shows_its_position_by_more_than_color

## Interactions

### select-activity-runs-mode

- on: [activity-runs-mode](#activity-runs-mode)
- trigger: pointer click, tap, Enter, or Space on the runs rail button or its SVG, captured by the delegated `#activitybar` click handler.
- role: button
- name: `Runs`
- keyboard: Tab and Shift+Tab reach the button.
- verify: visible(locator=".act-btn[data-mode='runs']:focus", text="Runs")
- keyboard: Enter or Space activates the button.
- verify: visible(locator=".app[data-mode='runs']", text="Runs")
- when:
  - The shell is loaded and the rail contains the runs control.
  - The click target or an ancestor matches `.act-btn`, and that control's `data-mode` is `runs`.
  - The prior mode may be any of the four.
- does:
  - Writes `runs` to the root `.app` element's `data-mode`.
- verify: visible(locator=".app[data-mode='runs']", text="Runs")
- does:
  - Shows the runs pane.
- verify: visible(locator="#runs-pane")
- does:
  - Removes the attendant, dispatch, and settings panes from the accessibility tree.
- verify: removed(subject="the attendant, dispatch, and settings panes in the accessibility tree")
- does:
  - Adds the `active` class to the runs rail button.
- verify: created(subject="the `active` class on the runs rail button")
- does:
  - Sets `aria-pressed="true"` on the runs rail button.
- verify: visible(locator=".act-btn[data-mode='runs'][aria-pressed='true']", text="Runs")
- does:
  - Removes the `active` class from every non-runs rail button.
- verify: removed(subject="the `active` class from every non-runs rail button")
- does:
  - Sets `aria-pressed="false"` on every non-runs rail button.
- verify: json_path(path="activity.buttons.settings.ariaPressed", equals="false")
- does:
  - Writes the mode to the store, so components that branch on it agree with the DOM.
- verify: json_path(path="store.mode", equals="runs")
- does:
  - Leaves each run's chosen checkout unchanged.
- verify: unchanged(subject="each run's chosen checkout")
- does:
  - Leaves the run's Files and Diff tab state unchanged.
- verify: unchanged(subject="run Files and Diff tab state")
- does:
  - Leaves the selected run unchanged.
- verify: unchanged(subject="selected run")
- does:
  - Leaves the fleet unchanged.
- verify: unchanged(subject="fleet")
- does:
  - Leaves the detail pane unchanged.
- verify: unchanged(subject="detail pane")
- does:
  - Leaves the command palette unchanged.
- verify: unchanged(subject="command palette")
- does:
  - Leaves the status bar unchanged.
- verify: unchanged(subject="status bar")
- does:
  - Leaves the socket unchanged.
- verify: unchanged(subject="dashboard socket")
- does:
  - Leaves server state unchanged.
- verify: unchanged(subject="server state")
- does:
  - Performs no HTTP request.
- verify: count(subject="HTTP requests", equals=0)
- does:
  - Performs no WebSocket send.
- verify: count(subject="WebSocket sends", equals=0)
- does:
  - Performs no navigation.
- verify: unchanged(subject="browser URL")
- does:
  - Performs no focus move.
- verify: unchanged(subject="document.activeElement")
- does:
  - Performs no permission prompt.
- verify: count(subject="permission prompts", equals=0)
- code: groom/groom/assets/dashboard.js::setMode@d01c7d7c3d9c
- detail: [dashboard mode selection](../../concepts/dashboard-mode-selection.md)

### select-activity-settings-mode

- on: [activity-settings-mode](#activity-settings-mode)
- trigger: pointer click, tap, Enter, or Space on the settings rail button or its SVG, captured by the delegated `#activitybar` click handler.
- role: button
- name: `Settings`
- keyboard: Tab reaches the button.
- verify: visible(locator=".act-btn[data-mode='settings']:focus", text="Settings")
- keyboard: Shift+Tab reaches the button.
- verify: visible(locator=".act-btn[data-mode='settings']:focus", text="Settings")
- keyboard: Enter activates the button.
- verify: visible(locator=".app[data-mode='settings']", text="Settings")
- keyboard: Space activates the button.
- verify: visible(locator=".app[data-mode='settings']", text="Settings")
- when:
  - The click target or an ancestor matches `.act-btn` with `data-mode="settings"`.
- does:
  - Writes `settings` to `.app[data-mode]`.
- verify: visible(locator=".app[data-mode='settings']", text="Settings")
- does:
  - Recomputes `active` across the rail.
- verify: visible(locator=".act-btn[data-mode='settings'].active", text="Settings")
- does:
  - Recomputes `aria-pressed` across the rail.
- verify: visible(locator=".act-btn[data-mode='settings'][aria-pressed='true']", text="Settings")
- does:
  - Writes the mode to the store.
- verify: json_path(path="$.mode", equals="settings")
- verify: absent(subject="loader")
- verify: absent(subject="permission dialog")
- verify: unchanged(subject="application state", except_fields=["mode", "active", "aria-pressed"])
- code: groom/groom/assets/dashboard.js::setMode@d01c7d7c3d9c
- detail: [dashboard mode selection](../../concepts/dashboard-mode-selection.md)
- screenshot: docs/services/groom/gui/screenshots/operator-refreshes-workflow-fleet-settings-idle.png

### filter-runs

- on: [runs-filter-input](#runs-filter-input)
- trigger: an `input` event on the runs filter field — typing, pasting, or using the search field's clear affordance.
- role: searchbox
- name: `Filter runs`
- keyboard: Tab reaches the field.
- verify: json_path(path="$.activeElement", equals="#runs .filter")
- keyboard: Every keystroke fires the handler.
- verify: json_path(path="$.query", equals="author")
- when: The runs pane is loaded.
- verify: visible(locator="#runs")
- when: The fleet may be empty, mid-discovery, or populated.
- verify: visible(locator="#runs-list", text="author-002")
- does:
  - Writes the field's raw value to the store's query without debounce, because filtering happens on the client over a few dozen already-pushed rows.
- verify: json_path(path="$.query", equals=" author ")
- does:
  - Re-renders the run list to only rows whose lowercased haystack contains the trimmed lowercased query.
- verify: visible(locator="#runs-list", text="author-002")
- does:
  - Builds each row's haystack from its name, repository, type, node, activity, current doing line, question, and run id.
- verify: visible(locator="#runs-list", text="author-002")
- does:
  - Renders `No workhorse runs — nothing is running.` when the query matches nothing.
- verify: visible(locator="#runs-list", text="No workhorse runs — nothing is running.")
- does:
  - Shows the discovery message only for an empty unfiltered fleet.
- verify: visible(locator="#runs-list", text="Discovering containers…")
- does:
  - Does not filter server-side, because a server-filtered list would be clobbered by the next 5s push that sends the whole fleet.
- verify: count(subject="outbound HTTP requests after filter input", equals=0)
- does:
  - Leaves the selected run untouched.
- verify: unchanged(subject="selected run")
- does:
  - Leaves the detail pane untouched.
- verify: unchanged(subject="run detail pane")
- does:
  - Leaves the command palette's hit list untouched.
- verify: unchanged(subject="command palette hit list")
- does:
  - Lets the command palette find a run this filter is hiding because its hit list reads the fleet from the store.
- verify: visible(locator="#palette-results", text="author-002")
- does:
  - Performs no HTTP request.
- verify: count(subject="outbound HTTP requests after filter input", equals=0)
- does:
  - Performs no websocket send.
- verify: count(subject="outbound websocket sends after filter input", equals=0)
- code: groom/groom/assets/dashboard.js::wireEvents@99f073783401
- code: groom/groom/assets/dashboard.js::Fleet@b1dc450f276a
- code: groom/groom/assets/dashboard.js::rowHaystack@484f5d24f89a
- detail: [dashboard event wiring interaction contexts](../../concepts/dashboard-event-wiring-interaction-contexts.md)
- tests: groom/tests/test_projection.py::test_query_filters_the_fleet

### select-run-row

- on: [run-row](#run-row)
- trigger: pointer click, tap, Enter, or Space anywhere in a run row, captured by the delegated body click handler that looks for the nearest `[data-worker-id]` ancestor.
- role: button
- one-per: `run` — one interaction per run in Fleet's filtered `shown` collection, which maps each run to `RunRow`.
- name: `{run.repo} #{run.row_id} {run.live_label} {run.doing}`
- unique-by: `run.id` — the `data-worker-id` and Preact key rendered by `RunRow` are distinct per run.
- keyboard: Tab reaches the row.
- verify: visible(locator="[data-worker-id]")
- keyboard: Enter or Space activates the row.
- verify: json_path(path="selection.activation_key_selects_row", equals=true)
- when:
  - The click did not originate inside a form or a file tree — those have their own handlers.
  - The nearest matching ancestor carries a `data-worker-id`.
- does:
  - Takes the next selection sequence number, so a slower reply for an older selection cannot land.
  - verify: json_path(path="selection.stale_fetch_is_ignored", equals=true)
  - Writes the run id and a null detail to the store in one update, so no render pairs the new selection with the previous run's pane.
  - verify: json_path(path="store.detail", equals=null)
  - Renders the detail pane as `Loading telemetry history…` while the store holds that null detail for the newly selected run, on the Overview tab, with the run list narrowed beside it.
  - verify: visible(locator="#detail", text="Loading telemetry history…")
  - Keeps the [gate strip](#detail-gate-strip)'s collapsed state when the id is the run already selected, and opens it expanded for any other run.
  - verify: json_path(path="store.gatesCollapsed", equals=false)
  - Keeps the text typed in each of the previous run's answer boxes in the page-held draft, so it returns when the operator selects that run again.
  - verify: persists(subject="typed answer text for a run after selecting another run and coming back")
  - Sends this tab's watch subscription for the id over the dashboard websocket, replacing whatever it was watching.
  - verify: json_path(path="watch.subscription", equals="selected run")
  - Limits a tab to watching one run.
  - verify: count(subject="runs watched by the selecting tab", equals=1)
  - Does not retry a refused watch send, because the next selection or reconnect re-sends it.
  - verify: count(subject="watch sends after a refused send", equals=1)
  - Fetches [GET /worker/{container_id}](../../http/groom.md#get-run-detail) once.
  - verify: count(subject="GET /worker/{container_id} requests after selection", equals=1)
  - Stores the parsed fetch body only when this is still the newest selection and no pushed detail has landed meanwhile, since a `detail` frame that arrived first is the fresher truth.
  - verify: unchanged(subject="pushed run detail after an older fetch completes")
  - Swallows a rejected fetch.
  - verify: json_path(path="selection.fetch_rejection_is_handled", equals=true)
  - Leaves the pane in its loading state after a rejected fetch until the subscription's next push fills it, so a transient failure costs a tick rather than an error message.
  - verify: visible(locator="#detail", text="Loading…")
  - Renders the selected row from the store with `selected` and `aria-current="true"` on every render, so a fleet push already agrees with the selection and nothing walks the document repainting rows.
  - verify: json_path(path="selected_row.ariaCurrent", equals="true")
  - Does not move focus.
  - verify: unchanged(subject="active element after selecting a run")
  - Does not change the active mode.
  - verify: unchanged(subject="active dashboard mode after selecting a run")
  - Does not mutate server state beyond the watch subscription.
  - verify: unchanged(subject="server state except the selecting tab's watch subscription")
- code: groom/groom/assets/dashboard.js::select@90d0cfa4c531
- code: groom/groom/assets/dashboard.js::onDetail@f9e46aa48020
- code: groom/groom/assets/dashboard.js::RunRow@703c0edbc1b1
- detail: [dashboard run selector](../../concepts/dashboard-run-selector.md)
- tests: groom/tests/test_app.py::test_watch_registers_the_tab_and_pushes_that_run_immediately
- tests: groom/tests/test_app.py::test_a_detail_push_reaches_only_the_tabs_watching_that_run
- screenshot: docs/services/groom/gui/screenshots/operator-answers-blocked-gate-detail-selected.png

### keyboard-select-run-row

- on: [run-row](#run-row)
- trigger: pressing `j` or `k` anywhere on the page while focus is not in a text field, textarea, select or editable region.
- role: button
- one-per: `run` — one keyboard-selectable row per run in the store-backed fleet after the active filter is applied.
- name: `{run.repo} #{run.row_id} {run.live_label} {run.doing}`
- unique-by: `run.id` — the distinct key and `data-worker-id` rendered by `RunRow`.
- keyboard: `j` moves the selection one row down and clamps at the end of the list rather than wrapping.
- verify: json_path(path="keyboard.j.moves_selection_down_and_clamps", equals=true)
- keyboard: `k` moves the selection one row up and clamps at the beginning of the list rather than wrapping.
- verify: json_path(path="keyboard.k.moves_selection_up_and_clamps", equals=true)
- when:
  - The command palette is closed — while it is open, the same keys type into its input.
  - The active element is not an `INPUT`, `TEXTAREA` or `SELECT` and is not editable, so typing a `j` into the filter box, or pressing it on the [checkout selector](#detail-checkout-select), never moves the selection.
- does:
  - Reads the currently rendered rows out of `#runs-list` and finds the index of the selected run by its `data-worker-id`.
- verify: json_path(path="selection.index_is_read_from_rendered_rows", equals=true)
- does:
  - Starts from the first row when the fleet has no selected run.
- verify: json_path(path="selection.unselected_fleet_starts_at_first_row", equals=true)
- does:
  - Clamps the neighbouring index into range.
- verify: json_path(path="selection.neighbouring_index_is_clamped", equals=true)
- does:
  - When a row is in range, switches to runs mode.
- verify: json_path(path="selection.in_range_row_switches_to_runs_mode", equals=true)
- does:
  - When a row is in range, selects that run through the same selector the click path uses.
- verify: json_path(path="selection.in_range_row_uses_the_click_selector", equals=true)
- does:
  - Moves through the *rendered* rows, so an active filter narrows what the keys traverse.
- verify: json_path(path="selection.traverses_filtered_rendered_rows", equals=true)
- does:
  - Does nothing when the list is empty.
- verify: json_path(path="selection.empty_list_does_nothing", equals=true)
- code: groom/groom/assets/dashboard.js::wireEvents@99f073783401
- code: groom/groom/assets/dashboard.js::select@46f96b77d0ce
- code: groom/groom/assets/dashboard.js::setMode@d01c7d7c3d9c
- detail: [dashboard mode selection](../../concepts/dashboard-mode-selection.md)
- detail: [dashboard run selector](../../concepts/dashboard-run-selector.md)
- detail: [dashboard event wiring interaction contexts](../../concepts/dashboard-event-wiring-interaction-contexts.md)

### edit-detail-answer-textarea

- on: [detail-answer-textarea](#detail-answer-textarea)
- trigger: typing, pasting, or otherwise editing the answer field.
- role: textbox
- name: `Your answer`
- keyboard: Tab reaches the field.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- keyboard: Enter inserts a newline.
- verify: created(subject="a newline at the caret position")
- keyboard: Tab moves on to the send button.
- verify: json_path(path="keyboard.tab_moves_to_send_button", equals=true)
- when:
  - The open run has at least one open gate, so the answer form is rendered.
- does:
  - Writes the field's value to a page-held draft keyed by run and gate, through one delegated input handler. It writes nothing to the store and sends no request.
  - Brings the kept text back when the operator selects another run and returns to this one.
  - Survives the fleet's 5-second push: the gate block is keyed by gate file path, so Preact reuses the same `<textarea>` DOM node across re-renders and neither the text, the caret, the selection nor the focus is lost.
  - Survives a pushed `detail` frame for the same run for the same reason, including one carrying a newly opened gate for a different file. Another gate's box keeps its own draft.
  - Survives collapsing and expanding the [gate strip](#detail-gate-strip), because the boxes are hidden and not removed.
  - Does nothing else for a shortcut key: the list shortcuts ignore a focused text field.
- code: groom/groom/assets/dashboard.js::AnswerForm@8a9e54c1b5c4
- code: groom/groom/assets/dashboard.js::GateBlock@0b60fdd379ab
- tests: groom/tests/test_gate_strip_dynamic.py::test_a_live_push_keeps_the_draft_the_collapsed_state_and_the_focused_gate
- tests: groom/tests/test_gate_strip_dynamic.py::test_shortcut_keys_typed_in_the_answer_box_do_nothing_else
- tests: groom/tests/test_gate_above_diff_dynamic.py::test_j_and_k_typed_in_the_answer_box_type_those_letters_and_leave_the_run_and_the_file_alone
- tests: groom/tests/test_gate_above_diff_dynamic.py::test_selecting_another_run_keeps_what_was_typed_for_this_runs_gate_until_it_is_sent
- screenshot: docs/services/groom/gui/screenshots/operator-answers-blocked-gate-answer-typed.png

### send-detail-answer

- on: [detail-send-answer-button](#detail-send-answer-button)
- trigger: submitting the answer form — clicking the button, or Enter from within it — captured by a delegated document-level submit handler.
- role: button
- name: `Send answer`
- keyboard: Tab reaches the button.
- verify: visible(locator=".answer button[type='submit']:focus", text="Send answer")
- keyboard: Enter submits the answer form.
- verify: count(subject="WebSocket sends after Enter submits the answer form", equals=1)
- keyboard: Space submits the answer form.
- verify: count(subject="WebSocket sends after Space submits the answer form", equals=1)
- when: The submit target is inside a `form[data-answer]`.
- verify: json_path(path="submit_target.is_answer_form", equals=true)
- when: The dashboard websocket is open.
- verify: json_path(path="websocket.readyState", equals=1)
- when: The dashboard websocket is closed.
- verify: json_path(path="websocket.readyState", equals=3)
- does:
  - Prevents the browser's own form submission.
- verify: unchanged(subject="browser URL")
- does:
  - Sends an `answer` command in the [dashboard websocket answer frame](../../formats/dashboard-websocket-answer-frame.md).
- verify: json_path(path="websocket.frames[0].cmd", equals="answer")
- does:
  - Sends the form's workflow id in the answer frame.
- verify: json_path(path="websocket.frames[0].workflow_id", equals="fixture workflow id")
- does:
  - Sends the form's gate file path in the answer frame.
- verify: json_path(path="websocket.frames[0].file_path", equals="fixture gate file path")
- does:
  - Sends the typed answer in the answer frame.
- verify: json_path(path="websocket.frames[0].answer", equals="fixture answer")
- does:
  - Sends one answer frame over the open dashboard websocket.
- verify: count(subject="answer frames sent after one submission", equals=1)
- does:
  - Clears the textarea and its page-held draft after a successful send.
- verify: json_path(path="answer_textarea.value", equals="")
- does:
  - Leaves the textarea unchanged when the send is refused.
- verify: json_path(path="answer_textarea.value", equals="fixture answer")
- does:
  - Pushes the `✗ not sent` toast when the send is refused.
- verify: visible(locator="#toasts", text="✗ not sent")
- does:
  - Names the lost connection in the refused-send toast.
- verify: visible(locator="#toasts", text="No connection to groom")
- does:
  - Does not re-fetch the pane after submission.
- verify: count(subject="HTTP requests after answer submission", equals=0)
- does:
  - Shows the `✓ answer sent` confirmation when it receives a [dashboard answered message](../../formats/dashboard-answered-message.md).
- verify: visible(locator="#toasts", text="✓ answer sent")
- does:
  - Shows the `✗ answer not taken` toast with the server's reason as its body when this tab receives an `answer_rejected` frame.
- verify: visible(locator="#toast-region", text="✗ answer not taken")
- does:
  - Puts the sent answer back into its gate's textarea when this tab receives an `answer_rejected` frame for that gate's `id` and `file_path`, unless the operator has typed into the box since.
- verify: persists(subject="sent answer in its gate textarea after an answer_rejected frame for that gate")
- does:
  - Refreshes the pane from the `detail` push triggered by the answer command.
- verify: visible(locator=".detail-body", text="fixture refreshed gate detail")
- does:
  - Leaves a half-typed answer for a different run untouched when the answered pane refreshes.
- verify: json_path(path="other_run.answer_textarea.value", equals="fixture answer")
- does:
  - Continues to handle answer-form submissions after a detail push re-renders the form.
- verify: count(subject="answer frames sent after a detail-push re-render", equals=1)
- does:
  - Leaves the answered gate out of the [gate strip](#detail-gate-strip) once the refreshed detail arrives.
- verify: absent(subject="the answered gate's block in the gate strip")
- does:
  - Keeps the open tab and its scroll position when the last gate leaves the strip.
- verify: persists(subject="the open tab and its scroll position after the last gate leaves the strip")
- code: groom/groom/assets/dashboard.js::wireAnswerForm@37509043cbdd
- code: groom/groom/assets/dashboard.js::sendCommand@37a75c09204d
- code: groom/groom/assets/dashboard.js::onAnswered@cf3cd6e147fe
- code: groom/groom/assets/dashboard.js::onAnswerRejected@de5d47f81c94
- tests: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_an_answered_event
- tests: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch
- tests: groom/tests/test_a11y_dynamic.py::test_the_answer_form_is_reachable_and_submittable_by_keyboard
- tests: groom/tests/test_a11y_dynamic.py::test_a_rejected_answer_toasts_the_reason_to_the_sending_tab_alone
- tests: groom/tests/test_a11y_dynamic.py::test_a_rejected_answer_puts_the_typed_text_back_in_its_box
- tests: groom/tests/test_gate_strip_dynamic.py::test_sending_an_answer_removes_that_gate_and_the_last_one_clears_the_strip_without_moving_the_tab
- tests: groom/tests/test_gate_strip_dynamic.py::test_a_failed_send_keeps_the_typed_answer_and_says_it_failed
- screenshot: docs/services/groom/gui/screenshots/operator-answers-blocked-gate-answer-drafted.png

### rescan-containers-from-settings

- on: [settings-rescan-button](#settings-rescan-button)
- trigger: pointer click, tap, Enter, or Space on the settings pane's rescan button, captured by the delegated body click handler.
- role: button
- name: `Rescan containers`
- keyboard: Tab reaches the button.
- verify: visible(locator="#btn-notify", text="Enable notifications")
- keyboard: Enter or Space activates the button.
- verify: emitted(event="browser notification permission request", count=1)
- when:
  - Settings mode is active. A rescan may already be in flight.
- does:
  - Returns immediately when the button already carries `data-busy`, so a double click issues one request.
- verify: count(subject="POST /refresh requests after a double click", equals=1)
- does:
  - Marks the button busy before sending the refresh request.
- verify: json_path(path="refresh_button.busy", equals=true)
- does:
  - Shows the button spinner while the refresh request is in flight.
- verify: visible(locator="#btn-refresh.spinning", text="Rescan containers")
- does:
  - Sends `POST /refresh` to [post refresh](../../http/groom.md#post-refresh).
- verify: count(subject="POST /refresh requests after one activation", equals=1)
- does:
  - Clears the button's busy marking when the request settles, whether it succeeds or fails.
- verify: json_path(path="refresh_button.busy", equals=false)
- does:
  - Stops the button spinner when the request settles, whether it succeeds or fails.
- verify: json_path(path="refresh_button.spinning", equals=false)
- does:
  - Does not render the refresh reply directly.
- verify: unchanged(subject="dashboard state before and after the refresh reply")
- does:
  - Reconciles the fleet with containers discovered by the scan.
- verify: created(subject="workflow discovered by the refresh scan")
- does:
  - Prunes a container that the scan no longer finds.
- verify: removed(subject="state.WORKFLOWS['gone']")
- does:
  - Broadcasts the reconciled fleet state on the dashboard websocket.
- verify: emitted(event="state", count=1)
- does:
  - Updates the run list from the broadcast state.
- verify: visible(locator="#runs-list", text="discovered-workflow")
- does:
  - Updates the status bar from the broadcast state.
- verify: visible(locator=".status-right", text="1 workers")
- does:
  - Leaves the selected run untouched.
- verify: unchanged(subject="selected run")
- does:
  - Leaves the detail pane untouched.
- verify: unchanged(subject="run detail pane")
- does:
  - Leaves the files cache untouched.
- verify: unchanged(subject="files cache")
- does:
  - Leaves the diff cache untouched.
- verify: unchanged(subject="diff cache")
- does:
  - Leaves the command palette untouched.
- verify: unchanged(subject="command palette")
- does:
  - Retains the existing fleet when Docker availability cannot be determined, so a transient outage does not empty the dashboard.
- verify: unchanged(subject="state.WORKFLOWS['keep']")
- code: groom/groom/assets/dashboard.js::doRefresh@622b51370ad0
- detail: [dashboard rescan control selection](../../concepts/dashboard-rescan-control-selection.md)
- tests: groom/tests/test_app.py::test_refresh_prunes_vanished_containers
- tests: groom/tests/test_app.py::test_refresh_skips_prune_when_docker_unavailable

### rescan-containers-from-statusbar

- on: [statusbar-refresh-button](#statusbar-refresh-button)
- trigger: pointer click, tap, Enter, or Space on the status bar's refresh control, captured by the same delegated body click handler.
- role: button
- name: `Rescan containers (reconcile + prune)`
- keyboard: Tab reaches the button.
- verify: visible(locator="#btn-refresh-bar")
- keyboard: Enter or Space activates it.
- verify: count(subject="POST /refresh requests after one status-bar keyboard activation", equals=1)
- when:
  - Any mode is active — the status bar is outside the panes and always visible.
- does:
  - Runs the identical rescan as the settings control.
- verify: count(subject="POST /refresh requests after one status-bar activation", equals=1)
- does:
  - Uses the same refresh handler as the settings control.
- verify: json_path(path="settings_and_statusbar_refresh.handler", equals="doRefresh")
- does:
  - Keeps an independent busy guard for the status-bar button.
- verify: count(subject="POST /refresh requests after a status-bar double click", equals=1)
- does:
  - Spins its own icon while the refresh request is in flight.
- verify: visible(locator="#btn-refresh-bar.spinning")
- does:
  - Shows no other feedback than the spinning icon until the resulting state broadcast arrives.
- verify: unchanged(subject="run list and status bar text before the refresh broadcast arrives")
- does:
  - Uses a longer accessible name than the settings control because both controls are visible in settings mode and matching role and names would make them indistinguishable to a screen reader and `getByRole`.
- verify: json_path(path="accessibility.statusbar_refresh_button.name", equals="Rescan containers (reconcile + prune)")
- code: groom/groom/assets/dashboard.js::doRefresh@622b51370ad0
- code: groom/groom/assets/dashboard.js::StatusBar@e4ee89746df9
- detail: [dashboard rescan control selection](../../concepts/dashboard-rescan-control-selection.md)
- screenshot: docs/services/groom/gui/screenshots/operator-refreshes-workflow-fleet-post-scan.png

### enable-browser-notifications-from-settings

- on: [settings-enable-notifications-button](#settings-enable-notifications-button)
- trigger: pointer click, tap, Enter, or Space on the settings pane's notifications button.
- role: button
- name: `Enable notifications`
- keyboard: Tab reaches the button, then Enter or Space activates it.
- verify: emitted(event="browser notification permission request", count=1)
- when:
  - The browser exposes the Notification API. Where it does not, the click is ignored entirely.
- verify: emitted(event="browser notification permission request", count=0)
- does:
  - Requests [browser notification permission](../../concepts/browser-notification-permission.md).
- verify: emitted(event="browser notification permission request", count=1)
- does:
  - Shows the browser's own prompt when permission is still at its default.
- verify: emitted(event="browser notification permission prompt", count=1)
- does:
  - Resolves silently when permission has already been granted or denied.
- verify: emitted(event="browser notification permission prompt", count=0)
- does:
  - Changes no dashboard state: the label does not change.
- verify: unchanged(subject="dashboard state")
- does:
  - Stores nothing and sends no request.
- verify: unchanged(subject="dashboard persistence and requests")
- does:
  - With permission granted, a blocked-run notification raises a system notification alongside its toast.
- verify: emitted(event="browser notification", count=1)
- does:
  - Without permission, a blocked-run notification raises only the toast.
- verify: emitted(event="browser notification", count=0)
- does:
  - The first click anywhere on the page also asks once.
- verify: emitted(event="browser notification permission request", count=1)
- does:
  - The first-click path requires a user gesture because browsers ignore an unprompted permission dialog.
- verify: emitted(event="browser notification permission request", count=0)
- code: groom/groom/assets/dashboard.js::wireEvents@99f073783401
- code: groom/groom/assets/dashboard.js::onNotify@cce9ad7b825b
- detail: [dashboard event wiring interaction contexts](../../concepts/dashboard-event-wiring-interaction-contexts.md)

### toggle-command-palette-shortcut

- on: [command-palette-open-button](#command-palette-open-button)
- trigger: `Ctrl+K` or `Meta+K` anywhere on the page, or pointer click, tap, Enter, or Space on the status bar's palette button.
- role: button
- name: `Open command palette`
- keyboard: Either `Ctrl+K` or `Meta+K` opens the palette from anywhere, including inside a text field.
- verify: visible(locator="#palette.open")
- keyboard: Either `Ctrl+K` or `Meta+K` closes the palette when it is open.
- verify: absent(subject="open command palette dialog")
- keyboard: Escape closes the palette.
- verify: absent(subject="open command palette dialog")
- when:
  - The dashboard is loaded.
- verify: visible(locator=".app")
- when:
  - The palette is closed when the keyboard shortcut opens it.
- verify: visible(locator="#palette.open")
- when:
  - The palette is open when the keyboard shortcut closes it.
- verify: absent(subject="open command palette dialog")
- does:
  - Suppresses the browser default for the shortcut.
- verify: json_path(path="keyboardEvent.defaultPrevented", equals=true)
- does:
  - Closes the palette when the shortcut fires while it is open.
- verify: removed(subject="open command palette dialog")
- does:
  - Opens the palette when the shortcut fires while it is closed.
- verify: created(subject="the open command palette")
- does:
  - Leaves the palette open when the palette button is clicked while it is already open.
- verify: json_path(path="store.palette.open", equals=true)
- does:
  - Records the palette button as the invoker when that button opens the palette.
- verify: json_path(path="document.activeElement.id", equals="btn-palette")
- does:
  - Records the focused element as the invoker when the shortcut opens the palette.
- verify: json_path(path="document.activeElement.id", equals="repo-search")
- does:
  - Adds `open` to the palette when it opens.
- verify: created(subject="the palette with the open class")
- does:
  - Sets the palette input's `aria-expanded` value to `true` when it opens.
- verify: json_path(path="palette.input.aria-expanded", equals="true")
- does:
  - Clears the palette input when it opens.
- verify: json_path(path="palette.input.value", equals="")
- does:
  - Resets the palette query in the store when it opens.
- verify: json_path(path="store.palette.query", equals="")
- does:
  - Resets the palette active index in the store when it opens.
- verify: json_path(path="store.palette.active", equals=0)
- does:
  - Focuses the palette input when it opens.
- verify: json_path(path="document.activeElement.id", equals="palette-input")
- does:
  - Renders the current fleet from the store as results, so the palette lists runs the runs-pane filter is hiding.
- verify: count(subject="palette results", equals=2)
- does:
  - Traps Tab on the input while open, since that input is the dialog's only focusable element.
- verify: json_path(path="document.activeElement.id", equals="palette-input")
- does:
  - Removes `open` from the palette when it closes.
- verify: removed(subject="open command palette dialog")
- does:
  - Sets the palette input's `aria-expanded` value to `false` when it closes.
- verify: json_path(path="palette.input.aria-expanded", equals="false")
- does:
  - Removes `aria-activedescendant` from the palette input when it closes.
- verify: removed(subject="the palette input's aria-activedescendant")
- does:
  - Marks the palette closed in the store.
- verify: json_path(path="store.palette.open", equals=false)
- does:
  - Returns focus to the recorded invoker when the palette closes.
- verify: json_path(path="document.activeElement.id", equals="btn-palette")
- does:
  - Sends no request.
- verify: count(subject="HTTP requests", equals=0)
- does:
  - Leaves server state unchanged.
- verify: unchanged(subject="server state")
- code: groom/groom/assets/dashboard.js::openPalette@ab1a5517a248
- code: groom/groom/assets/dashboard.js::closePalette@039308c89fc9
- code: groom/groom/assets/dashboard.js::wireEvents@99f073783401
- detail: [dashboard event wiring interaction contexts](../../concepts/dashboard-event-wiring-interaction-contexts.md)

### filter-command-palette-results

- on: [command-palette-input](#command-palette-input)
- trigger: an `input` event on the palette field, or ArrowDown/ArrowUp to move the active result.
- role: combobox
- name: `Jump to a worker or blocked gate`
- keyboard: the field is focused on open. ArrowDown and ArrowUp move the active result and are prevented from scrolling the page. Enter chooses. Escape closes.
- verify: json_path(path="document.activeElement.id", equals="palette-input")
- when:
  - The palette is open. The fleet may be empty.
- verify: visible(locator="#palette-input")
- does:
  - Writes the raw query to the palette slice and resets the active index to the first hit.
- verify: json_path(path="palette.query", equals="worker")
- does:
  - Computes hits from the fleet **in the store** — not from the rendered rows — filtering on the same haystack the runs filter uses, so a run hidden by that filter is still reachable here.
- verify: count(subject="palette results for a run hidden by the runs filter", equals=1)
- does:
  - Clamps the active index into the hit list on every move, so it never points past the end of a shortened list, and does nothing at all when there are no hits.
- verify: json_path(path="palette.active", equals=0)
- does:
  - Republishes `aria-activedescendant` on the input to the active result and scrolls that result into view.
- verify: json_path(path="palette.input.aria-activedescendant", equals="presult-0")
- does:
  - Removes `aria-activedescendant` from the palette input when nothing matches.
- verify: removed(subject="the palette input's aria-activedescendant")
- does:
  - Sends no request (the fleet is already in the browser).
- verify: count(subject="HTTP requests", equals=0)
- code: groom/groom/assets/dashboard.js::paletteHits@8c050d08b6fa
- code: groom/groom/assets/dashboard.js::PaletteResults@fb2140639a3c
- code: groom/groom/assets/dashboard.js::movePaletteActive@75aa0822155a

### select-command-palette-result

- on: [command-palette-result](#command-palette-result)
- trigger: pointer click or tap on a result, or Enter from the palette input with an active result.
- role: option
- one-per: `run` — one result per run matching the palette query in the fleet store.
- name: `{run.repo} #{run.row_id} {run.doing}` — followed by `gate` for a blocked run, otherwise its live label when present or its state.
- unique-by: `run.id` — the run identifier used as the rendered result key and selection target.
- keyboard: ArrowDown and ArrowUp move the active result.
- verify: json_path(path="$.aria-activedescendant", equals="presult-1")
- keyboard: Enter chooses the active result.
- verify: visible(locator="#detail .detail-head", text="{repo} #{short_handle}")
- keyboard: Escape abandons the palette.
- verify: absent(subject="command palette dialog")
- when:
  - The palette is open and at least one result matches.
- does:
  - Switches to runs mode first, so the row the operator just chose is on screen — the palette is reachable from files, diff, and settings alike.
  - Selects that run through the same selector the row click and the `j`/`k` keys use: store write, watch subscription, one detail fetch.
  - Closes the palette and returns focus to whatever opened it.
  - Chooses by run id rather than by rendered position, so the result list re-rendering under a concurrent push cannot open the wrong run.
- code: groom/groom/assets/dashboard.js::choosePaletteHit@79c641f3d2fb
- code: groom/groom/assets/dashboard.js::select@46f96b77d0ce
- code: groom/groom/assets/dashboard.js::setMode@d01c7d7c3d9c
- detail: [dashboard mode selection](../../concepts/dashboard-mode-selection.md)
- detail: [dashboard run selector](../../concepts/dashboard-run-selector.md)

### close-run-detail

- on: [detail-close-button](#detail-close-button)
- trigger: click, tap, Enter, or Space on the close control.
- role: button
- name: `Close run detail`
- keyboard: Tab reaches the control.
- verify: visible(locator="#detail-close-button", text="Close")
- keyboard: Enter or Space closes the detail.
- when:
  - A run is open in the detail pane.
- verify: json_path(path="store.selected", absent=true)
- does:
  - Takes the next selection and overview sequence numbers, so a slower reply for the closed run cannot land.
  - verify: json_path(path="selection.stale_fetch_is_ignored", equals=true)
  - Clears this tab's watch subscription.
  - verify: json_path(path="watch.subscription", equals="")
  - Clears the selected run, its detail and its Overview figures from the store.
  - verify: json_path(path="store.detail", absent=true)
  - Hides `#detail` and returns the run list to full width.
  - verify: absent(subject="#detail in the accessibility tree after close")
  - Keeps the run filter text and the filtered list as they were.
  - verify: json_path(path="runs_filter.value", equals="acme")
  - Does not change the active mode.

### switch-detail-tab

- on: [detail-tabs](#detail-tabs)
- trigger: click or tap on a tab, or ArrowLeft or ArrowRight while a tab has focus.
- role: tab
- name: Overview
- keyboard: ArrowLeft and ArrowRight select the neighbouring tab, wrapping at the ends.
- keyboard: focus moves to the selected tab.
- when:
  - A run is open in the detail pane.
- verify: json_path(path="keyboard.arrow_keys_switch_tabs", equals=true)
- does:
  - Writes the chosen tab to the store.
  - verify: json_path(path="store.tab", equals="details")
  - Sets `aria-selected` true on the chosen tab and false on the other.
  - verify: visible(locator="#detail-tabs", text="Details")
  - Swaps the tabpanel to that tab's content while the [gate strip](#detail-gate-strip) above the tabs stays.
  - verify: visible(locator="#detail .live-sec .metrics-grid")
  - Returning to Overview after a failed read requests the figures again.
  - Does not fetch the run detail again and does not change the watch subscription.

### open-detail-diff-tab

- on: [detail-diff-tab](#detail-diff-tab)
- trigger: click or tap on the Diff tab, or ArrowLeft or ArrowRight to it, or Enter or Space while it has focus.
- role: tab
- name: `Diff`
- keyboard: ArrowRight from Details selects the Diff tab and moves focus to it.
- verify: json_path(path="keyboard.arrow_keys_reach_diff", equals=true)
- when:
  - A live container run with a connected sidecar is open in the detail pane.
- does:
  - Writes the chosen tab to the store.
  - verify: json_path(path="store.tab", equals="diff")
  - Shows the changed files in a folder tree with per-file counts, above a `Not tracked by git yet` group of untracked files.
  - verify: visible(locator="#detail-diff-file-row", text="sign_in.py")
  - Shows the first changed file's diff in tree order.
  - verify: visible(locator="#detail-diff-body")
  - Shows another file's diff when its row is selected, with no request.
  - verify: count(subject="GET /diff/{container_id} requests when a file row is selected", equals=0)
  - Says an untracked file has no diff because git does not track it yet, when its row is selected.
  - verify: visible(locator="#detail-diff-panel", text="has no diff because git does not track it yet")
  - Sends no request, because the diff was read when the run was selected.
  - verify: count(subject="GET /diff/{container_id} requests when the tab opens", equals=0)
- code: groom/groom/assets/dashboard.js::DiffTab@ed8babf5c628
- code: groom/groom/assets/dashboard.js::diffEntries@ffb64254c8fd
- code: groom/groom/assets/dashboard.js::fileDiffMarkup@1286720f9b96
- tests: groom/tests/test_diff_tab_dynamic.py::test_opening_diff_lists_changed_files_in_a_tree_with_counts_and_shows_the_first_file
- tests: groom/tests/test_diff_tab_dynamic.py::test_untracked_files_sit_in_their_own_group_and_are_not_counted_in_the_tab
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_clean_checkout_says_so_and_the_tab_shows_no_count
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_checkout_with_only_untracked_files_lists_them_and_says_no_tracked_file_changed

### refresh-detail-diff

- on: [detail-diff-tab](#detail-diff-tab)
- trigger: click or tap, Enter, or Space on the `Read the diff again` button in the tab bar.
- role: button
- name: `Read the diff again`
- keyboard: the button is reached with Tab and operated with Enter or Space.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- when:
  - The Diff tab is selected and a first read has landed.
- does:
  - Fetches `GET /diff/{container_id}` from [get working tree diff](../../http/groom.md#get-working-tree-diff) once, naming the chosen checkout and, in the Since branch start view, `view=branch`.
  - verify: count(subject="GET /diff/{container_id} requests per activation", equals=1)
  - Keeps the file tree and the open diff on screen, disables the button and says `reading…` until the reply lands.
  - verify: visible(locator="#detail-diff-read", text="reading…")
  - Updates the tab's `+N −M` counts, the tree and the read time from the reply.
  - verify: visible(locator="#detail-diff-count", text="+9 −6")
  - Keeps the selected file when its path is still in the diff.
  - Keeps the chosen checkout and the chosen view.
- code: groom/groom/assets/dashboard.js::DiffRead@4ceebad9cc73
- code: groom/groom/assets/dashboard.js::loadRunDiff@a79bfdf4c0b1
- tests: groom/tests/test_diff_tab_dynamic.py::test_the_tab_says_when_the_diff_was_read_and_refresh_reads_again_and_updates_the_counts

### retry-detail-diff

- on: [detail-diff-tab](#detail-diff-tab)
- trigger: click or tap, Enter, or Space on the `Retry now` button in the unreadable-diff message.
- role: button
- name: `Retry now`
- keyboard: the button is reached with Tab and operated with Enter or Space.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- when:
  - The Diff tab is selected and the last read failed, or the Since branch start view could not find where the branch started.
- does:
  - Fetches `GET /diff/{container_id}` once, in the view in force.
  - verify: count(subject="GET /diff/{container_id} requests per activation", equals=1)
  - Replaces the message with the diff when the read succeeds.
  - verify: absent(subject="the unreadable-diff message after a successful read")
  - Keeps the message when the read fails again, and never shows it as no changes.
  - verify: omits(subject="unreadable diff panel", text="no uncommitted changes")
- code: groom/groom/assets/dashboard.js::DiffTab@ed8babf5c628
- code: groom/groom/assets/dashboard.js::loadRunDiff@a79bfdf4c0b1
- tests: groom/tests/test_diff_tab_dynamic.py::test_an_unreadable_diff_says_so_offers_a_retry_and_clears_when_a_read_succeeds
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_read_the_sidecar_errors_on_also_reads_as_unreadable_never_as_no_changes
- tests: groom/tests/test_diff_tab_dynamic.py::test_an_empty_diff_from_a_sidecar_too_old_to_report_failure_cannot_be_confirmed

### select-detail-checkout

- on: [detail-checkout-select](#detail-checkout-select)
- trigger: choosing another checkout in the select, with the pointer or with ArrowUp and ArrowDown.
- role: combobox
- name: `Checkout`
- keyboard: the select is reached with Tab and its value changes with ArrowUp and ArrowDown.
- verify: json_path(path="keyboard.tab_reachable", equals=true)
- when:
  - The Files or Diff tab of a live container run is selected and the run has more than one checkout.
  - The chosen checkout differs from the run's current one.
- does:
  - Keeps the choice for this run in the page's memory.
  - verify: json_path(path="store.checkouts.run", equals="web-app")
  - Reads that checkout's diff once, naming the checkout, and shows the tab's `+N −M` for it.
  - verify: visible(locator="#detail-diff-count", text="+1 −2")
  - Reads that checkout's tree once when the Files tab is shown, and shows it.
  - verify: count(subject="GET /files/{container_id} requests per choice", equals=1)
  - Clears the Files tab's selected file and its folder collapse state.
  - verify: visible(locator="#detail-files-panel", text="Select a file to read it.")
  - Keeps the choice when the operator moves between Files and Diff.
  - verify: count(subject="reads when moving between Files and Diff", equals=0)
  - Leaves the selected run unchanged.
  - verify: unchanged(subject="selected run")
  - Does not move the run selection when `j` or `k` is pressed with the select focused.
  - verify: unchanged(subject="selected run after j or k with the select focused")
- code: groom/groom/assets/dashboard.js::selectCheckout@fe08d1478779
- code: groom/groom/assets/dashboard.js::setCheckout@912b63a12a8d
- detail: [run checkout selection](../../concepts/run-checkout-selection.md)
- tests: groom/tests/test_checkout_selector_dynamic.py::test_selecting_a_checkout_shows_its_change_and_its_tree_and_the_size_follows
- tests: groom/tests/test_checkout_selector_dynamic.py::test_one_selection_governs_files_and_diff_and_moving_between_them_reads_nothing_more
- tests: groom/tests/test_checkout_selector_dynamic.py::test_changing_the_checkout_clears_the_open_file_and_the_collapsed_folders_of_files
- tests: groom/tests/test_checkout_selector_dynamic.py::test_j_and_k_with_the_selector_focused_do_not_move_the_run_selection
