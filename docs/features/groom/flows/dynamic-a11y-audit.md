---
type: flow
slug: dynamic-a11y-audit
title: Dynamic accessibility audit
---
# Dynamic accessibility audit

This journey covers how groom's accessibility is actually measured: by booting a
real groom over a synthetic fleet, driving a real Chromium through every reachable
pane of the [groom dashboard](../gui/screens/groom-dashboard.md), and running
axe-core against the live DOM in each one — plus two keyboard checks axe cannot
perform. It replaces the retired static linter, which parsed
`groom/groom/templates/dashboard.html` with a hand-rolled tag scanner.

The static reader stopped being able to see the dashboard the moment the panes
became islands. The template now ships five empty pane roots, and every control an
operator can reach — run rows, the answer form, the repository listbox, the file
tree, the diff table, the trace rows — is created by JavaScript from JSON that
arrives over a socket. A static lint of that template inspects markup no operator
ever meets, so a green result asserted nothing. The audit had to move to where the
controls exist, which is the running page.

axe-core is vendored at `groom/tests/vendor/axe.min.js` and injected from disk.
Nothing on this path reaches a CDN — the same rule the shipped dashboard obeys
applies to the test that measures it. It lives under `tests/vendor/` rather than
`groom/groom/assets/` precisely because it is not shipped: it is a measuring
instrument, not part of the product surface.

- start: a checkout of groom with its test dependencies installed, Playwright's
  Chromium present (`uv run playwright install chromium`), and axe-core vendored
  under `groom/tests/vendor/`. No Docker daemon, no running workflow container,
  and no network access is required. When the browser or the vendored axe bundle
  is missing the audit skips loudly rather than failing, so a machine without a
  browser does not report an accessibility result it never measured.
- code: groom/tests/test_a11y_dynamic.py::_workspace
- code: groom/tests/test_a11y_dynamic.py::_seed
- code: groom/tests/test_a11y_dynamic.py::_Live
- code: groom/tests/test_a11y_dynamic.py::_live
- code: groom/tests/test_a11y_dynamic.py::_open
- code: groom/tests/test_a11y_dynamic.py::_drive
- code: groom/tests/test_a11y_dynamic.py::_scan
- code: groom/tests/test_a11y_dynamic.py::_check_mode
- code: groom/tests/test_a11y_dynamic.py::teardown_module
- code: groom/groom/app.py::create_app
- steps:
  1. The harness builds a workspace the way a native run leaves one: a checkout
     under a temporary directory, committed, then dirtied. That is what gives the
     Files pane a tree to render and the Diff pane a working-tree diff to parse.
     Repository and branch names are neutral placeholders, because this repository
     ships publicly.
  2. The harness seeds the process-local [workflow registry](../concepts/workflow-registry.md)
     with three runs covering every row state — one blocked, one running, one
     finished — and clears the
     [dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md).
     The blocked run carries one [gate info](../concepts/gate-info.md) whose
     question is markdown, which is what puts a real answer form on the page; the
     running run gets a batch of spans so the telemetry table has rows.
  3. The harness boots the real application factory on a free loopback port in a
     background thread, replacing only the Docker reconciliation pass — startup
     discovery would otherwise prune the synthetic fleet on its way past. The
     [live clock](../http/groom.md#schedule-live-clock), the alert rule ticker, the
     websocket, and every route are left exactly as they ship, so the page under
     test is the page groom serves.
  4. Playwright launches Chromium once and the booted server, browser, and
     temporary directories are shared across every check in the file. A browser
     launch plus a lifespan startup costs about two seconds; paying it once per
     pane to prove the same five panes accessible would be time spent on nothing.
  5. Each check opens a page at the server's root, waits for the first run row to
     exist — which only happens after the socket has delivered a
     [dashboard state payload](../dashboard-state-payload.md) and the islands have
     rendered it — and then injects the vendored axe bundle from disk.
  6. The harness drives the page into one pane and waits for that pane's content to
     actually load. An empty pane passes axe trivially and proves nothing, so the
     runs check selects the blocked row and waits for the answer textarea; the
     files and diff checks open the repository picker, select an entry, and wait for
     a tree leaf and a rendered viewer; the telemetry check waits for table rows.
  7. axe runs against `document` — not against the pane's subtree — once per mode.
     That is deliberate rather than lazy: inactive panes are `display:none`, which
     axe already excludes, so one scan per mode covers that mode's pane *plus* the
     shell around it — the [activity rail](../gui/screens/groom-dashboard.md#activity-rail),
     the [status bar](../gui/screens/groom-dashboard.md#statusbar-region), the
     [connection chip](../gui/screens/groom-dashboard.md#connection-chip), and the
     [toast region](../gui/screens/groom-dashboard.md#toast-region) — and so catches
     a shell regression five times over.
  8. Only violations are collected, and each is reported with its rule id, impact,
     help text, and up to six offending selectors. A non-empty violation list fails
     that pane's check with that report as the message, so the failure names the
     element rather than only the count.
  9. Two keyboard checks cover what axe structurally cannot: axe inspects the
     markup's accessibility properties, it does not press Tab. The first asserts
     every [activity rail](../gui/screens/groom-dashboard.md#activity-rail) button
     is in the tab order and *operable* — focus one, press Enter, and the pane must
     actually change and announce itself through `aria-pressed`. A click-only
     handler passes axe and fails here.
  10. The second answers a gate without a mouse: focus the
      [detail answer textarea](../gui/screens/groom-dashboard.md#detail-answer-textarea),
      type, press Tab, and assert focus lands on that form's submit button, then
      press Enter and wait for the textarea to clear. The answer travels the real
      [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md)
      path and lands in the gate file on disk, so this is an end-to-end keyboard
      path and not a focus-order assertion.
  11. Teardown closes the browser, stops the server, and removes the temporary
      directories while the interpreter is still healthy — from pytest's module
      hook, and from a `finally` in the standalone runner. It is deliberately not
      an `atexit` callback: by the time those run, CPython has banned new threads
      and the server's shutdown spawns one, which ends in a traceback printed after
      the results.
- end: every reachable dashboard pane has been scanned by axe-core against the DOM
  an operator would actually receive, with zero violations, and the two paths with
  no mouse-free alternative — choosing a pane and answering a gate — have been
  exercised by keyboard. On a machine without Chromium or the vendored axe bundle,
  every check skips with a printed reason and the suite passes without claiming an
  accessibility result. The temporary workspace, the seeded fleet, the server
  thread, and the browser are all gone; nothing persists between runs.
- verify: groom/tests/test_a11y_dynamic.py::test_runs_pane_with_an_open_gate_is_accessible,
  groom/tests/test_a11y_dynamic.py::test_files_pane_is_accessible,
  groom/tests/test_a11y_dynamic.py::test_diff_pane_is_accessible,
  groom/tests/test_a11y_dynamic.py::test_telemetry_pane_is_accessible,
  groom/tests/test_a11y_dynamic.py::test_settings_pane_is_accessible,
  groom/tests/test_a11y_dynamic.py::test_the_activity_rail_is_reachable_and_operable_by_keyboard,
  groom/tests/test_a11y_dynamic.py::test_the_answer_form_is_reachable_and_submittable_by_keyboard
