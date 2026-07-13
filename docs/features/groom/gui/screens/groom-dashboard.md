---
type: screen
slug: groom-dashboard
title: groom dashboard
---
# groom dashboard

- code: groom/groom/app.py::index
- route: `/`; live-verified — selecting an inbox row, editing the answer textarea, and every activity-mode switch stay on this same landed path with no browser navigation.
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- verify: groom/tests/test_render.py::test_dynamic_regions_have_stable_ids_and_oob_flag

The `groom` dashboard is the browser screen served by the [root dashboard endpoint](../../http/groom.md#get-root-dashboard-html). It is the operator console for the [operator inbox](../../operator-inbox.md), repository file browser, working-tree diff view described by [changes view](../../changes-view.md), and manual reconciliation controls for the [worker tree](../../worker-tree.md). The screen opens a browser websocket to `/ws`, receives out-of-band updates for the inbox list and status bar, and fetches selected worker, repository, file, and diff details on demand so live broadcasts do not overwrite in-progress operator input.

The visible shell has four activity modes selected by the left activity bar: inbox, files, diff, and settings. The app starts in inbox mode, holds the selected worker id, the selected `(container, repo)` pair, and transient overlay state for the repository picker and command palette in browser state, and keeps the source of truth for workflow rows and counts on the server. Selecting an inbox row follows [select inbox worker row](#select-inbox-worker-row), which marks one [inbox worker row](#inbox-worker-row) selected and loads [get worker detail](../../http/groom.md#get-worker-detail) into the detail pane without changing the active dashboard mode.

## Layout

- app root: `.app[data-mode]`, connected to `WS /ws`; `data-mode` controls which pane is visible.
- activity bar: left rail with inbox, files, diff, and settings mode controls; selecting the settings gear follows [select activity settings mode](#select-activity-settings-mode).
- inbox pane: filter input, live inbox rows in `#inbox-list`, and selected worker detail in `#detail`.
- files pane: repository picker, lazily loaded file tree, and selected file viewer.
- diff pane: repository picker, lazily loaded changed-file tree, and selected-file diff viewer.
- settings pane: manual container rescan and browser notification permission controls.
- status bar: live fleet counts, websocket liveness label, refresh control, and command-palette hint.
- overlays: shared repository picker in `#repo-menu-wrap`, command palette in `#palette`, and toast stack in `#toasts`.

## States

- mode: `inbox` by default; `files`, `diff`, and `settings` are mutually exclusive alternatives.
- selected worker: absent until an inbox row, palette result, or keyboard row movement writes [dashboard selected worker state](../../dashboard-selected-worker-state.md); selecting one refreshes `#detail` from `GET /worker/{container_id}`.
- selected repository: absent until a repository menu item is chosen; choosing one writes the [dashboard selected repository state](../../dashboard-selected-repository-state.md), updates both repository picker labels, and loads the currently active files or diff pane.
- repository menu: closed by default with `#repo-menu-wrap` lacking `open`; opening positions it below the active picker, fetches `GET /repos`, clears the menu search, and focuses `#repo-search`; closing removes only the `open` class and preserves menu contents, search text, picker labels, and selected repository state.
- command palette: closed by default; `Ctrl+K` or `Meta+K` opens it, clears its input, renders current inbox rows as results, and focuses `#palette-input`.
- live regions: `#inbox-list` and `#statusbar` are replaced by websocket out-of-band swaps; markdown questions are re-rendered after swaps through the escaped text-node to `marked` to DOMPurify path.

## Components

### activity-inbox-mode

- selector: `.act-btn[data-mode="inbox"]`
- role: none; rendered as a clickable `div`, not a semantic button.
- name: none as a robust control name; the element only has `title="Inbox"` and an inline SVG icon, with no visible text, `aria-label`, or focusable control role.
- keyboard: none; a11y gap because the element is not focusable and has no Enter/Space handling.
- parent: [groom dashboard](#groom-dashboard)
- states: inactive; active when the root `.app` has `data-mode="inbox"`.
- code: groom/groom/templates/dashboard.html::setMode
- props:
  - `data-mode`: literal `inbox`; required; used as the mode value passed to the shared mode-switch handler.
  - `title`: literal `Inbox`; required; tooltip text only, not a complete accessible-control contract for this non-focusable `div`.
  - `class`: includes `act-btn`; includes `active` exactly when inbox mode is selected.
- dom: icon-only activity-bar control inside `#activitybar`, rendered before files, diff, spacer, and settings controls; contains only an inline SVG inbox icon and no text node.
- leads-to: [select activity inbox mode](#select-activity-inbox-mode), which shows the inbox pane in this screen, containing the [operator inbox](../../operator-inbox.md) row list and selected worker detail.

### activity-files-mode

- selector: `.act-btn[data-mode="files"]`
- role: none; rendered as a clickable `div`, not a semantic button.
- name: none as a robust control name; the element only has `title="Files"` and an inline SVG folder icon, with no visible text, `aria-label`, or focusable control role.
- keyboard: none; a11y gap because it is not focusable and has no Enter/Space handling.
- parent: [groom dashboard](#groom-dashboard)
- states: inactive when the root `.app` is in inbox, diff, or settings mode; active when the root `.app` has `data-mode="files"` and this control has the `active` class.
- code: groom/groom/templates/dashboard.html::setMode
- props:
  - `data-mode`: literal `files`; required; used as the mode value passed to the shared mode-switch handler.
  - `title`: literal `Files`; required; tooltip text only, not a complete accessible-control contract for this non-focusable `div`.
  - `class`: includes `act-btn`; includes `active` exactly when files mode is selected.
- dom: icon-only activity-bar control inside `#activitybar`, rendered after inbox and before diff, spacer, and settings controls; contains only an inline SVG folder icon and no text node.
- leads-to: files pane in this screen, containing the [files repository picker button](#files-repository-picker-button), `#files-tree`, and `#file-view`; when a repository is already selected, entering this mode reloads that repository's file tree.

### activity-diff-mode

- selector: `.act-btn[data-mode="diff"]`
- role: none; rendered as a clickable `div`, not a semantic button.
- name: none as a robust control name; the element only has `title="Diff"` and an inline SVG icon, with no visible text, `aria-label`, or focusable control role.
- keyboard: none; a11y gap because it is not focusable and has no Enter/Space handling.
- parent: [groom dashboard](#groom-dashboard)
- states: inactive when the root `.app` is in inbox, files, or settings mode; active when the root `.app` has `data-mode="diff"` and this control has the `active` class.
- code: groom/groom/templates/dashboard.html::setMode
- props:
  - `data-mode`: literal `diff`; required; used as the mode value passed to the shared mode-switch handler.
  - `title`: literal `Diff`; required; tooltip text only, not a complete accessible-control contract for this non-focusable `div`.
  - `class`: includes `act-btn`; includes `active` exactly when diff mode is selected.
- dom: icon-only activity-bar control inside `#activitybar`, rendered after inbox and files and before spacer and settings controls; contains only an inline SVG bidirectional-arrows icon and no text node.
- leads-to: diff pane in this screen, containing the [diff repository picker button](#diff-repository-picker-button), `#diff-tree`, and `#diff-view`; when a repository is already selected, entering this mode reloads that repository's working-tree diff described by [changes view](../../changes-view.md).

### activity-settings-mode

- selector: `.act-btn[data-mode="settings"]`
- role: none; rendered as a clickable `div`, not a semantic button.
- name: none as a robust control name; the element only has `title="Settings"` and an inline SVG gear icon, with no visible text, `aria-label`, or focusable control role.
- keyboard: none; a11y gap because it is not focusable and has no Enter/Space handling.
- parent: [groom dashboard](#groom-dashboard)
- states: inactive when the root `.app` is in inbox, files, or diff mode; active when the root `.app` has `data-mode="settings"` and this control has the `active` class.
- code: groom/groom/templates/dashboard.html::setMode
- props:
  - `data-mode`: literal `settings`; required; used as the mode value passed to the shared mode-switch handler.
  - `title`: literal `Settings`; required; tooltip text only, not a complete accessible-control contract for this non-focusable `div`.
  - `class`: includes `act-btn`; includes `active` exactly when settings mode is selected.
- dom: icon-only activity-bar control inside `#activitybar`, rendered after the activity-bar spacer as the bottom rail control; contains only an inline SVG gear icon and no text node.
- leads-to: settings pane in this screen, containing the [settings rescan button](#settings-rescan-button) and [settings enable notifications button](#settings-enable-notifications-button); entering this mode does not reload data or request notification permission.

### inbox-filter-input

- selector: `input.filter[name="q"]`
- role: searchbox.
- name: `Filter incoming messages`.
- keyboard: text entry; browser search-input clear/search behavior; each changed input value is debounced for 250 ms before filtering, and native search events filter immediately.
- parent: [groom dashboard](#groom-dashboard)
- states: empty query shows every workflow that has at least one open gate; non-empty query narrows the operator inbox by case-insensitive substring match; focused state accepts ordinary text editing and browser search-field controls.
- code: groom/groom/templates/dashboard.html
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- props:
  - `class`: literal `filter`; required; identifies the inbox-pane search field for styling and as the stable selector for this component.
  - `type`: literal `search`; required; exposes native searchbox semantics and user-agent search-field behavior.
  - `name`: literal `q`; required; serialized as the query parameter consumed by the search fragment endpoint.
  - `aria-label`: literal `Filter incoming messages`; required; the durable accessible name.
  - `placeholder`: literal `Filter messages…`; required visual hint, not the accessible name.
  - `hx-get`: literal `/search`; required; destination for filter requests.
  - `hx-trigger`: literal `input changed delay:250ms, search`; required; sends changed text-entry events after a 250 ms debounce and also sends native search events such as clearing the field.
  - `hx-swap`: literal `none`; required; prevents direct replacement of the input or its container so the endpoint's out-of-band `#inbox-list` fragment is the only DOM update from the request.
- dom: native search input in the inbox pane header, rendered after the visible `Inbox — needs you` heading text and before the live `#inbox-list` region.
- leads-to: [GET /search](../../http/groom.md#get-search-fragment) on changed input values and search events; the response updates `#inbox-list` out of band while status counts remain fleet-wide.

### inbox-worker-row

- selector: `#inbox-list [data-worker-id]`
- role: none; rendered as a clickable `div`, not a semantic button or list option.
- name: none as a robust control name; visible text combines repository label, short worker id, selected gate path or current node/exit hint, and an optional question preview, but the row has no role, `aria-label`, or focusable name-bearing element.
- keyboard: global `j`/`k` move selection across inbox rows when focus is not in an input or textarea; direct row focus and Enter/Space activation are absent, which is an a11y gap.
- parent: [groom dashboard](#groom-dashboard)
- states: normal; selected when its `data-worker-id` equals the browser's selected worker id and the `selected` class is applied; blocked when the workflow state is `blocked` and the `blocked` class plus question preview are present; gated non-blocked when a running, idle, or finished worker still has an open gate and therefore appears without the blocked class or question preview.
- code: groom/groom/render.py::_inbox_row
- verify: groom/tests/test_render.py::test_inbox_shows_only_workers_with_open_gates
- verify: groom/tests/test_render.py::test_inbox_orders_gated_workers_by_state_then_name
- verify: groom/tests/test_render.py::test_exit_code_hint_only_on_finished_with_code
- props:
  - source workflow: required [operator inbox](../../operator-inbox.md) worker that has at least one open gate; workers without open gates are not rendered as inbox rows.
  - `data-worker-id`: required string; the escaped workflow container id; used by row click selection, palette result selection, keyboard row movement, and the `GET /worker/{container_id}` detail request.
  - `data-state`: required enum string from the workflow state value; used by the command palette to render the row's state hint and dot.
  - `class`: required; always includes `row`, adds `blocked` exactly when `data-state` is `blocked`, and may later gain `selected` in browser state.
  - gate source: first open gate after sorting [gate info](../../concepts/gate-info.md) records by `file_path`; required by the inbox caller because only gated workflows become rows; supplies the displayed gate path and, when blocked, the question preview.
  - tail text: required; the sorted gate file path when an open gate is present; otherwise the [operator inbox exit hint](../../operator-inbox.md#method-render-exit-hint) `exited {code}` when the workflow is finished and has an exit code; otherwise the workflow current node. The exit hint uses `exit-ok` for code `0`, `exit-err` for every other known integer, escapes the code text, and is serializer behavior not normally reached through the gated-only inbox list.
  - repository branch label: required; produced by [method-render-repository-label](../../operator-inbox.md#method-render-repository-label) as `repo_name@repo_branch` when a branch exists, otherwise `repo_name`, otherwise an em dash placeholder.
  - worker id label: required; `#` followed by the first four characters of `container_id`, or `#----` when the id is empty.
  - state marker: required [workflow state dot renderer](../../concepts/workflow-state-dot-renderer.md) fragment; one empty visual dot whose classes are `dot` and the escaped workflow state value.
  - type badge: optional [workflow type badge renderer](../../concepts/workflow-type-badge-renderer.md) fragment; omitted when `workflow_type` is empty; otherwise contains the escaped workflow type text, `data-type`, and a deterministic hue style derived from the type string.
  - question preview: optional [inbox question preview](../../concepts/inbox-question-preview.md); present only for blocked workers with a gate, derived from the first non-empty question line after trimming leading markdown quote/list/code markers and capped at 140 characters.
  - escaping: required through the [HTML escape helper](../../concepts/html-escape-helper.md) for container id, workflow state value, repository label parts, workflow type, short id text, gate file path, exit-code text, current node, and question preview before insertion into attributes or text nodes.
- dom: `<div class="row..." data-worker-id data-state>` inside live region `#inbox-list`; child `.line1` contains the [workflow state dot renderer](../../concepts/workflow-state-dot-renderer.md) fragment, optional [workflow type badge renderer](../../concepts/workflow-type-badge-renderer.md) fragment, `.repo-branch`, `.wid` short id in `#abcd` form, and `.gate` tail text; blocked rows append one `.q` question-preview block below the first line.
- leads-to: [GET /worker/{container_id}](../../http/groom.md#get-worker-detail) replacing selected worker detail in `#detail`; the browser URL and dashboard activity mode are not navigated by a pointer row click.

### detail-answer-textarea

- selector: `#detail textarea[name="answer"]`
- role: textbox.
- name: `Your answer…`, computed by the browser's accessible-name algorithm from the `placeholder` attribute because no `<label>`/`aria-label`/`aria-labelledby` is present; live-verified reachable as `getByRole("textbox", { name: "Your answer…" })`. Still an a11y gap in the durable-label sense (the name is a placeholder fallback, not an explicit label, and would disappear if the element gained one from another source), but it is not nameless and is not without a robust role-based locator.
- keyboard: Tab and Shift+Tab use normal document focus traversal; ordinary textarea editing keys insert and edit multiline text; Enter inserts a newline rather than submitting; submission is performed by the sibling [detail send answer button](#detail-send-answer-button) or by browser form submission behavior outside the textarea editing keys.
- parent: [groom dashboard](#groom-dashboard)
- states: empty with no default value; focused for multiline editing; edited with an unsent browser-local value; serialized on form submission; replaced only when the selected worker detail pane is explicitly refetched after a successful answer for the same selected worker.
- code: groom/groom/render.py::_answer_form
- verify: groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form
- props:
  - source workflow: required [operator inbox](../../operator-inbox.md) workflow container selected in the detail pane; supplies the hidden `workflow_id` field in the enclosing form.
  - source gate: required open gate file path; supplies the hidden `file_path` field in the enclosing form and scopes the answer when a workflow has multiple simultaneous gates.
  - `name`: literal `answer`; required; serialized as the websocket JSON frame's `answer` field by the enclosing `ws-send` form.
  - `placeholder`: literal `Your answer…`; required visual hint only, not a programmatic label.
  - `rows`: literal `4`; required; gives the multiline field a four-row default height.
  - value: string; optional; default empty string; user-authored operator answer text, preserved only in the browser DOM until the form is submitted or the detail pane is replaced.
- dom: native `<textarea>` rendered after hidden `cmd`, `workflow_id`, and `file_path` inputs and before `.answer-actions`; the enclosing `<form class="answer" ws-send>` is inside one `.gate-block` for a single gate.
- leads-to: [edit detail answer textarea](#edit-detail-answer-textarea) captures browser-local answer text; the submitted value becomes the `answer` field in a [dashboard websocket answer frame](../../dashboard-websocket-answer-frame.md) handled by [WS /ws](../../http/groom.md#websocket-dashboard).

### detail-send-answer-button

- selector: `#detail form.answer button[type="submit"]`
- role: button.
- name: `Send answer`.
- keyboard: Tab and Shift+Tab reach the native button in document order; Enter or Space activates it when focused; browser form submission behavior can also submit the enclosing form from compatible form controls outside the multiline textarea editing path.
- parent: [groom dashboard](#groom-dashboard)
- states: enabled whenever an open gate answer form is rendered; activated while focused; removed when its gate block is replaced after the selected worker is refetched or the gate no longer exists.
- code: groom/groom/render.py::_answer_form
- verify: groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch
- props:
  - source workflow: required [operator inbox](../../operator-inbox.md) workflow container selected in the detail pane; supplies the hidden `workflow_id` value submitted by the enclosing form.
  - source gate: required open gate file path in the selected workflow; supplies the hidden `file_path` value submitted by the enclosing form.
  - `type`: literal `submit` by default browser semantics for a `<button>` without an explicit `type`; required so activation submits the enclosing form.
  - `class`: literal `btn`; required visual button styling only.
  - text content: literal `Send answer`; required visible label and accessible name.
  - enclosing form `class`: literal `answer`; required stable scope for the gate-answer form.
  - enclosing form `ws-send`: present boolean attribute; required so the htmx websocket extension serializes the form fields as a JSON websocket message instead of performing an HTTP form navigation.
- dom: native submit `<button class="btn">Send answer</button>` inside `.answer-actions`, after the multiline answer textarea, inside one `<form class="answer" ws-send>` per open gate block in `#detail`.
- leads-to: [send detail answer](#send-detail-answer), which serializes hidden `cmd=answer`, hidden `workflow_id`, hidden `file_path`, and textarea `answer` into a dashboard websocket frame handled by [WS /ws](../../http/groom.md#websocket-dashboard).

### detail-working-tree-diff-toggle

- selector: `#detail details[data-diff] > summary`
- role: disclosure button; native `<summary>` control for a `<details>` disclosure.
- name: `Working-tree diff`.
- keyboard: Tab and Shift+Tab reach the native summary in document order when the selected worker detail contains open gates; Enter or Space toggles the native details disclosure between collapsed and expanded.
- parent: [groom dashboard](#groom-dashboard)
- states: collapsed before activation; expanded before the diff response arrives; expanded with diff loaded; expanded with `(no changes)` empty state; expanded with `failed to load diff` error text; collapsed after loading with the already-loaded diff retained in the disclosure body.
- code: groom/groom/render.py::_diff_disclosure
- verify: groom/tests/test_render.py::test_worker_detail_has_one_diff_disclosure
- props:
  - source workflow: required [operator inbox](../../operator-inbox.md) workflow container currently rendered in `#detail`; supplies the disclosure's worker container id.
  - `data-diff`: required escaped workflow container id on the enclosing `<details>`; used only to identify the worker-scoped disclosure block.
  - summary text: literal `Working-tree diff`; required visible label and accessible name.
  - `data-diff-target`: required boolean marker on the disclosure body; selects the element that receives loading text, diff HTML, empty-state HTML, or failure text.
  - `data-container`: required escaped workflow container id on the disclosure body; becomes the `container_id` path variable for the lazy `GET /diff/{container_id}` request.
  - `data-loaded`: absent by default; set to `1` after the first successful HTTP response is rendered so later expansions reuse the loaded body instead of refetching.
  - `class`: literal `disclosure` on the enclosing `<details>` and `diff-wrap` on the body; required for dashboard styling only.
- dom: exactly one `<details class="disclosure" data-diff="{container_id}">` is rendered after all gate question/answer blocks for a selected worker that has at least one open gate; it contains `<summary>Working-tree diff</summary>` followed by `<div class="diff-wrap" data-diff-target data-container="{container_id}"></div>`.
- leads-to: [toggle detail working tree diff](#toggle-detail-working-tree-diff), whose first expansion fetches [GET /diff/{container_id}](../../http/groom.md#get-workspace-diff) and renders the returned unified diff into the detail pane.

### files-repository-picker-button

- selector: `.repo-picker[data-picker="files"]`
- role: button.
- name: `Select container / repo…` until a repository is selected, then the selected repository menu label shared by the files and diff pickers.
- keyboard: Tab and Shift+Tab reach the native button when the files pane is active; Enter or Space activates it; Escape closes the repository menu after it opens through the document-level keyboard handler.
- parent: [groom dashboard](#groom-dashboard)
- states: files pane inactive but still present in the DOM; files pane active with the repository menu closed; repository menu open and positioned below this button; repository selected with this button's label replaced by the selected workflow/repository label; repository selected while another activity mode is active, retaining the label for the next files-pane visit.
- code: groom/groom/templates/dashboard.html::openRepoMenu
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- props:
  - `class`: literal `repo-picker`; required; selects the shared repository-picker click wiring and dashboard styling.
  - `type`: literal `button`; required; prevents form submission semantics and exposes native button activation behavior.
  - `data-picker`: literal `files`; required; distinguishes this files-pane picker from the diff-pane picker for stable selection and styling, while the current handler treats both pickers with the same shared overlay behavior.
  - label text: literal `Select container / repo…` before selection; required; visible text and accessible name supplied by `.repo-picker-label`.
  - selected label text: required after a [repository menu option](#repository-menu-option) is selected; copied from the option's `data-label` to every `.repo-picker-label`, including this button.
  - caret text: literal `▾`; required visual affordance only; not the accessible name.
- dom: native `<button class="repo-picker" type="button" data-picker="files">` in the files pane picker bar, rendered before `#files-tree` and `#file-view`; it contains a `.repo-picker-label` text span followed by a `.caret` span.
- leads-to: [open files repository picker](#open-files-repository-picker), which opens the shared repository menu overlay, loads [GET /repos](../../http/groom.md#get-repository-menu), and focuses [repository menu search input](#repository-menu-search-input); selecting a [repository menu option](#repository-menu-option) later loads the files pane for the selected container/repo pair.

### diff-repository-picker-button

- selector: `.repo-picker[data-picker="diff"]`
- role: button.
- name: `Select container / repo…` until a repository is selected, then the selected repository menu label shared by the files and diff pickers.
- keyboard: Tab and Shift+Tab reach the native button when the diff pane is active; Enter or Space activates it; Escape closes the repository menu after it opens through the document-level keyboard handler.
- parent: [groom dashboard](#groom-dashboard)
- states: diff pane inactive but still present in the DOM; diff pane active with the repository menu closed; repository menu open and positioned below this button; repository selected with this button's label replaced by the selected workflow/repository label; repository selected while another activity mode is active, retaining the label for the next diff-pane visit.
- code: groom/groom/templates/dashboard.html::openRepoMenu
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- props:
  - `class`: literal `repo-picker`; required; selects the shared repository-picker click wiring and dashboard styling.
  - `type`: literal `button`; required; prevents form submission semantics and exposes native button activation behavior.
  - `data-picker`: literal `diff`; required; distinguishes this diff-pane picker from the files-pane picker for stable selection and styling, while the current handler treats both pickers with the same shared overlay behavior.
  - label text: literal `Select container / repo…` before selection; required; visible text and accessible name supplied by `.repo-picker-label`.
  - selected label text: required after a [repository menu option](#repository-menu-option) is selected; copied from the option's `data-label` to every `.repo-picker-label`, including this button.
  - caret text: literal `▾`; required visual affordance only; not the accessible name.
- dom: native `<button class="repo-picker" type="button" data-picker="diff">` in the diff pane picker bar, rendered before `#diff-tree` and `#diff-view`; it contains a `.repo-picker-label` text span followed by a `.caret` span.
- leads-to: [open diff repository picker](#open-diff-repository-picker), which opens the shared repository menu overlay, loads [GET /repos](../../http/groom.md#get-repository-menu), and focuses [repository menu search input](#repository-menu-search-input); selecting a [repository menu option](#repository-menu-option) later loads the diff pane for the selected container/repo pair.

### repository-menu-search-input

- selector: `#repo-search`
- role: textbox.
- name: `Search container / repo`.
- keyboard: Tab and Shift+Tab use normal document focus traversal after a repository picker opens and focuses the field; ordinary text editing changes the filter query immediately; Escape closes the repository menu through the dashboard-level keydown handler; arrow keys have no repository-option navigation behavior.
- parent: [groom dashboard](#groom-dashboard)
- states: hidden with the repository menu closed; focused after a files or diff repository picker opens the menu; empty query showing every currently loaded repository option; non-empty query hiding currently loaded options whose `data-label` does not contain the query case-insensitively; loading state when `#repo-menu` still contains `Loading…` and no `.repo-item` rows; stale non-empty query possible when text is entered before the `/repos` response arrives because the filter is not re-run after the response replaces `#repo-menu`.
- code: groom/groom/templates/dashboard.html::filterRepoMenu
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- props:
  - `id`: literal `repo-search`; required; selects the field for repository-picker focus and input-event wiring.
  - `type`: literal `text`; required; exposes native single-line textbox semantics rather than searchbox-specific browser behavior.
  - `aria-label`: literal `Search container / repo`; required; supplies the accessible name because no visible `<label>` is rendered.
  - `placeholder`: literal `Search container / repo…`; required visual hint only, not the accessible name.
  - value: string; optional browser-local query; default empty whenever a repository picker opens because `openRepoMenu` clears it before fetching repository options.
  - option source: currently loaded [repository menu option](#repository-menu-option) rows inside `#repo-menu`; required for filtering to affect visible menu contents.
- dom: native single-line text input at the top of `.repo-menu-box` inside the shared `#repo-menu-wrap` overlay, rendered before the `#repo-menu` option container and present in the DOM even when the overlay is closed.
- leads-to: [filter repository menu options](#filter-repository-menu-options), which filters already-loaded [repository menu option](#repository-menu-option) rows by their `data-label` text without requesting new data or selecting a repository.

### repository-menu-option

- selector: `#repo-menu .repo-item`
- role: option; explicit `role="option"` on a rendered `div`, without an owning `listbox` role on `#repo-menu`.
- name: visible text from the optional workflow type badge followed by the repository option label generated from workflow/container name and checkout directory, for example `coder coder-001/predykt` when a `coder` badge is rendered or `author-002` when no checkout directory and no badge are present.
- keyboard: none; a11y gap because rendered options are not focusable, no listbox keyboard navigation is implemented, and Enter/Space cannot activate an individual option.
- parent: [groom dashboard](#groom-dashboard)
- states: visible after [GET /repos](../../http/groom.md#get-repository-menu) replaces the menu loading state; filtered out when [repository menu search input](#repository-menu-search-input) sets inline `display: none`; selected only transiently during pointer activation with no persisted selected styling, `aria-selected`, or focus movement; absent when no eligible repository entries exist and the menu instead renders `No repositories available.`
- code: groom/groom/render.py::render_repo_menu
- verify: groom/tests/test_render.py::test_repo_menu_one_entry_per_container_repo
- verify: groom/tests/test_render.py::test_repo_menu_empty_when_no_entries
- verify: groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo
- props:
  - source entry: required tuple of one workflow container and one checkout directory from the repository menu endpoint; a workflow with no checkout directories contributes one volume-root option with an empty repository value.
  - ordering: required; options are grouped by workflow after sorting workflows by dashboard state order and then workflow name, and checkout directories appear in the order supplied for that workflow without an additional row-level sort.
  - row cardinality: one row per checkout directory when the source checkout list is non-empty; exactly one synthetic volume-root row when the source checkout list is empty; no option rows when the entire rendered entry list is empty.
  - `class`: literal `repo-item`; required; selects the option for search filtering and delegated click selection.
  - `role`: literal `option`; required on the row, but incomplete because the parent menu has no `role="listbox"` and the row is not focusable.
  - `data-container`: required string; escaped workflow container id; becomes the selected container id used by later files and diff requests.
  - `data-repo`: required string; escaped volume-relative checkout directory; empty string means the workflow workspace volume root.
  - `data-label`: required string; escaped visible picker label; derived as `workflow.name/repo` for a checkout row and `workflow.name` for a synthetic volume-root row; copied into every `.repo-picker-label` after selection and used as the case-insensitive menu-search source.
  - state dot: required; visual workflow state marker rendered before the label as an empty span, so the workflow state is not part of the option's accessible name and is not exposed as selected or status text.
  - workflow type badge: optional [workflow type badge renderer](../../concepts/workflow-type-badge-renderer.md) fragment; rendered when the workflow has a workflow type, carries `data-type` plus type text, and contributes that visible type text to the option's accessible name before `.repo-item-label`.
  - `.repo-item-label`: required span whose text is the same escaped label stored in `data-label`.
- dom: one `<div class="repo-item" role="option" data-container data-repo data-label>` inside `#repo-menu` per rendered repository-menu row; contains a [workflow state dot renderer](../../concepts/workflow-state-dot-renderer.md) fragment, optional [workflow type badge renderer](../../concepts/workflow-type-badge-renderer.md) fragment, and `.repo-item-label` text; when the endpoint has no rows, this component is absent and `#repo-menu` instead contains `<div class="repo-empty">No repositories available.</div>`.
- leads-to: [select repository menu option](#select-repository-menu-option), which selects the container/repo pair, closes the menu, updates both picker labels, and loads the active files or diff pane.

### files-directory-toggle

- selector: `#files-tree .tree-dir-head`
- role: none; rendered as a clickable `div`, not a semantic disclosure control.
- name: none as a robust control name; visible text is the directory basename preceded by the `▾` chevron, but the clickable `div` has no role, `aria-label`, `aria-expanded`, or focusable name-bearing element.
- keyboard: none; a11y gap because the generated directory header is not focusable and has no Enter/Space handling.
- parent: [groom dashboard](#groom-dashboard)
- states: expanded by default; collapsed when the enclosing `.tree-dir` has the `collapsed` class; state is visual only and not mirrored to ARIA.
- code: groom/groom/templates/dashboard.html::renderPathTree
- props:
  - source directory: required node in the [dashboard files path tree](../../dashboard-files-path-tree.md) built from newline-separated repo-relative file paths returned by [GET /files/{container_id}](../../http/groom.md#get-workspace-file-list); one toggle is rendered for every directory segment with at least one child directory or file.
  - directory name: required string; escaped before insertion and rendered as the visible label after the chevron; sorting is case-sensitive JavaScript object-key order after `Object.keys(...).sort()`.
  - `class`: literal `tree-dir-head`; required; selects the clickable generated directory header for delegated files-tree click handling and dashboard styling.
  - parent `class`: literal `tree-dir`; required; receives or loses `collapsed` when this header is activated.
  - chevron text: literal `▾`; required visual expansion affordance in child `<span class="tchev">`; it does not expose disclosure state to assistive technology.
  - children container `class`: literal `tree-children`; required; contains recursively rendered child directories and file rows whose visibility is controlled by the parent `.tree-dir.collapsed` state.
- dom: generated `<div class="tree-dir"><div class="tree-dir-head"><span class="tchev">▾</span>{directory}</div><div class="tree-children">...</div></div>` inside `#files-tree`; it appears only after a repository is selected and the files pane successfully renders a non-empty file list.
- leads-to: [toggle files directory](#toggle-files-directory), which toggles visibility of this directory's child paths in the files tree without selecting a file or loading file contents.

### files-file-row

- selector: `#files-tree .tree-file[data-path]`
- role: none; rendered as a clickable `div`, not a semantic button or treeitem.
- name: none as a robust control name; visible text is the file basename in `.fname`, but the clickable row has no role, `aria-label`, or focusable name-bearing element.
- keyboard: none; a11y gap because the row is not focusable and no Enter, Space, arrow-key tree navigation, or shortcut activation is implemented for file selection.
- parent: [groom dashboard](#groom-dashboard)
- states: unselected after the files tree is rendered; active when this exact row has the `active` class after pointer selection; inactive when any other file row in `#files-tree` is selected and the prior active class is removed; absent while no repository is selected, the files endpoint is loading, the selected repository has no files, or the files request failed.
- code: groom/groom/templates/dashboard.html::openFile
- props:
  - source path: required repo-relative file path returned as one newline-delimited entry from [GET /files/{container_id}](../../http/groom.md#get-workspace-file-list) and retained in a [dashboard files path tree](../../dashboard-files-path-tree.md) file leaf; directory segments are used only to place the row under generated directory toggles, and the full path is retained on the row.
  - file basename: required string; the last slash-delimited segment of the source path, sorted locale-aware against sibling files by basename and escaped before insertion.
  - `class`: literal `tree-file`; required; gains `active` exactly for the currently selected file row in the files tree.
  - `data-path`: required escaped repo-relative full file path; becomes the `path` query parameter for the file-content request.
  - `.fname`: required child span containing the escaped file basename; this is visible text only, not a programmatic control name.
- dom: generated `<div class="tree-file" data-path="{path}"><span class="fname">{basename}</span></div>` inside `#files-tree`, nested under zero or more `.tree-dir > .tree-children` containers after a repository selection successfully renders a non-empty path list.
- leads-to: [select files file row](#select-files-file-row), which fetches [GET /file/{container_id}](../../http/groom.md#get-workspace-file-content) with the selected repository and file path, then renders the returned raw text in `#file-view`.

### diff-directory-toggle

- selector: `#diff-tree .tree-dir-head`
- role: none; rendered as a clickable `div`, not a semantic disclosure control.
- name: none as a robust control name; visible text is the directory basename preceded by the `▾` chevron, but the clickable `div` has no role, `aria-label`, `aria-expanded`, or focusable name-bearing element.
- keyboard: none; a11y gap because the generated directory header is not focusable and has no Enter/Space handling.
- parent: [groom dashboard](#groom-dashboard)
- states: expanded by default after the diff tree renders; collapsed when the enclosing `.tree-dir` has the `collapsed` class; state is visual only and not mirrored to ARIA.
- code: groom/groom/templates/dashboard.html::renderDiffTree
- props:
  - source directory: required node in the [dashboard diff file tree](../../dashboard-diff-file-tree.md) built from parsed unified diff file entries returned by [GET /diff/{container_id}](../../http/groom.md#get-workspace-diff); one toggle is rendered for every directory segment that contains at least one changed file or child directory.
  - directory name: required string; derived from the selected diff file's new path unless that path is `/dev/null`, in which case the old path is used; escaped before insertion and rendered as the visible label after the chevron.
  - ordering: required; sibling directories are rendered by JavaScript object-key sort order before sibling changed-file rows, and changed-file rows inside each directory are sorted by basename with `localeCompare`.
  - `class`: literal `tree-dir-head`; required; selects the clickable generated directory header for delegated diff-tree click handling and dashboard styling.
  - parent `class`: literal `tree-dir`; required; receives or loses `collapsed` when this header is activated.
  - chevron text: literal `▾`; required visual expansion affordance in child `<span class="tchev">`; it does not expose disclosure state to assistive technology.
  - children container `class`: literal `tree-children`; required; contains recursively rendered child directories and changed-file rows whose visibility is controlled by the parent `.tree-dir.collapsed` state.
- dom: generated `<div class="tree-dir"><div class="tree-dir-head"><span class="tchev">▾</span>{directory}</div><div class="tree-children">...</div></div>` inside `#diff-tree`; it appears only after a repository is selected, the diff endpoint returns non-empty unified diff text, Diff2Html parses at least one changed file, and at least one changed-file path contains a directory segment.
- leads-to: [toggle diff directory](#toggle-diff-directory), which toggles visibility of this directory's child changed files in the diff tree without selecting a file or rendering a diff in `#diff-view`.

### diff-file-row

- selector: `#diff-tree .tree-file[data-file-idx]`
- role: none; rendered as a clickable `div`, not a semantic button or treeitem.
- name: none as a robust control name; visible text is the file basename plus added/deleted line counts, but the generated row has no role, `aria-label`, or focusable name-bearing element.
- keyboard: none; a11y gap because the row is not focusable and no Enter, Space, arrow-key tree navigation, or shortcut activation is implemented for selecting a changed file.
- parent: [groom dashboard](#groom-dashboard)
- states: absent while no repository is selected, diff loading is in progress, the selected repository has no changes, the returned unified diff parses to no files, or the diff request fails; unselected after the diff tree renders; active when this exact row has the `active` class after pointer selection; inactive when any other changed-file row in `#diff-tree` is selected and the prior active class is removed.
- code: groom/groom/templates/dashboard.html::renderDiffTree
- props:
  - source file: required changed-file leaf from the [dashboard diff file tree](../../dashboard-diff-file-tree.md), produced from one parsed diff2html file entry in the [dashboard parsed diff file cache](../../dashboard-parsed-diff-file-cache.md); the row represents exactly one parsed changed file.
  - file path source: required; uses the parsed file's `newName` unless it is `/dev/null`, otherwise uses `oldName`; only the slash-delimited basename is displayed in this row while the parsed file entry remains available for full diff rendering.
  - ordering: required; sibling changed-file rows are sorted by displayed basename with `localeCompare`, after sibling directories are rendered by JavaScript object-key sort order.
  - `class`: literal `tree-file`; required; gains `active` exactly for the currently selected changed-file row in the diff tree.
  - `data-file-idx`: required zero-based integer string; indexes the parsed file entry in `#diff-tree._files` and is converted with unary `+` when the row is selected.
  - `.fname`: required child span containing the escaped displayed basename; this is visible text only, not a programmatic control name.
  - `.fstat`: required child span containing the changed-line summary; wraps `.add` and `.del` spans.
  - `.add`: required child span text in `+{addedLines}` form, where `addedLines` comes from the parsed file entry.
  - `.del`: required child span text in `-{deletedLines}` form, where `deletedLines` comes from the parsed file entry.
- dom: generated `<div class="tree-file" data-file-idx="{idx}"><span class="fname">{basename}</span><span class="fstat"><span class="add">+{addedLines}</span> <span class="del">-{deletedLines}</span></span></div>` inside `#diff-tree`, nested under zero or more generated `.tree-dir > .tree-children` containers after repository selection successfully renders a non-empty parsed diff tree.
- leads-to: [select diff file row](#select-diff-file-row), which renders that cached parsed file entry into `#diff-view` without another network request.

### settings-rescan-button

- selector: `#btn-refresh`
- role: button.
- name: `Rescan containers`.
- keyboard: Tab and Shift+Tab reach the native button when the settings pane is active; Enter or Space activates it when focused.
- parent: [groom dashboard](#groom-dashboard)
- states: settings pane inactive but present in the DOM; idle and activatable when settings mode is active; busy after activation with `data-busy="1"` and `spinning` class on this button; idle again after the refresh request settles whether it fulfilled or rejected.
- code: groom/groom/templates/dashboard.html::doRefresh
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- props:
  - `id`: literal `btn-refresh`; required; selects this settings-pane button in the shared refresh click delegation.
  - `class`: literal `btn`; required visual button styling and the base class that receives transient `spinning` during a request.
  - text content: literal `Rescan containers`; required visible label and accessible name.
  - `type`: absent; the button is not inside a form, so activation has no form submission target and is owned by the dashboard click handler.
  - `data-busy`: absent by default; set to string `1` only while the client-side refresh request is in flight, and used as the duplicate-activation guard.
- dom: native `<button class="btn" id="btn-refresh">Rescan containers</button>` inside one `.row-set` in `#settings-pane .settings-panel`, rendered after the `Settings` heading and before the explanatory text `Re-run the docker discovery pass.`.
- leads-to: [rescan containers from settings](#rescan-containers-from-settings), which posts to [POST /refresh](../../http/groom.md#post-refresh); websocket shell broadcasts deliver the scanning and refreshed fleet states.

### settings-enable-notifications-button

- selector: `#btn-notify`
- role: button.
- name: `Enable notifications`.
- keyboard: Tab and Shift+Tab reach the native button while settings mode is active; Enter or Space activates it when focused.
- parent: [groom dashboard](#groom-dashboard)
- states: absent only if the dashboard shell is not loaded; inactive but present when another activity mode is selected; idle and enabled when settings mode is active; remains enabled with no `disabled`, busy, pressed, granted, denied, or unavailable visual state regardless of the browser's current notification permission.
- code: groom/groom/templates/dashboard.html::btn-notify
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- props:
  - `id`: literal `btn-notify`; required; the delegated dashboard click handler matches this exact event target before requesting browser notification permission.
  - `class`: literal `btn ghost`; required; provides button styling and secondary visual emphasis, with no state semantics.
  - text content: literal `Enable notifications`; required visible label and accessible name.
  - `type`: absent; the button is not inside a form, so activation has no form submission target and is owned by the dashboard click handler.
- dom: native `<button class="btn ghost" id="btn-notify">Enable notifications</button>` inside one `.row-set` in `#settings-pane .settings-panel`, rendered after the [settings rescan button](#settings-rescan-button) row and before the explanatory text `Browser alerts when a worker blocks.`.
- leads-to: [enable browser notifications from settings](#enable-browser-notifications-from-settings), which requests browser notification permission when the Notification API is available; later `groom:blocked` browser events may show system notifications only if the browser reports permission as `granted`.

### statusbar-refresh-button

- selector: `#btn-refresh-bar`
- role: button.
- name: `⟳`, the accessible name computed from the button's own visible text content; live-verified — the `title` attribute value `Rescan containers (reconcile + prune)` is exposed only as the tooltip/description, not the accessible name, because a non-empty text-content child outranks `title` in the browser's accessible-name computation. This is an a11y gap: the icon-only glyph is not a meaningful accessible name.
- keyboard: Tab and Shift+Tab reach the native button in the always-visible status bar; Enter or Space activates it when focused.
- parent: [groom dashboard](#groom-dashboard)
- states: idle and activatable whenever the dashboard shell is loaded; busy after activation with `data-busy="1"` and `spinning` class on this status-bar button only; idle again after the refresh request settles whether it fulfilled or rejected; replaced back to server-rendered idle markup when an out-of-band status bar update arrives.
- code: groom/groom/render.py::render_statusbar
- verify: groom/tests/test_render.py::test_statusbar_has_refresh_button
- props:
  - `id`: literal `btn-refresh-bar`; required; selects this status-bar button in the shared refresh click delegation alongside the settings-pane `#btn-refresh` button.
  - `class`: literal `statusbar-refresh`; required for status-bar refresh styling and the base class that receives transient `spinning` during a request.
  - `title`: literal `Rescan containers (reconcile + prune)`; tooltip text and accessible-description only — live-verified this does not become the accessible name because the button's own non-empty text content (`⟳`) wins.
  - text content: literal `⟳`; required visible icon glyph only, not a descriptive visible label.
  - `type`: absent; the button is not inside a form, so activation has no form submission target and is owned by the dashboard click handler.
  - `data-busy`: absent by default; set to string `1` only while this button's client-side refresh request is in flight, and used as the duplicate-activation guard for this button.
- dom: native `<button id="btn-refresh-bar" class="statusbar-refresh" title="Rescan containers (reconcile + prune)">⟳</button>` inside `#statusbar .status-right`, rendered after the websocket liveness label and before the command-palette hint; the status bar itself is replaced out of band by websocket shell broadcasts.
- leads-to: [rescan containers from statusbar](#rescan-containers-from-statusbar), which posts to [POST /refresh](../../http/groom.md#post-refresh); websocket shell broadcasts deliver the scanning and refreshed fleet states.

### command-palette-shortcut

- selector: `document keydown Ctrl+K or Meta+K`
- role: keyboard shortcut; no focusable ARIA or native control role because the opener is a document-level keydown handler and the visible status-bar hint is static text.
- name: no robust interactive accessible name; the status bar renders visible text `⌘K palette`, but it is not a named button or link and cannot be reached by `getByRole`.
- keyboard: `Ctrl+K` or `Meta+K` toggles the command palette from anywhere in the dashboard, including while focus is in a text input; Escape closes the palette through the same document-level keydown handler.
- parent: [groom dashboard](#groom-dashboard)
- states: palette closed with `#palette` lacking `open`; palette open with `#palette.open`, empty [command palette input](#command-palette-input), refreshed [command palette result](#command-palette-result) rows, and focus moved to `#palette-input`; closed again after the same shortcut, Escape, clicking a result, or pressing Enter with a selectable result.
- code: groom/groom/templates/dashboard.html::openPalette
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- props:
  - shortcut: required platform-neutral chord; `Ctrl+K` for control-key environments and `Meta+K` for command-key environments; checked case-insensitively with `e.key.toLowerCase() === "k"`.
  - trigger scope: required document-wide keydown listener; it runs before Escape, palette Enter, and `j`/`k` inbox-row movement handling.
  - visible hint: optional status-bar text rendered as `⌘K palette`; informative only and not an operable control.
  - opened overlay: required `#palette` element; receives the `open` class when the shortcut opens the palette and loses it when the shortcut closes the palette.
  - input reset: required; opening clears `#palette-input` to the empty string before results are rendered.
  - result source: required current `#inbox-list .row` DOM collection; opening rebuilds palette results from currently rendered inbox rows and does not request fresh data.
- dom: no standalone button or link; the only persistent visual affordance is the non-interactive status-bar hint inside `#statusbar .status-right`, and the overlay itself is `<div id="palette">` containing the [command palette input](#command-palette-input) and [command palette result](#command-palette-result) list.
- leads-to: [toggle command palette shortcut](#toggle-command-palette-shortcut), which opens [command palette input](#command-palette-input) and [command palette result](#command-palette-result) overlay content in this screen; no browser route change occurs.

### command-palette-input

- selector: `#palette-input`
- role: textbox.
- name: `Jump to a worker or blocked gate`.
- keyboard: ordinary single-line text editing filters palette results while focus remains in the input; Enter selects the active or first result through the document-level palette key handler; Escape closes the palette through the document-level key handler.
- parent: [groom dashboard](#groom-dashboard)
- states: hidden but present in the DOM while `#palette` is closed; focused after `Ctrl+K` or `Meta+K` opens the palette; empty query showing all currently rendered inbox rows as results; non-empty query showing only palette results whose normalized row text contains the query case-insensitively; stale results possible when websocket out-of-band swaps replace `#inbox-list` while the palette remains open because results are rebuilt only on open or input events.
- code: groom/groom/templates/dashboard.html
- verify: groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- props:
  - `id`: literal `palette-input`; required; selects the field for palette-open focus, input-event wiring, and the command-palette text value.
  - `type`: literal `text`; required; exposes native single-line textbox behavior rather than the ARIA combobox pattern.
  - `aria-label`: literal `Jump to a worker or blocked gate`; required; supplies the durable accessible name because no visible label is rendered.
  - `placeholder`: literal `Jump to a worker or blocked gate...`; required visual hint only, not the accessible name.
  - value: string; optional browser-local query; default empty whenever the palette is opened because `openPalette` clears it before rebuilding results.
  - result source: currently rendered `#inbox-list .row` elements; required for filtering and result generation, with each source row contributing `data-worker-id`, `data-state`, and normalized visible text.
- dom: native `<input id="palette-input" type="text" aria-label="Jump to a worker or blocked gate" placeholder="Jump to a worker or blocked gate...">` as the first child of `.palette-box`, followed by `#palette-results`; the enclosing `#palette` overlay is a role-less `div` rather than a modal dialog, and the input has no `role="combobox"`, `aria-expanded`, `aria-controls`, or `aria-activedescendant` relationship to the generated result rows.
- leads-to: [filter command palette results](#filter-command-palette-results), which filters rows currently present in `#inbox-list` into [command palette result](#command-palette-result) rows without requesting fresh server data.

### command-palette-result

- selector: `#palette-results .presult`
- role: none; rendered as a clickable `div`, not a semantic option, button, or link.
- name: none as a robust control name; visible text mirrors the normalized inbox row plus a state hint, but the generated row has no interactive role, `aria-label`, `aria-selected`, or focusable name-bearing element.
- keyboard: Enter selects the active or first generated result while the palette is open and focus normally remains on [command palette input](#command-palette-input); individual result rows are not focusable, arrow keys do not move active result state, and direct Enter/Space activation on a row is absent.
- parent: [groom dashboard](#groom-dashboard)
- states: absent while the palette has not been rendered, no inbox rows exist, or the current query filters out every inbox row; normal generated result; active when it is the first result for the current render and therefore carries the `active` class; selected only transiently during pointer click or palette Enter handling before the palette closes.
- code: groom/groom/templates/dashboard.html::renderPalette
- props:
  - source row: required currently rendered [inbox worker row](#inbox-worker-row) from `#inbox-list .row`; each source row contributes exactly one palette result when its normalized text matches the current palette query.
  - source ordering: required DOM order of the current `#inbox-list .row` collection; filtering preserves this order and the first remaining row becomes the active result.
  - `class`: literal `presult`; required; receives `active` only for the first generated result in the current render.
  - `data-id`: required string copied from the source row's `data-worker-id`; becomes the selected worker id passed to the shared row-selection handler; the browser renderer inserts this DOM-derived value into an HTML string without an additional escaping pass.
  - state dot class: required string copied from the source row's `data-state`; appended to the child `.dot` class list for visual state color only; the same value becomes the fallback hint when it is not `blocked`.
  - row body text: required normalized source row `textContent`, with whitespace collapsed and ends trimmed; rendered inside child `.rb` and used as the query-match source.
  - hint text: required; renders `gate` when source state is `blocked`, otherwise renders the source state string.
- dom: generated `<div class="presult" data-id="{worker_id}">` row inside `#palette-results`, with an additional `active` class on the first result; contains `<span class="dot {state}"></span>`, `<span class="rb">{normalized row text}</span>`, and `<span class="hint">{gate_or_state}</span>`; all results are replaced as one `#palette-results.innerHTML` assignment on each palette render.
- leads-to: [select command palette result](#select-command-palette-result), which switches to inbox mode, selects the result's worker, loads worker detail through [GET /worker/{container_id}](../../http/groom.md#get-worker-detail), and closes the palette without changing the browser route.

## Interactions

### select-activity-inbox-mode

- on: [activity-inbox-mode](#activity-inbox-mode)
- trigger: pointer click or tap on `.act-btn[data-mode="inbox"]` or its SVG descendants, captured by the delegated `#activitybar` click handler.
- role: none; the triggering element is a clickable `div`, not a button.
- name: none as a robust control name; the code supplies only `title="Inbox"` on an icon-only `div`.
- keyboard: none for this control; direct Tab focus and Enter/Space activation are absent.
- when:
  - The dashboard shell is loaded and `#activitybar` contains the inbox activity control.
  - The click event target or one of its ancestors matches `.act-btn`.
  - The matched activity control has `data-mode="inbox"`; the prior dashboard mode may be inbox, files, diff, or settings.
- does:
  - Calls `setMode("inbox")` with the mode value read from the activity control's `data-mode` attribute.
  - Sets the root `.app` element's `data-mode` state to `inbox`, making the inbox pane the active dashboard pane and hiding the files, diff, and settings panes according to the screen mode contract.
  - Recomputes the `active` class across every `.act-btn` control by comparing each control's `data-mode` value to `inbox`; the inbox control gains `active`, and the files, diff, and settings controls lose `active` even if inbox was already the current mode.
  - Calls the repository-menu close layer, which unconditionally removes the `open` class from `#repo-menu-wrap`; the operation is idempotent when the menu is already closed.
  - Leaves the repository menu DOM subtree, loaded option rows or loading/empty text, `.repo-menu-box` positioning styles, `#repo-search` value, selected repository browser state, and both repository picker labels unchanged.
  - Skips the files-pane and diff-pane loader branches because the selected mode is neither `files` nor `diff`; cached files tree, file view, diff tree, parsed diff cache, and diff view DOM are left as-is for the next visit to those modes.
  - Leaves the selected worker id, visible inbox rows, selected worker detail, command palette state, status bar, websocket connection, and server workflow state unchanged.
  - Does not perform an HTTP request, websocket send, browser navigation, focus movement, or notification permission prompt.
  - Calls no groom first-party symbol beyond this close layer; the layer bottoms out in browser DOM class-list mutation.
- code: groom/groom/templates/dashboard.html::setMode
- code: groom/groom/templates/dashboard.html::closeRepoMenu

### select-activity-files-mode

- on: [activity-files-mode](#activity-files-mode)
- trigger: pointer click or tap on `.act-btn[data-mode="files"]` or its SVG descendants, captured by the delegated `#activitybar` click handler.
- role: none; the triggering element is a clickable `div`, not a button.
- name: none as a robust control name; the code supplies only `title="Files"` on an icon-only `div`.
- keyboard: none for this control; direct Tab focus and Enter/Space activation are absent.
- when:
  - The dashboard shell is loaded and `#activitybar` contains the files activity control.
  - The click event target or one of its ancestors matches `.act-btn`.
  - The matched activity control has `data-mode="files"`; the prior dashboard mode may be inbox, files, diff, or settings.
  - A selected repository may be absent, or may contain a container id plus an optional repository path in [dashboard selected repository state](../../dashboard-selected-repository-state.md).
- does:
  - Calls `setMode("files")` with the mode value read from the activity control's `data-mode` attribute.
  - Sets the root `.app` element's `data-mode` state to `files`, making the files pane the active dashboard pane and hiding the inbox, diff, and settings panes according to the screen mode contract.
  - Recomputes the `active` class across all `.act-btn` controls so the files control is active and the inbox, diff, and settings controls are inactive.
  - Calls the repository-menu close layer, which removes the `open` class from `#repo-menu-wrap`; selected repository browser state, repository search text, loaded menu rows, menu positioning styles, and both picker labels are retained.
  - Enters the files-pane loader because the selected mode is `files`; this happens even when files mode was already active, so reselecting the Files activity control reloads the files pane.
  - Reads `#files-tree` and `#file-view` as the two mutable Files pane regions.
  - If no selected repository container is present in [dashboard selected repository state](../../dashboard-selected-repository-state.md), replaces `#files-tree` with the empty prompt `Pick a container / repo above.` and returns before changing `#file-view`, issuing a request, or rendering generated file rows.
  - If a selected repository container is present, replaces `#files-tree` with the loading prompt `Loading files…` and resets `#file-view` to `Select a file to view it.` before requesting data, so any prior selected file body and active file row are cleared for the new load.
  - Sends `GET /files/{container_id}?repo={repo}` to [get workspace file list](../../http/groom.md#get-workspace-file-list), URL-encoding the selected container id and selected repository path from browser state; an empty selected repository path is serialized as an empty `repo` query value.
  - Treats any fulfilled fetch response as [workspace file list data](../../workspace-file-list-data.md) by reading the response body as text; HTTP error statuses are not specially branched by this layer.
  - Normalizes the response text into candidate file paths by splitting on newline characters, trimming each line, and discarding empty strings.
  - If no paths remain after normalization, replaces `#files-tree` with `(no files)` and leaves `#file-view` on the empty selection prompt set before the request.
  - If one or more paths remain, calls the [dashboard files path tree builder](../../concepts/dashboard-files-path-tree-builder.md) to group the normalized repo-relative paths into a [dashboard files path tree](../../dashboard-files-path-tree.md) of nested directory nodes and file leaves.
  - For each normalized path passed to the builder, splits the path on `/`, creates or reuses directory nodes for every segment before the final segment, and appends one file leaf containing the final segment as `name` and the original full path as `path`.
  - Calls the files tree renderer with the built path tree to replace `#files-tree` with generated [files directory toggle](#files-directory-toggle) and [files file row](#files-file-row) components; directory names are sorted lexicographically, file leaves are sorted by display name, and rendered directory names, file paths, and file names are HTML-escaped before insertion.
  - If the fetch rejects or response text reading rejects, replaces `#files-tree` with `failed to load` and leaves `#file-view` on the empty selection prompt set before the request.
  - Leaves the selected worker id, visible inbox rows, selected worker detail, command palette state, status bar, websocket connection, and server workflow state unchanged.
  - Does not send a websocket message, perform browser navigation, move focus, or request notification permission.
- code: groom/groom/templates/dashboard.html::setMode
- code: groom/groom/templates/dashboard.html::loadFiles
- code: groom/groom/templates/dashboard.html::buildPathTree
- code: groom/groom/templates/dashboard.html::renderPathTree

### select-activity-diff-mode

- on: [activity-diff-mode](#activity-diff-mode)
- trigger: pointer click or tap on `.act-btn[data-mode="diff"]` or its SVG descendants, captured by the delegated `#activitybar` click handler.
- role: none; the triggering element is a clickable `div`, not a button.
- name: none as a robust control name; the code supplies only `title="Diff"` on an icon-only `div`.
- keyboard: none for this control; direct Tab focus and Enter/Space activation are absent.
- when:
  - The dashboard shell is loaded and `#activitybar` contains the diff activity control.
  - The click event target or one of its ancestors matches `.act-btn`.
  - The matched activity control has `data-mode="diff"`; the prior dashboard mode may be inbox, files, diff, or settings.
  - A selected repository may be absent, or may contain a container id plus an optional repository path in [dashboard selected repository state](../../dashboard-selected-repository-state.md).
  - Reselecting the Diff activity control while already in diff mode is allowed and reloads the Diff pane from the current selected repository state.
- does:
  - Calls `setMode("diff")` with the mode value read from the activity control's `data-mode` attribute.
  - Sets the root `.app` element's `data-mode` state to `diff`, making the diff pane the active dashboard pane and hiding the inbox, files, and settings panes according to the screen mode contract.
  - Recomputes the `active` class across all `.act-btn` controls so the diff control is active and the inbox, files, and settings controls are inactive.
  - Calls the repository-menu close layer, which removes the `open` class from `#repo-menu-wrap`; selected repository browser state, repository search text, loaded menu rows, menu positioning styles, and both picker labels are retained.
  - Enters the Diff pane loader because the selected mode is `diff`; this happens even when diff mode was already active, so reselecting the Diff activity control reloads the Diff pane.
  - Reads `#diff-tree` and `#diff-view` as the two mutable Diff pane regions.
  - If no selected repository container is present in [dashboard selected repository state](../../dashboard-selected-repository-state.md), replaces `#diff-tree` with the empty prompt `Pick a container / repo above.` and returns before changing `#diff-view`, issuing a request, parsing diff text, or rendering generated changed-file rows.
  - If a selected repository container is present, replaces `#diff-tree` with the loading prompt `Loading changes…` and resets `#diff-view` to `Select a changed file to see its diff.` before requesting data, so any prior selected-file diff body and active changed-file row are cleared for the new load.
  - Sends `GET /diff/{container_id}?repo={repo}` to [get workspace diff](../../http/groom.md#get-workspace-diff), URL-encoding the selected container id and selected repository path from browser state; an empty selected repository path is serialized as an empty `repo` query value.
  - Treats any fulfilled fetch response as [workspace diff data](../../workspace-diff-data.md) by reading the response body as text; HTTP error statuses are not specially branched by this layer.
  - If the response text is empty after whitespace trimming, replaces `#diff-tree` with `(no changes)`, leaves `#diff-view` on the empty selection prompt set before the request, and does not create a [dashboard parsed diff file cache](../../dashboard-parsed-diff-file-cache.md).
  - If the response text is non-empty, parses the raw unified diff text with the third-party Diff2Html parser into candidate parsed changed-file entries.
  - If parsing yields no file entries, replaces `#diff-tree` with `(no changes)`, leaves `#diff-view` on the empty selection prompt set before the request, and does not create a parsed diff cache.
  - If parsing yields one or more file entries, stores the parsed file array as [dashboard parsed diff file cache](../../dashboard-parsed-diff-file-cache.md) on `#diff-tree._files`, calls the [dashboard diff file tree builder](../../concepts/dashboard-diff-file-tree-builder.md) to group the entries into a [dashboard diff file tree](../../dashboard-diff-file-tree.md), and replaces `#diff-tree` with generated [diff directory toggle](#diff-directory-toggle) and [diff file row](#diff-file-row) components.
  - For each parsed diff file entry passed to the builder, chooses `newName` unless it is missing or `/dev/null`, otherwise chooses `oldName`; coerces that chosen path to a string; splits it on `/`; creates or reuses directory nodes for every segment before the final segment; and appends one changed-file leaf with the final segment, original parsed-file index, added-line count, and deleted-line count.
  - If the fetch rejects or response text reading rejects, replaces `#diff-tree` with `failed to load` and leaves `#diff-view` on the empty selection prompt set before the request.
  - Leaves the selected worker id, visible inbox rows, selected worker detail, command palette state, status bar, websocket connection, and server workflow state unchanged.
  - Does not send a websocket message, perform browser navigation, move focus, or request notification permission.
- code: groom/groom/templates/dashboard.html::loadDiff
- code: groom/groom/templates/dashboard.html::buildFileTree
- code: groom/groom/templates/dashboard.html::renderDiffTree
- code: groom/groom/templates/dashboard.html::setMode

### select-activity-settings-mode

- on: [activity-settings-mode](#activity-settings-mode)
- trigger: pointer click or tap on `.act-btn[data-mode="settings"]` or its SVG descendants, captured by the delegated `#activitybar` click handler.
- role: none; the triggering element is a clickable `div`, not a button.
- name: none as a robust control name; the code supplies only `title="Settings"` on an icon-only `div`.
- keyboard: none for this control; direct Tab focus and Enter/Space activation are absent.
- when:
  - The dashboard shell is loaded and `#activitybar` contains the settings activity control.
  - The click event target or one of its ancestors matches `.act-btn`.
  - The matched activity control has `data-mode="settings"`; the prior dashboard mode may be inbox, files, diff, or settings.
  - A repository picker overlay may be open or closed, and a selected repository may be absent or already stored in [dashboard selected repository state](../../dashboard-selected-repository-state.md).
  - Reselecting the Settings activity control while already in settings mode is allowed and repeats the mode switch without fetching files, fetching diffs, or resetting settings controls.
- does:
  - Calls `setMode("settings")` with the mode value read from the activity control's `data-mode` attribute.
  - Sets the root `.app` element's `data-mode` state to `settings`, making the settings pane the active dashboard pane and hiding the inbox, files, and diff panes according to the screen mode contract.
  - Recomputes the `active` class across all `.act-btn` controls so the settings control is active and the inbox, files, and diff controls are inactive.
  - Calls the repository-menu close layer, which removes the `open` class from `#repo-menu-wrap`; selected repository browser state, repository search text, loaded menu rows, menu positioning styles, and both picker labels are retained.
  - Skips the files-pane loader and diff-pane loader because the selected mode is neither `files` nor `diff`, so `#files-tree`, `#file-view`, `#diff-tree`, and `#diff-view` keep their current DOM contents.
  - Shows the existing settings pane controls without changing [settings rescan button](#settings-rescan-button) idle or busy state and without invoking [settings enable notifications button](#settings-enable-notifications-button).
  - Leaves the selected worker id, visible inbox rows, selected worker detail, selected repository state, command palette state, status bar, websocket connection, browser URL, and server workflow state unchanged.
  - Does not perform an HTTP request, send a websocket message, perform browser navigation, move focus, mutate an ARIA state, or request notification permission.
- code: groom/groom/templates/dashboard.html::setMode
- code: groom/groom/templates/dashboard.html::closeRepoMenu

### open-files-repository-picker

- on: [files repository picker button](#files-repository-picker-button)
- trigger: pointer click, tap, Enter, or Space activation of `.repo-picker[data-picker="files"]` or one of its child spans, handled by the per-button repository-picker click listener.
- role: button.
- name: `Select container / repo…` before repository selection, then the currently selected workflow/repository label.
- keyboard: Tab or Shift+Tab reaches the native button while the files pane is active; Enter or Space activates the button; Escape closes the repository menu once it is open.
- when:
  - The groom dashboard shell is loaded and the files pane contains the native files repository picker button.
  - The activating event reaches the button-specific repository-picker listener before the document-level body click handler.
  - The shared `#repo-menu-wrap` overlay may be closed or already open; the selected repository browser state may be absent or already set.
  - If the shared repository menu is already open, the activation is treated as a close request regardless of whether the open menu was positioned from the files picker or the diff picker.
- does:
  - Stops propagation of the activating click event so the document-level click handlers do not immediately close the shared repository menu or interpret the click as another dashboard action.
  - If `#repo-menu-wrap` already has the `open` class, closes the repository menu by removing that class and leaves selected repository state, picker labels, files tree, file view, diff tree, and diff view unchanged.
  - If the menu is closed, measures the activated files picker button and positions `.repo-menu-box` at the button's left edge, four pixels below the button, with a minimum width equal to the larger of the button width and 240 pixels.
  - Opens the shared repository menu by adding the `open` class to `#repo-menu-wrap`.
  - Replaces `#repo-menu` with the loading state `Loading…` and clears the [repository menu search input](#repository-menu-search-input) value.
  - Sends `GET /repos` to [get repository menu](../../http/groom.md#get-repository-menu) without a request body, query string, websocket message, or browser navigation.
  - Moves focus immediately to [repository menu search input](#repository-menu-search-input), before the `/repos` response resolves, so typed input during loading stays in the filter field.
  - When the response resolves, consumes the body as text regardless of HTTP status and replaces `#repo-menu` with the returned repository-option HTML derived from [repository menu data](../../repository-menu-data.md).
  - When the resolved response body is empty, represents the empty result client-side as `No repositories available.` instead of inserting an empty menu.
  - If the `/repos` request or response-text read rejects, leaves the menu open with `#repo-menu` still showing `Loading…`; no failure text, retry affordance, or console-visible recovery state is rendered by this handler.
  - Leaves the root activity mode, selected worker id, selected repository value, selected file, selected diff file, inbox rows, selected worker detail, status bar, command palette, websocket connection, and server workflow state unchanged until an option is selected.
  - Does not mark the button expanded with `aria-expanded`, does not give the menu a listbox relationship through `aria-controls`, and does not expose the loading/result change through an `aria-live` region.
- code: groom/groom/templates/dashboard.html::openRepoMenu
- screenshot: .agents/okf-build/walkthrough/groom/operator-browses-workspace-file-repo-menu-open.png

### open-diff-repository-picker

- on: [diff repository picker button](#diff-repository-picker-button)
- trigger: pointer click, tap, Enter, or Space activation of `.repo-picker[data-picker="diff"]` or one of its child spans, handled by the per-button repository-picker click listener.
- role: button.
- name: `Select container / repo…` before repository selection, then the currently selected workflow/repository label.
- keyboard: Tab or Shift+Tab reaches the native button while the diff pane is active; Enter or Space activates the button; Escape closes the repository menu once it is open.
- when:
  - The groom dashboard shell is loaded and the diff pane contains the native diff repository picker button.
  - The activating event reaches the button-specific repository-picker listener before the document-level body click handler.
  - The shared `#repo-menu-wrap` overlay may be closed or already open; the selected repository browser state may be absent or already set.
  - If the shared repository menu is already open, the activation is treated as a close request regardless of whether the open menu was positioned from the files picker or the diff picker.
- does:
  - Stops propagation of the activating click event so the document-level click handlers do not immediately close the shared repository menu or interpret the click as another dashboard action.
  - If `#repo-menu-wrap` already has the `open` class, closes the repository menu by removing that class and leaves selected repository state, picker labels, files tree, file view, diff tree, and diff view unchanged.
  - If the menu is closed, measures the activated diff picker button and positions `.repo-menu-box` at the button's left edge, four pixels below the button, with a minimum width equal to the larger of the button width and 240 pixels.
  - Opens the shared repository menu by adding the `open` class to `#repo-menu-wrap`.
  - Replaces `#repo-menu` with the loading state `Loading…` and clears the [repository menu search input](#repository-menu-search-input) value.
  - Sends `GET /repos` to [get repository menu](../../http/groom.md#get-repository-menu) without a request body, query string, websocket message, or browser navigation.
  - Moves focus immediately to [repository menu search input](#repository-menu-search-input), before the `/repos` response resolves, so typed input during loading stays in the filter field.
  - When the response resolves, consumes the body as text regardless of HTTP status and replaces `#repo-menu` with the returned repository-option HTML derived from [repository menu data](../../repository-menu-data.md).
  - When the resolved response body is empty, represents the empty result client-side as `No repositories available.` instead of inserting an empty menu.
  - If the `/repos` request or response-text read rejects, leaves the menu open with `#repo-menu` still showing `Loading…`; no failure text, retry affordance, or console-visible recovery state is rendered by this handler.
  - Leaves the root activity mode, selected worker id, selected repository value, selected file, selected diff file, inbox rows, selected worker detail, status bar, command palette, websocket connection, and server workflow state unchanged until an option is selected.
  - Does not mark the button expanded with `aria-expanded`, does not give the menu a listbox relationship through `aria-controls`, and does not expose the loading/result change through an `aria-live` region.
- code: groom/groom/templates/dashboard.html::openRepoMenu

### filter-repository-menu-options

- on: [repository menu search input](#repository-menu-search-input)
- trigger: native `input` event after typing, paste, cut, undo, redo, clearing, or any other browser-supported value change in `#repo-search`.
- role: textbox.
- name: `Search container / repo`.
- keyboard: ordinary single-line text editing changes the filter query immediately; Tab and Shift+Tab leave the field through normal browser focus traversal; Escape closes the repository menu through the separate dashboard-level keydown handler and does not clear the query or select an option.
- when:
  - The groom dashboard shell is loaded and the shared repository menu overlay has wired `#repo-search` to the filtering handler.
  - The input event's target is the repository menu search field; the field is normally focused by [open files repository picker](#open-files-repository-picker) or [open diff repository picker](#open-diff-repository-picker).
  - `#repo-menu` may contain loading text, an empty-state row, or zero or more [repository menu option](#repository-menu-option) rows returned by [GET /repos](../../http/groom.md#get-repository-menu).
- does:
  - Reads the current search input value and passes it to `filterRepoMenu` without debouncing, form submission, websocket send, HTTP request, browser navigation, or URL mutation.
  - Lowercases the query for case-insensitive matching.
  - Iterates only the `.repo-item` rows currently present inside `#repo-menu`; loading and empty-state elements are ignored because they do not match `.repo-item`, and rows inserted later by the `/repos` response are outside this pass.
  - For each option row, reads `data-label` as the searchable repository label from the [repository menu data](../../repository-menu-data.md) option-label contract, treats a missing label as an empty string, lowercases it, and checks whether it contains the query substring.
  - Sets each matching row's inline `display` style to the empty string so it remains visible under stylesheet defaults.
  - Sets each non-matching row's inline `display` style to `none`, hiding it visually and from normal pointer selection while leaving the row in the DOM.
  - When the query is empty, clears the inline `display` override on every currently loaded option row so all repository options are visible again.
  - When the query matches no loaded option rows, leaves every option row hidden and does not render a search-specific empty message, count, or recovery affordance.
  - Leaves selected repository state, files tree, diff tree, picker labels, activity mode, command palette state, selected worker detail, status bar, websocket connection, server workflow state, and keyboard focus unchanged.
  - Does not re-run automatically after the asynchronous `/repos` response replaces `#repo-menu`; if the operator typed while the menu was still loading, the newly inserted option rows keep their default visibility until the next input event.
- code: groom/groom/templates/dashboard.html::filterRepoMenu

### select-repository-menu-option

- on: [repository menu option](#repository-menu-option)
- trigger: pointer click or tap on `#repo-menu .repo-item` or any descendant of that row, captured by the delegated `#repo-menu` click listener.
- role: option; explicit `role="option"` on the rendered row, without an owning `listbox` role.
- name: visible text from the optional workflow type badge followed by the repository option label generated from workflow/container name and checkout directory.
- keyboard: none for direct option activation; the option is not focusable and the repository menu has no arrow-key, Enter, or Space selection model.
- when:
  - The groom dashboard shell is loaded and the shared repository menu has been populated by [GET /repos](../../http/groom.md#get-repository-menu).
  - The click event target or one of its ancestors inside `#repo-menu` matches `.repo-item`; clicks on loading or empty-state rows do not match and have no effect.
  - The matched option carries `data-container`, `data-repo`, and `data-label`; `data-repo` may be the empty string for the workflow workspace volume root.
  - The active dashboard mode is normally files or diff because the menu is opened by a repository picker in one of those panes.
- does:
  - Reads the selected workflow container id, volume-relative repository path, and display label from the option's `data-container`, `data-repo`, and `data-label` attributes generated from [repository menu data](../../repository-menu-data.md).
  - Stores the selected repository browser state as [dashboard selected repository state](../../dashboard-selected-repository-state.md), assigning `container` from `data-container`, assigning `label` from `data-label`, and normalizing a missing or empty `data-repo` value to the empty string.
  - Replaces the text content of every `.repo-picker-label` in the dashboard with the selected label, so the files and diff picker buttons show the same selected repository.
  - Calls the [dashboard active pane loader](../../concepts/dashboard-active-pane-loader.md), which reads the root `.app` element's `data-mode` value exactly once and dispatches only for repository-backed panes.
  - If the active mode is files, the active-pane loader calls the Files pane load path: sets `#files-tree` to `Loading files...`, resets `#file-view` to `Select a file to view it.`, sends `GET /files/{container_id}?repo={repo}` to [get workspace file list](../../http/groom.md#get-workspace-file-list), and renders the returned path list as the files tree, `(no files)`, or `failed to load`.
  - If the active mode is diff, the active-pane loader calls the Diff pane load path: sets `#diff-tree` to `Loading changes...`, resets `#diff-view` to `Select a changed file to see its diff.`, sends `GET /diff/{container_id}?repo={repo}` to [get workspace diff](../../http/groom.md#get-workspace-diff), parses the returned unified diff, and renders the changed-file tree, `(no changes)`, or `failed to load`.
  - If the active mode is inbox, settings, missing, or any other value, the active-pane loader returns without calling a pane loader, so only the selected repository state and picker labels change; no files or diff request is sent.
  - Leaves the dashboard activity mode, selected worker id, selected worker detail, inbox rows, status bar, command palette, websocket connection, browser URL, and server workflow state unchanged while dispatching the active-pane load.
  - Closes the shared repository menu by removing the `open` class from `#repo-menu-wrap` after selection.
  - Does not move focus deliberately, expose the changed selected option with `aria-selected`, announce loading or result states through an `aria-live` region, send a websocket message, or navigate away from the dashboard.
- code: groom/groom/templates/dashboard.html::selectRepo

### toggle-files-directory

- on: [files directory toggle](#files-directory-toggle)
- trigger: pointer click or tap on `#files-tree .tree-dir-head` or any descendant of that generated directory header, captured by the delegated `#files-tree` click listener.
- role: none; the triggering element is a clickable `div`, not a semantic disclosure button or treeitem.
- name: none as a robust control name; visible text is the directory basename plus chevron, but the code supplies no role, `aria-label`, or `aria-expanded` state.
- keyboard: none for direct directory toggling; the directory header is not focusable and no Enter, Space, or arrow-key tree navigation is implemented.
- when:
  - The groom dashboard shell is loaded and `#files-tree` has its delegated click listener attached.
  - A repository has been selected and [GET /files/{container_id}](../../http/groom.md#get-workspace-file-list) has returned at least one path containing a directory segment, so `renderPathTree` has generated one or more [files directory toggle](#files-directory-toggle) rows.
  - The click event target or one of its ancestors inside `#files-tree` matches `.tree-dir-head`; clicks on file rows and empty/loading/error states do not satisfy this directory branch.
  - The matched directory header is inside an enclosing `.tree-dir` whose `collapsed` class currently represents that directory's local expanded or collapsed state.
- does:
  - Finds the nearest `.tree-dir-head` for the click target within the files tree.
  - If no directory header matches, leaves the directory-toggle interaction with no collapse or expansion effect and lets the same delegated listener continue to the [files file row](#files-file-row) branch.
  - Toggles the `collapsed` class on that header's parent `.tree-dir`, changing only that directory branch and not any sibling directory or ancestor directory.
  - When `collapsed` is added, the parent `.tree-dir.collapsed > .tree-children` rule hides the direct child subtree with `display: none`, so all nested changed-file rows and nested directories under that directory are visually removed from the diff tree while remaining in the DOM.
  - When `collapsed` is removed, the direct `.tree-children` subtree becomes visible again with its previously generated nested directory and changed-file rows intact; any `collapsed` classes already present on nested descendant directories continue to control their own subtrees.
  - When collapsed, the parent `.tree-dir.collapsed > .tree-dir-head .tchev` rule rotates the visible `▾` chevron `-90deg`; when expanded, the chevron returns to its unrotated downward state.
  - Returns immediately after toggling so the same click is not treated as a [files file row](#files-file-row) activation and does not call the file-opening path.
  - Treats every directory's collapsed state as local DOM state on that directory's own `.tree-dir`; collapsing a parent hides its child subtree visually without changing any nested child directory's existing `collapsed` class.
  - Re-expands a collapsed directory by removing the same class on a later activation of the same generated directory header; the handler does not persist expanded/collapsed state across file-tree reloads.
  - Leaves selected repository state, selected worker id, selected file row styling, `#file-view` contents, inbox rows, selected worker detail, diff tree, diff view, status bar, command palette, websocket connection, browser URL, and server workflow state unchanged.
  - Does not send an HTTP request or websocket message, perform browser navigation, move focus, update `aria-expanded`, or announce the collapse/expand state through an `aria-live` region.
- code: groom/groom/templates/dashboard.html::files-tree click listener

### filter-inbox-messages

- on: [inbox-filter-input](#inbox-filter-input)
- trigger: changed text input after the configured 250 ms debounce, or native search event from the searchbox such as pressing Enter in the field or clearing the field through browser-provided search UI.
- role: searchbox.
- name: `Filter incoming messages`.
- keyboard: text entry edits the query; Enter dispatches the browser search event for `type="search"`; Tab and Shift+Tab use normal document focus traversal.
- when:
  - The groom dashboard shell is loaded in any activity mode; the input remains in the inbox pane and can initiate requests even though the pane is only visible in inbox mode.
  - The input value has changed since the last htmx request, or the browser dispatches a search event for the current value.
  - The request carries the current input value as query parameter `q`; empty string means no text filter.
- does:
  - Sends `GET /search?q={current input value}` to the [search fragment endpoint](../../http/groom.md#get-search-fragment), with `q` serialized from the searchbox's `name` attribute; there is no request body and no browser navigation.
  - The server reads the current in-memory workflow list, keeps only workflows that have at least one open gate, and applies a case-insensitive substring match across workflow identity, repository name, repository branch, workflow type, current node, and gate-file paths when `q` is non-empty.
  - Receives one out-of-band HTML fragment whose root element is the replacement `<div class="inbox-list" id="inbox-list" hx-swap-oob="true">`; because the input uses `hx-swap="none"`, the triggering searchbox, selected worker detail, status bar, activity mode, repository picker, command palette, and browser URL are not directly replaced by the htmx request.
  - Replaces the inbox row list with matching [inbox worker row](#inbox-worker-row) components sorted blocked first, then running, idle, and finished, with names ascending inside each state; each row includes a visual [workflow state dot renderer](../../concepts/workflow-state-dot-renderer.md) fragment whose state class matches the row's `data-state` value.
  - If no rows match, renders the inbox empty state `No incoming messages — inbox zero.`; during discovery this search-triggered empty state remains empty rather than changing to the discovery spinner when `q` is non-empty.
  - After the out-of-band replacement settles, rerenders markdown inside any swapped inbox question previews and uses the [dashboard inbox selection applier](../../concepts/dashboard-inbox-selection-applier.md) to reapply the browser-local selected-worker class to any newly rendered row whose `data-worker-id` still equals the selected worker id.
  - Leaves fleet-wide status counts unchanged because they are not part of the search response.
- code: groom/groom/templates/dashboard.html
- verify: groom/tests/test_render.py::test_search_with_query_shows_empty_not_spinner_even_while_scanning

### select-inbox-worker-row

- on: [inbox-worker-row](#inbox-worker-row)
- trigger: pointer click or tap on an inbox row or any descendant of that row, captured by the delegated `document.body` click handler.
- role: none; the triggering element is a clickable `div`, not a button or list option.
- name: none as a robust control name; selection is keyed by `data-worker-id`, while visible row text is not exposed through a named interactive role or labelled focus target.
- keyboard: none for direct row activation; the row is not focusable and has no Enter/Space activation, while global `j`/`k` movement is handled separately by [keyboard select inbox worker row](#keyboard-select-inbox-worker-row).
- when:
  - The dashboard shell is loaded and the delegated body click listener is registered.
  - The click is outside any form, so clicks inside gate answer forms are left to form controls and the websocket-send form behavior.
  - The click is outside `#repo-menu-wrap`, outside a `.repo-picker`, and outside a `.fd-tree`, so repository menu, repository picker, files tree, and diff tree panel-local click handlers own their regions.
  - The remaining click target or one of its ancestors matches `[data-worker-id]`; for server-rendered inbox rows this is the [workflow container](../../concepts/workflow-container.md) `container_id` emitted as the row's `data-worker-id`.
  - The handler does not require the row to be in `#inbox-list`, does not check that the id is non-empty, and does not check that the id still exists in the server registry before issuing the detail request.
- does:
  - Finds the closest `[data-worker-id]` ancestor for the pointer event target and reads its `dataset.workerId` value exactly as provided by the DOM.
  - Calls the shared `select(id)` handler with that value; the handler stores it as [dashboard selected worker state](../../dashboard-selected-worker-state.md) without trimming, normalizing, existence-checking, or rejecting empty strings.
  - Recomputes selection styling through the [dashboard inbox selection applier](../../concepts/dashboard-inbox-selection-applier.md), which scans every `[data-worker-id]` element currently in the document and toggles the `selected` class true only where the element's `data-worker-id` equals the stored selected worker id.
  - Sends `GET /worker/{encodeURIComponent(id)}` to [get worker detail](../../http/groom.md#get-worker-detail) through htmx with target `#detail` and `innerHTML` swap; the request has no query string, request body, history update, or browser navigation.
  - When the endpoint returns, replaces only the selected worker detail pane with the returned [worker detail renderer](../../concepts/worker-detail-renderer.md) fragment; the inbox row list, status bar, activity mode, selected repository state, repository picker, command palette, toast stack, browser URL, and websocket connection remain unchanged by this interaction.
  - Allows the normal htmx `afterSwap` lifecycle to run after the detail replacement, so dashboard-wide listeners render escaped gate markdown and wire the worker-detail diff disclosure for the newly selected detail fragment.
  - Preserves [dashboard selected worker state](../../dashboard-selected-worker-state.md) for later row clicks, [keyboard select inbox worker row](#keyboard-select-inbox-worker-row), [select command palette result](#select-command-palette-result), and the `groom:answered` browser event refresh path.
  - Returns from the body click handler after selecting the row, so the same click does not trigger status-bar refresh, settings notification permission, repository menu behavior, files/diff tree selection, answer submission, or any other body-click branch.
  - Does not move focus, expose selection with `aria-selected`, send a websocket message, submit an answer form, answer a gate, compute a diff, mutate server state, refilter the inbox, change the active dashboard mode, or change the browser URL.
- code: groom/groom/templates/dashboard.html::select

### keyboard-select-inbox-worker-row

- on: [inbox-worker-row](#inbox-worker-row)
- trigger: document-level keydown for `j` or `k` after command-palette shortcuts, Escape handling, and palette Enter handling have had priority.
- role: keyboard shortcut.
- name: inbox row movement.
- keyboard: `j` selects the next inbox row; `k` selects the previous inbox row; when no rendered row matches the current selected worker, either key selects the first rendered inbox row; the shortcut is disabled while an `INPUT` or `TEXTAREA` has focus.
- when:
  - The dashboard shell is loaded and the keydown was not consumed by the earlier Ctrl/Meta+K palette toggle, Escape close-all branch, or open-palette Enter selection branch.
  - The active element's tag name is not `INPUT` or `TEXTAREA`, so text entry in the inbox searchbox, repository search field, command palette input, and gate answer textarea is not intercepted; other focus targets, including body and non-input controls, remain eligible for `j`/`k` movement.
  - `#inbox-list` contains at least one `.row`; if it contains none, the keydown has no row-selection effect.
- does:
  - Reads the current ordered list of rendered inbox rows from `#inbox-list .row`; this order is the server-rendered inbox order: blocked first, then running, idle, and finished, with workflow names ascending inside each state.
  - Finds the row whose `data-worker-id` equals the browser-local selected worker id; if none is found, clamps movement to the first row.
  - Chooses the next row for `j` or previous row for `k`, clamped so movement at the first or last row stays on the boundary row.
  - If there is no rendered row to choose after clamping, leaves activity mode, selected worker id, selected-row classes, worker detail, repository picker, command palette, browser URL, websocket connection, and server workflow state unchanged and sends no request.
  - Calls `setMode("inbox")`, making the inbox pane active, marking the inbox activity control active, closing the repository picker overlay if open, and leaving files/diff data cached in browser state.
  - Calls the shared row selection handler with the chosen row's `data-worker-id`, which writes [dashboard selected worker state](../../dashboard-selected-worker-state.md), updates selected-row classes through the [dashboard inbox selection applier](../../concepts/dashboard-inbox-selection-applier.md), and sends `GET /worker/{container_id}` to [get worker detail](../../http/groom.md#get-worker-detail) for the `#detail` pane.
  - When an `INPUT` or `TEXTAREA` has focus, skips the row-navigation branch entirely: no inbox rows are queried, the active mode is not changed, selected-row classes are not recomputed, `#detail` is not fetched, and the key remains available to the focused text-entry control.
  - Does not prevent the key event's default browser handling, stop event propagation, move DOM focus to the row, send a websocket message, submit an answer form, mutate server state, or change the browser URL.
- code: groom/groom/templates/dashboard.html::keydown

### toggle-command-palette-shortcut

- on: [command palette shortcut](#command-palette-shortcut)
- trigger: document-level keydown for `Ctrl+K` or `Meta+K`, checked before Escape, palette Enter, and inbox-row `j`/`k` keyboard handling.
- role: keyboard shortcut.
- name: no robust interactive accessible name; the only visible affordance is the static status-bar hint `⌘K palette`.
- keyboard: `Ctrl+K` or `Meta+K` opens the command palette when closed and closes it when open; Escape closes the palette without toggling it.
- when: dashboard shell has the document keydown listener and the event is `Ctrl+K` or `Meta+K`.
  - The groom dashboard shell is loaded and the document-level keydown listener is registered.
  - The key event has either `metaKey` or `ctrlKey` set and its key value lowercases to `k`.
  - The event may originate while focus is inside a text input or textarea; this shortcut branch runs before the later text-entry guard used for `j`/`k` row movement.
  - `#palette`, `#palette-input`, `#palette-results`, and the current `#inbox-list` DOM may be present with zero or more rendered inbox rows.
- does: toggles `#palette.open`; opening clears and rebuilds results from current inbox rows, then focuses `#palette-input`.
  - Prevents the browser's default handling for the `Ctrl+K` or `Meta+K` key event.
  - If `#palette` already has the `open` class, removes that class and leaves the palette input value, rendered results, selected worker id, selected worker detail, activity mode, repository picker, status bar, websocket connection, browser URL, and server workflow state unchanged.
  - If `#palette` is closed, adds the `open` class to `#palette`, making the command palette overlay visible.
  - Clears `#palette-input` to the empty string.
  - Rebuilds `#palette-results` from the currently rendered `#inbox-list .row` elements by normalizing each row's text, copying its `data-worker-id` into result `data-id`, copying its `data-state` into the result state dot and hint, filtering with the empty query, and marking the first rendered result `active`.
  - Moves DOM focus to [command palette input](#command-palette-input) after opening; closing by the same shortcut does not restore focus to a prior trigger because there is no focusable trigger element.
  - Returns from the keydown handler immediately after toggling, so Escape handling, palette Enter selection, and `j`/`k` inbox-row navigation do not also run for the same key event.
  - Does not send an HTTP request, send a websocket message, mutate server state, change the selected worker id, change dashboard mode, close the repository menu, request notification permission, or navigate away from the dashboard.
  - Does not expose the palette as an ARIA modal dialog, trap focus inside it, or provide a focusable non-shortcut opener; these are accessibility gaps in the shipped behavior.
- code: groom/groom/templates/dashboard.html::keydown

### edit-detail-answer-textarea
- on: [detail-answer-textarea](#detail-answer-textarea)
- trigger: keyboard text entry, paste, cut, undo, redo, or other browser-supported editing action while focus is inside `#detail textarea[name="answer"]`; the value is sent only when the enclosing answer form is submitted.
- role: textbox.
- name: `Your answer…`, computed from the `placeholder` attribute per [detail-answer-textarea](#detail-answer-textarea); reachable as `getByRole("textbox", { name: "Your answer…" })`, though it is a placeholder-derived fallback rather than a durable explicit label.
- keyboard: ordinary multiline textbox editing; Enter inserts a newline; Tab leaves the textarea according to normal browser focus traversal; global `j`/`k` inbox navigation is disabled while the textarea has focus.
- when:
  - The dashboard shell is loaded and connected to the browser websocket at [WS /ws](../../http/groom.md#websocket-dashboard).
  - A worker is selected and `GET /worker/{container_id}` has rendered a detail pane containing at least one open gate block.
  - The gate block's answer form contains hidden `cmd=answer`, hidden `workflow_id`, hidden `file_path`, this textarea's `answer` value field, and a submit button.
  - No first-party `input`, `change`, or `keydown` handler owns the textarea's editing path; the only relevant dashboard keydown branch treats a focused `TEXTAREA` as text entry and skips inbox-row `j`/`k` selection.
  - Focus is inside the textarea; if the selected worker is changed or the same selected worker is refetched, the textarea is replaced and any unsent browser-local value is lost.
- does:
  - Lets the browser's native multiline textbox model own caret position, selection, undo/redo history, paste/cut behavior, and the current form-control value.
  - Updates only the textarea's browser-local `answer` form value; groom does not send a websocket frame, issue an HTTP request, or mutate server state on ordinary text input.
  - Keeps the selected worker id, inbox rows, status bar, activity mode, repository picker, command palette, browser URL, and server workflow state unchanged while text is being edited.
  - Leaves document-level `j` and `k` row-selection shortcuts inactive because the dashboard keydown handler treats `TEXTAREA` focus as text entry.
  - Preserves the edited value across websocket out-of-band inbox/status broadcasts because those live swaps do not replace `#detail`; preserves it across command-palette, repository-picker, and activity-mode changes that leave the selected detail pane in place.
  - Loses the edited value when `#detail` is replaced by selecting another worker, by refetching the selected worker detail, or by the successful-answer refresh path after the answered worker is still selected.
  - On enclosing form submission, the htmx websocket extension serializes hidden `cmd=answer`, hidden `workflow_id`, hidden `file_path`, and this textarea's current `answer` value into one [dashboard websocket answer frame](../../dashboard-websocket-answer-frame.md) for [WS /ws](../../http/groom.md#websocket-dashboard); the textarea value is not trimmed by the client before serialization.
  - The first first-party server layer reached by that submitted message is `groom/groom/app.py::_handle_command`, which ignores non-`answer` commands, string-normalizes the submitted `workflow_id`, `file_path`, and `answer`, looks up the selected workflow's workspace volume when the workflow is known, and delegates the gate write to the gate-answering layer.
  - The gate-answering layer serializes concurrent submissions with a lock keyed by the submitted workflow id and gate file path, rereads the gate file from the workflow workspace volume, rejects the answer if the file is missing or no longer has `STATUS: AWAITING_OPERATOR`, writes `STATUS: ANSWERED` plus the stripped answer text when accepted, clears the matching in-memory gate, and starts the workflow container only when it is not already running.
  - The server-side gate-answering call returns an [answer result](../../answer-result.md); every attempted answer builds an [answer log entry](../../answer-log-entry.md) with event `answer`, the normalized container id, gate file path, result success flag, and result message.
  - The answer command then calls [record answer log entry](../../concepts/answer-event-log.md#method-record-answer-log-entry), which appends that dictionary exactly once to the bounded process-local [answer event log](../../concepts/answer-event-log.md), retains only the newest 200 events, emits no return value or client-facing acknowledgement, and calls no deeper first-party groom layer.
  - A successful server-side answer broadcast calls the [groom answered browser event detail](../../groom-answered-browser-event-detail.md) renderer with the normalized workflow id and gate file path, then appends the returned `groom:answered` script after the out-of-band shell fragment.
  - The answered-event renderer serializes exactly `{id: container_id, file_path}` as `CustomEvent.detail`, embeds it in an inline `<script>` dispatching `groom:answered` on `document.body`, and excludes the answer text, gate question, success flag, answer log entry, worker detail HTML, and websocket frame envelope.
  - The answered-event renderer performs only string production and standard-library JSON serialization; it mutates no workflow state, gate files, browser DOM, websocket queues, answer logs, sidecar state, or Docker state and calls no deeper first-party groom layer.
  - When the browser executes the successful answer script, the dashboard shows the success toast `answer sent` and, only when the answered worker is still selected, refetches that worker detail so the answered gate block is dismissed without clobbering another worker's half-typed answer.
  - A failed server-side answer still broadcasts refreshed shell data but does not dispatch `groom:answered`, does not refetch selected detail through the success handler, and leaves the gate visible until a later state change.
- code: groom/groom/render.py::_answer_form
- code: groom/groom/templates/dashboard.html::keydown
- code: groom/groom/app.py::_handle_command
- verify: groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch

### toggle-detail-working-tree-diff

- on: [detail working tree diff toggle](#detail-working-tree-diff-toggle)
- trigger: native `<details>` `toggle` event after pointer, tap, Enter, or Space activation changes the open state of the selected worker's `Working-tree diff` disclosure.
- role: disclosure button; native `<summary>` control for a `<details>` disclosure.
- name: `Working-tree diff`.
- keyboard: Tab and Shift+Tab reach the summary in document order; Enter or Space toggles it; no custom shortcut is registered.
- when:
  - The dashboard shell is loaded and a selected worker detail fragment has been swapped into `#detail`.
  - `wireDetail()` runs after htmx swaps, scans the current `#detail details[data-diff]` disclosures, marks each previously unwired disclosure with `data-wired="1"`, and attaches exactly one toggle listener to that disclosure.
  - The disclosure belongs to a worker with at least one open gate; workers without gates do not render the working-tree diff disclosure.
  - The toggle event fires on `#detail details[data-diff]`; closing the disclosure is allowed at any time and never fetches data.
  - The disclosure body contains `[data-diff-target]` with `data-container` set to the selected worker container id.
- does:
  - Ignores any already-wired disclosure on later htmx swaps or detail refreshes, so an existing disclosure never accumulates duplicate toggle listeners; a replaced detail fragment receives fresh wiring because it is a new DOM node.
  - If the disclosure is closing, returns immediately after the browser updates the native collapsed state; loaded diff content, empty-state content, or failure text remains in the disclosure body for a later expansion.
  - If the disclosure is opening and the target already has `data-loaded`, returns without another HTTP request so repeated expansions reuse the existing rendered diff body.
  - If the disclosure is opening for the first time, sets the target text to `Loading diff…` while the request is in flight.
  - Sends `GET /diff/{container_id}` to [get workspace diff](../../http/groom.md#get-workspace-diff), where `container_id` is URL-encoded from the target's `data-container`; the detail disclosure does not include a `repo` query parameter, so the endpoint uses its default repository selection.
  - Receives the response as plain text from [serve workspace diff](../../http/groom.md#serve-workspace-diff); the server may return raw unified diff text or an empty body, and endpoint-level unavailable-data cases still resolve as `200 OK` empty text.
  - Treats any fulfilled HTTP response as renderable text without checking `response.ok`; framework-level non-OK responses are still read, marked loaded, and rendered or reduced to the empty-state branch according to their text body.
  - On a fulfilled response, sets `data-loaded="1"` on the target before rendering the result, so any successful HTTP response is cached for future expansions even when rendering produces an empty-state body.
  - When the fulfilled response has non-whitespace text after trimming, parses the raw unified diff text through the third-party Diff2Html renderer with file-list drawing enabled, line-matching mode, line-by-line output, and dark color scheme, then replaces the disclosure body with the generated diff HTML.
  - When the fulfilled response is empty or whitespace-only after trimming, replaces the target contents with `<div class="detail-empty">(no changes)</div>`.
  - On a network failure or response-body read rejection, replaces the target text with `failed to load diff` and does not set `data-loaded`, so a later expansion can retry the request.
  - Leaves the selected worker id, gate answer form values, inbox rows, status bar, activity mode, repository picker, command palette, websocket connection, browser URL, and server workflow state unchanged.
  - Does not move focus deliberately, announce the loading/result state through an `aria-live` region, submit websocket messages, render server-provided HTML directly, or broadcast dashboard updates.
- code: groom/groom/templates/dashboard.html::wireDetail

### send-detail-answer

- on: [detail send answer button](#detail-send-answer-button)
- trigger: pointer click, tap, Enter, or Space activation of the native `Send answer` submit button in a gate answer form; equivalent browser form submission from the same form reaches the same websocket-send path.
- role: button.
- name: `Send answer`.
- keyboard: Tab or Shift+Tab reaches the button; Enter or Space activates it when focused; Enter inside the multiline answer textarea inserts a newline and does not serve as the primary submit shortcut.
- when:
  - The dashboard shell is loaded and connected to [WS /ws](../../http/groom.md#websocket-dashboard).
  - A worker is selected and `GET /worker/{container_id}` has rendered `#detail` with at least one open gate block.
  - The activated button belongs to a `<form class="answer" ws-send>` containing hidden `cmd=answer`, hidden `workflow_id`, hidden `file_path`, and textarea `answer` fields.
  - The submitted `workflow_id` is the selected worker container id rendered into the hidden field, and the submitted `file_path` is the exact open gate context-file path rendered for that gate block; this pair scopes the answer when a worker has multiple open gates.
  - The submitted `answer` may be empty or whitespace-only; the client does not trim it, require non-blank text, disable the submit button, or block duplicate submissions while a prior answer is in flight.
  - The websocket receive loop must deliver a decoded JSON object to `groom/groom/app.py::_handle_command`; command frames whose `cmd` is missing or not exactly `"answer"` are outside this interaction's handled path and are ignored by that handler.
- does:
  - Submits the enclosing answer form through the htmx websocket extension without changing the browser URL or issuing an HTTP form request.
  - Serializes one JSON websocket frame containing `cmd: "answer"`, `workflow_id` from the selected workflow container id, `file_path` from the selected gate file, and `answer` from the textarea's current browser-local value.
  - Sends the frame over the existing dashboard websocket to [WS /ws](../../http/groom.md#websocket-dashboard); the dashboard websocket receive loop waits for `groom/groom/app.py::_handle_command` to finish before it receives another frame from the same browser tab.
  - `_handle_command` ignores any frame whose `cmd` is not exactly `"answer"`; for an answer command it converts missing or supplied `workflow_id`, `file_path`, and `answer` values with `str(...)`, defaulting each missing value to the empty string.
  - `_handle_command` looks up the normalized `workflow_id` in the process-local workflow registry; when the workflow is unknown it passes an empty workspace volume to the gate-answering layer, and when the workflow is known it passes that workflow's current workspace volume.
  - Calls the [gate-answering layer](../../concepts/gate-answering-layer.md) with `container_id`, `file_path`, `answer`, and `workspace_volume`; that layer rejects an unknown workspace volume before locking, serializes same-gate submissions with the per-gate lock, rereads the gate file under the lock, accepts only current `STATUS: AWAITING_OPERATOR`, writes `STATUS: ANSWERED` plus the stripped non-blank answer text, clears the matching in-memory gate after a successful write, and attempts the stopped-container restart fallback only after a successful write.
  - Receives an [answer result](../../answer-result.md) from the gate-answering layer for expected domain outcomes, including duplicate or stale gate, missing gate file, missing workspace volume, failed write, successful write while running, successful write with restart, and successful write with restart failure.
  - Builds one [answer log entry](../../answer-log-entry.md) with event `answer`, normalized container id, gate file path, result `ok` flag, and result message; the submitted answer text and gate question are not copied into the log entry.
  - Calls [record answer log entry](../../concepts/answer-event-log.md#method-record-answer-log-entry) to append that dictionary exactly once to the bounded process-local [answer event log](../../concepts/answer-event-log.md), retaining only the newest 200 events and producing no response frame, UI fragment, acknowledgement, or additional first-party service call.
  - If the answer result is successful, the workflow still exists, the gate clear leaves it with no remaining open gates, and its visible state is still blocked, changes that workflow's visible state to running before rendering the broadcast.
  - Renders a fresh [dashboard shell fragment](../../dashboard-shell-fragment.md) after every expected answer result and broadcasts it through the dashboard client queues, so connected dashboard tabs receive out-of-band inbox and status-bar updates; selected worker detail, repository picker, files pane, diff pane, command palette, and browser URL are not part of this shell fragment.
  - Sends no direct acknowledgement frame carrying the answer result; clients infer success only from the success-only script fragment and otherwise only observe the refreshed shell regions.
  - On success only, appends a [groom answered script fragment](../../groom-answered-script-fragment.md) to the same websocket broadcast after the shell fragment; executing that script dispatches `groom:answered` with the answered workflow id and gate file path, shows the success toast `✓ answer sent`, and refetches the selected worker detail only in tabs where the answered workflow is still the selected worker.
  - On expected failure, broadcasts shell data without `groom:answered`, leaves the visible gate and selected detail pane unchanged until a later state change or manual refetch, does not show the success toast, and does not invoke the selected-detail refetch handler.
  - If the gate-answering call, log append, shell rendering, or broadcast queueing raises an unexpected exception instead of returning an answer result, the handler does not convert it to a failure result or acknowledgement frame; the exception propagates through the websocket receive loop and any already-completed side effects are not rolled back.
  - Does not move focus deliberately, clear the textarea before the server response, change the selected worker id, alter repository picker or command palette state, request notification permission, or navigate away from the dashboard.
- code: groom/groom/app.py::_handle_command
- verify: groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch

### select-files-file-row

- on: [files file row](#files-file-row)
- trigger: pointer click or tap on `#files-tree .tree-file` or any descendant of that generated file row, captured by the delegated `#files-tree` click listener after the directory-toggle branch is skipped.
- role: none; the triggering element is a clickable `div`, not a button, link, or treeitem.
- name: none as a robust control name; selection is keyed by `data-path`, while visible basename text is not exposed through a named interactive role.
- keyboard: none for direct file activation; the file row is not focusable and no Enter, Space, or arrow-key file-tree selection model is implemented.
- when:
  - The groom dashboard shell is loaded and `#files-tree` has its delegated click listener attached.
  - A repository has been selected through [repository menu option](#repository-menu-option), so browser state contains a selected workflow container id and volume-relative repository path.
  - [GET /files/{container_id}](../../http/groom.md#get-workspace-file-list) has returned at least one file path, and `renderPathTree` has generated a [files file row](#files-file-row) with `data-path` for the selected file.
  - The click target does not match `.tree-dir-head`; directory-toggle clicks return before the file-row branch.
  - The matched file row's `data-path` is non-empty; an empty path still reaches the endpoint but is represented as empty content by the server.
- does:
  - Finds the nearest `.tree-file` for the click target within the files tree and returns with no effect when none is found.
  - Removes the `active` class from every currently active file row in `#files-tree` before the file-content request starts.
  - Adds the `active` class to the clicked file row immediately, making it the single visibly selected file in the current files tree before the loading state or response body appears.
  - Keeps that active-row state purely visual: it is not mirrored to `aria-selected`, focus, browser URL state, server state, or the selected repository object; it is cleared only by selecting another file row in the same rendered tree or by replacing the files tree after another repository/file-list load.
  - Reads the repo-relative file path from the row's `data-path` attribute and passes it to the file-opening handler.
  - Reads the selected workflow container id and selected volume-relative repository path from [dashboard selected repository state](../../dashboard-selected-repository-state.md); the handler assumes a prior repository selection has populated `container` and normalizes only through URL encoding.
  - Replaces `#file-view` with the loading state `Loading...` while the file-content request is in flight.
  - Sends `GET /file/{container_id}?repo={repo}&path={path}` to [get workspace file content](../../http/groom.md#get-workspace-file-content), URL-encoding the selected container id, selected repository path, and selected file path from browser state.
  - Treats any fulfilled HTTP response as [workspace file content data](../../workspace-file-content-data.md) by reading the response body as raw text regardless of status; the server may return file text or an empty body for empty, binary, missing, unsafe, or unavailable content.
  - Delegates the fulfilled body and the original selected path to the [dashboard file view renderer](../../concepts/dashboard-file-view-renderer.md), which replaces `#file-view` with a `.file-head` containing the escaped full file path and a `.file-body` containing either `(empty or binary file)` or a `<pre class="file-pre hljs"><code>...</code></pre>` block.
  - If the fulfilled body is falsey, renders the `(empty or binary file)` state and returns without creating a code block, resolving a language, or invoking Highlight.js.
  - If the fulfilled body is truthy, creates a fresh code block, assigns file content through `textContent`, wraps it in `.file-pre.hljs`, and appends it after the file header.
  - Chooses a Highlight.js language from the file path extension when a mapping exists and Highlight.js recognizes it; otherwise the code block remains unclassified for plain rendering or library auto-detection.
  - Attempts Highlight.js rendering inside a guarded block; any highlighter exception is swallowed and the plain text code block remains visible.
  - Escapes the inserted path before placing it in the header HTML, and inserts file content as text rather than HTML.
  - Has no request cancellation or selected-path freshness guard; if multiple file rows are selected quickly, each response or rejection may replace `#file-view` when it settles, so the last-settling request wins even if another row has become active meanwhile.
  - On network failure or response-body read rejection, replaces `#file-view` with the `failed to load` empty-state text and does not alter whichever row is currently visually active.
  - Leaves selected repository state, files tree contents, selected worker id, inbox rows, selected worker detail, diff tree, diff view, status bar, command palette, websocket connection, browser URL, and server workflow state unchanged.
  - Does not move focus, announce loading/result state through an `aria-live` region, send a websocket message, submit a form, mutate server state, or navigate away from the dashboard.
- code: groom/groom/templates/dashboard.html::openFile
- code: groom/groom/templates/dashboard.html::renderFile
- screenshot: .agents/okf-build/walkthrough/groom/operator-browses-workspace-file-file-loaded.png

### toggle-diff-directory

- on: [diff directory toggle](#diff-directory-toggle)
- trigger: pointer click or tap on `#diff-tree .tree-dir-head` or any descendant of that generated directory header, captured by the delegated `#diff-tree` click listener before the same listener considers [diff file row](#diff-file-row) activation.
- role: none; the triggering element is a clickable `div`, not a semantic disclosure button or treeitem.
- name: none as a robust control name; visible text is the directory basename plus chevron, but the code supplies no role, `aria-label`, or `aria-expanded` state.
- keyboard: none for direct directory toggling; the directory header is not focusable and no Enter, Space, or arrow-key tree navigation is implemented.
- when:
  - The groom dashboard shell is loaded and `#diff-tree` has its delegated click listener attached.
  - A repository has been selected through [repository menu option](#repository-menu-option), so browser state contains a selected workflow container id and volume-relative repository path.
  - [GET /diff/{container_id}](../../http/groom.md#get-workspace-diff) has returned non-empty unified diff text, Diff2Html has parsed at least one changed file, and `renderDiffTree` has generated one or more [diff directory toggle](#diff-directory-toggle) rows from changed-file paths with directory segments.
  - The click event target or one of its ancestors inside `#diff-tree` matches `.tree-dir-head`; clicks on changed-file rows and empty/loading/error states do not satisfy this directory branch.
  - The matched directory header is inside an enclosing `.tree-dir` whose `collapsed` class currently represents that directory's local expanded or collapsed state.
- does:
  - Receives every pointer click that bubbles to `#diff-tree`, including clicks on directory headers, changed-file rows, and empty/loading/error-state content.
  - Finds the nearest `.tree-dir-head` for the original click target; because the listener is attached to `#diff-tree`, a match represents a generated diff-tree directory header or one of its descendants.
  - When no `.tree-dir-head` is found, skips this interaction and lets the same listener continue to [select diff file row](#select-diff-file-row) or return with no effect for non-row content.
  - Toggles the `collapsed` class on that header's parent `.tree-dir`, changing only the visibility state of that directory's `.tree-children` subtree.
  - Returns immediately after toggling so the same click is not treated as a [diff file row](#diff-file-row) activation and does not render a changed-file diff.
  - Leaves [dashboard selected repository state](../../dashboard-selected-repository-state.md), [workspace diff data](../../workspace-diff-data.md) already parsed and cached on `#diff-tree`, current changed-file active styling, `#diff-view` contents, selected worker id, inbox rows, selected worker detail, files tree, file view, status bar, command palette, websocket connection, browser URL, and server workflow state unchanged.
  - Does not send an HTTP request or websocket message, perform browser navigation, move focus, update `aria-expanded`, or announce the collapse/expand state through an `aria-live` region.
- code: groom/groom/templates/dashboard.html::diff-tree click listener

### select-diff-file-row

- on: [diff file row](#diff-file-row)
- trigger: pointer click or tap on `#diff-tree .tree-file` or any descendant of that generated changed-file row, captured by the delegated `#diff-tree` click listener after the directory-toggle branch is skipped.
- role: none; the triggering element is a clickable `div`, not a button, link, or treeitem.
- name: none as a robust control name; selection is keyed by `data-file-idx`, while visible basename and line-count text are not exposed through a named interactive role.
- keyboard: none for direct changed-file activation; the file row is not focusable and no Enter, Space, or arrow-key diff-tree selection model is implemented.
- when:
  - The groom dashboard shell is loaded and `#diff-tree` has its delegated click listener attached.
  - A repository has been selected through [repository menu option](#repository-menu-option), so browser state contains a selected workflow container id and volume-relative repository path.
  - [GET /diff/{container_id}](../../http/groom.md#get-workspace-diff) has returned non-empty unified diff text, Diff2Html has parsed at least one changed file, and `#diff-tree._files` holds the [dashboard parsed diff file cache](../../dashboard-parsed-diff-file-cache.md).
  - `renderDiffTree` has generated a [diff file row](#diff-file-row) whose `data-file-idx` points to one entry in `#diff-tree._files`.
  - The click target does not match `.tree-dir-head`; directory-toggle clicks return before the changed-file-row branch.
- does:
  - Finds the nearest `.tree-file` for the click target within the diff tree and returns with no effect when none is found.
  - Removes the `active` class from every currently active changed-file row in `#diff-tree`.
  - Adds the `active` class to the clicked changed-file row, making it the single visibly selected changed file in the current diff tree.
  - Keeps that active-row state purely visual: it is not mirrored to `aria-selected`, focus, browser URL state, server state, selected repository state, or the parsed diff cache; it is cleared only by selecting another changed-file row in the same rendered tree or by replacing the diff tree after another diff-pane load.
  - Reads the parsed-file array index from the row's `data-file-idx` attribute, converts it to a number, and selects that file entry from `#diff-tree._files`.
  - Performs no index, cache-presence, stale-selection, or bounds validation after reading `data-file-idx`; correctness depends on the generated row and current `#diff-tree._files` cache coming from the same successful diff-pane load.
  - Replaces `#diff-view` with diff2html output for a one-file array containing the selected parsed file entry.
  - Renders the selected file diff with `drawFileList: false`, `matching: "lines"`, `outputFormat: "line-by-line"`, and `colorScheme: "dark"`, so the right pane shows only the selected file's line-by-line dark diff rather than the full changed-file list.
  - Uses the parsed diff file already cached on `#diff-tree`; does not send another HTTP request, reparse the raw unified diff text, rebuild the file tree, or read selected repository state after the changed-file tree has loaded.
  - Overwrites the previous `#diff-view` contents synchronously with the third-party renderer output and shows no intermediate loading, empty, stale, or error state for this per-file render.
  - If malformed DOM or stale cache state makes the selected cache entry unavailable, the handler has no recovery branch after marking the row active; any renderer exception bubbles through the event handler and the previous or partial `#diff-view` state is not intentionally restored.
  - Leaves selected repository state, diff tree contents, other directory collapsed states, selected worker id, inbox rows, selected worker detail, files tree, file view, status bar, command palette, websocket connection, browser URL, and server workflow state unchanged.
  - Does not move focus, announce loading/result state through an `aria-live` region, send a websocket message, submit a form, mutate server state, or navigate away from the dashboard.
- code: groom/groom/templates/dashboard.html::diff-tree click listener

### rescan-containers-from-settings

- on: [settings rescan button](#settings-rescan-button)
- trigger: pointer click, tap, Enter, or Space activation of the native `#btn-refresh` button in the settings pane, captured by the delegated `document.body` click handler.
- role: button.
- name: `Rescan containers`.
- keyboard: Tab or Shift+Tab reaches the button while settings mode is active; Enter or Space activates it when focused; there is no additional shortcut for rescan.
- when:
  - The groom dashboard shell is loaded and the settings pane contains the native [settings rescan button](#settings-rescan-button).
  - The click event target or one of its ancestors matches `#btn-refresh` and is not inside an answer form, repository menu, repository picker, or files/diff tree region that the body handler excludes first.
  - The matched button may be idle or may already carry `data-busy`; repeat activations while that button's refresh request is in flight are accepted by the event handler but ignored by the refresh layer before another request is sent.
- does:
  - Calls `doRefresh` with the matched settings rescan button.
  - If that button already has `data-busy`, returns without changing DOM state, sending another request, cancelling the in-flight request, or affecting any other refresh control.
  - Sets `data-busy="1"` on the button and adds its `spinning` class, making the in-flight state local to this control.
  - Starts one browser fetch to [post refresh](../../http/groom.md#post-refresh) using method `POST`, with no query string, no handler-required headers, and no request body; the handler stores the returned promise only to attach its `finally` cleanup and does not return or await it for any later dashboard code.
  - Relies on the refresh endpoint to set the [dashboard discovery scanning flag](../../concepts/dashboard-discovery-scanning-flag.md) true, render [dashboard shell fragment](../../dashboard-shell-fragment.md) with out-of-band swap markers, and broadcast that shell over [WS /ws](../../http/groom.md#websocket-dashboard) before Docker reconciliation starts.
  - Causes every connected dashboard websocket client, including the tab that clicked this settings button when its websocket is connected, to receive the pre-scan shell broadcast as out-of-band replacements for `#inbox-list` and `#statusbar`; when the inbox list is otherwise empty and unfiltered, the scanning flag makes `#inbox-list` show the `Discovering containers...` loading state rather than the empty inbox message.
  - Lets the refresh endpoint run one Docker reconciliation pass, upsert discovered workflows into the process-local registry, prune vanished workflows when Docker can report present container ids, retain the registry when Docker cannot report present ids, clear the scanning flag, and send a second websocket shell broadcast with refreshed inbox rows and status-bar counts.
  - Does not directly process the websocket broadcasts in this handler; htmx's websocket extension applies the out-of-band swaps when frames arrive, and the settings pane, selected worker detail, repository menu, files pane, diff pane, command palette, browser URL, selected worker id, and selected repository state are not part of the refresh shell.
  - Performs no direct htmx swap, DOM replacement, selected-worker change, repository-picker change, command-palette change, notification-permission request, websocket send, browser navigation, or focus movement from the click handler itself.
  - When the fetch promise settles fulfilled or rejected, removes `data-busy` and removes the `spinning` class from this same button so the control can be activated again.
  - Treats any fulfilled HTTP response, including non-`2xx` statuses, as enough to clear the busy state because no status code, response header, or body is inspected; the endpoint's JSON `ok` and `count` fields are not read by the browser.
  - On client-side fetch rejection, still clears the busy state through the `finally` handler but renders no failure text, toast, retry affordance, or status-bar error; the returned rejected promise is not caught by this handler.
  - Does not inspect the JSON response, surface refresh failures in the DOM, cancel an in-flight refresh, disable the sibling status-bar refresh button, synchronize busy state between the settings and status-bar refresh controls, or prevent a simultaneous refresh request started from the sibling control.
- code: groom/groom/templates/dashboard.html::doRefresh
- verify: groom/tests/test_app.py::test_refresh_prunes_vanished_containers
- verify: groom/tests/test_app.py::test_refresh_skips_prune_when_docker_unavailable

### rescan-containers-from-statusbar

- on: [statusbar refresh button](#statusbar-refresh-button)
- trigger: pointer click, tap, Enter, or Space activation of the native `#btn-refresh-bar` button in the status bar, captured by the delegated `document.body` click handler.
- role: button.
- name: `⟳`, computed from the button's visible text content; live-verified — the `title` attribute `Rescan containers (reconcile + prune)` is a tooltip/description only and is not the accessible name.
- keyboard: Tab or Shift+Tab reaches the always-visible status-bar button; Enter or Space activates it when focused; there is no additional shortcut for rescan.
- when:
  - The groom dashboard shell is loaded and the current `#statusbar` contains the native [statusbar refresh button](#statusbar-refresh-button).
  - The click event target or one of its ancestors matches `#btn-refresh-bar` and is not inside an answer form, repository menu, repository picker, or files/diff tree region that the body handler excludes first.
  - The matched status-bar button may be idle or may already carry `data-busy`; repeat activations while that same button's refresh request is in flight are accepted by the event handler but ignored by the refresh layer before another request is sent.
- does:
  - Calls `doRefresh` with the matched status-bar refresh button.
  - If that button already has `data-busy`, returns without changing DOM state, sending another request, cancelling the in-flight request, or affecting any other refresh control.
  - Sets `data-busy="1"` on the status-bar button and adds its `spinning` class, making the in-flight state local to this control.
  - Starts one browser fetch to [post refresh](../../http/groom.md#post-refresh) using method `POST`, with no query string, no handler-required headers, and no request body; the handler stores the returned promise only to attach its `finally` cleanup and does not return or await it for any later dashboard code.
  - Relies on the refresh endpoint to set the [dashboard discovery scanning flag](../../concepts/dashboard-discovery-scanning-flag.md) true, render [dashboard shell fragment](../../dashboard-shell-fragment.md) with out-of-band swap markers, and broadcast that shell over [WS /ws](../../http/groom.md#websocket-dashboard) before Docker reconciliation starts.
  - Causes every connected dashboard websocket client, including the tab that clicked this status-bar button when its websocket is connected, to receive the pre-scan shell broadcast as out-of-band replacements for `#inbox-list` and `#statusbar`; when the inbox list is otherwise empty and unfiltered, the scanning flag makes `#inbox-list` show the `Discovering containers...` loading state rather than the empty inbox message.
  - Lets the refresh endpoint run one Docker reconciliation pass, upsert discovered workflows into the process-local registry, prune vanished workflows when Docker can report present container ids, retain the registry when Docker cannot report present ids, clear the scanning flag, and send a second websocket shell broadcast with refreshed inbox rows and status-bar counts.
  - Does not directly process the websocket broadcasts in this handler; htmx's websocket extension applies the out-of-band swaps when frames arrive, and the settings pane, selected worker detail, repository menu, files pane, diff pane, command palette, browser URL, selected worker id, and selected repository state are not part of the refresh shell.
  - Performs no direct htmx swap, DOM replacement, selected-worker change, repository-picker change, command-palette change, notification-permission request, websocket send, browser navigation, or focus movement from the click handler itself.
  - When the fetch promise settles fulfilled or rejected, removes `data-busy` and removes the `spinning` class from the original matched button object; if a websocket out-of-band status-bar replacement already removed that element from the visible DOM, the visible replacement is the server-rendered idle refresh button.
  - Treats any fulfilled HTTP response, including non-`2xx` statuses, as enough to clear the busy state because no status code, response header, or body is inspected; the endpoint's JSON `ok` and `count` fields are not read by the browser.
  - On client-side fetch rejection, still clears the busy state through the `finally` handler but renders no failure text, toast, retry affordance, or status-bar error; the returned rejected promise is not caught by this handler.
  - Does not inspect the JSON response, surface refresh failures in the DOM, cancel an in-flight refresh, disable the sibling settings-pane refresh button, synchronize busy state between the settings and status-bar refresh controls, or prevent a simultaneous refresh request started from the sibling control.
- code: groom/groom/templates/dashboard.html::doRefresh
- verify: groom/tests/test_app.py::test_refresh_prunes_vanished_containers
- verify: groom/tests/test_app.py::test_refresh_skips_prune_when_docker_unavailable

### enable-browser-notifications-from-settings
- on: [settings enable notifications button](#settings-enable-notifications-button)
- trigger: pointer click, tap, Enter, or Space activation of the native `#btn-notify` button in the settings pane, captured by the delegated `document.body` click handler.
- role: button.
- name: `Enable notifications`.
- keyboard: Tab or Shift+Tab reaches the button while settings mode is active; Enter or Space activates it when focused; there is no additional shortcut for requesting notification permission.
- when:
  - The groom dashboard shell is loaded and the settings pane contains the native [settings enable notifications button](#settings-enable-notifications-button).
  - The click event target is exactly the `#btn-notify` button; the handler checks `e.target.id` rather than walking descendants with `closest`, and the shipped button has only a text node.
  - The event is not inside an answer form, repository menu, repository picker, or files/diff tree region that the delegated body click handler excludes before settings-button handling.
  - The browser exposes `window.Notification`; without that API, activation falls through with no permission request and no user-visible error.
- does:
  - If the page loaded with `window.Notification` present and `Notification.permission === "default"`, the independently registered one-time body click listener may also run on this same activation before the delegated settings click branch, call `Notification.requestPermission()`, and remove itself from `document.body`; the delegated branch still makes its own permission request for the settings button.
  - Skips worker-row selection, refresh-button handling, repository picker handling, files/diff tree handling, and answer-form interception because the click target is the notification button in the settings pane.
  - Calls `Notification.requestPermission()` from the delegated settings click branch when the Notification API exists, handing the prompt, persistence, grant, denial, and repeat-request behavior to the browser-owned [browser notification permission](../../concepts/browser-notification-permission.md) state.
  - Does not read the returned permission value, update the button label, disable the button, add busy state, show a toast, write to local storage, send an HTTP request, send a websocket message, navigate, or move focus after the browser permission flow resolves.
  - Leaves the selected worker id, selected repository state, inbox rows, selected worker detail, files tree, diff tree, status bar, command palette, websocket connection, and server workflow state unchanged.
  - Enables a later `groom:blocked` browser event caused by a [blocked push payload](../../blocked-push-payload.md) to create a system notification only when the browser subsequently reports `Notification.permission === "granted"`; denied, default, or unavailable permission still leaves in-page blocked toasts available.
- code: groom/groom/templates/dashboard.html::document.body click settings buttons

### filter-command-palette-results

- on: [command palette input](#command-palette-input)
- trigger: native `input` event after typing, paste, cut, undo, redo, clearing, or any other browser-supported value change in `#palette-input`.
- role: textbox.
- name: `Jump to a worker or blocked gate`.
- keyboard: ordinary single-line text editing changes the filter query immediately; Enter selects the active or first result through the separate document-level keydown branch; Escape closes the palette through the separate document-level keydown branch; arrow keys, `j`, and `k` do not move the active palette result.
- when:
  - The groom dashboard shell is loaded and the palette input has its `input` listener registered.
  - The command palette is normally open with focus on `#palette-input`, although the listener itself does not check the overlay's open state.
  - `#inbox-list` may contain zero or more currently rendered `.row` elements from the server-rendered operator inbox; no fresh inbox data is requested before filtering.
- does:
  - Reads the current input value from the event target and passes it to `renderPalette` without debouncing, form submission, websocket send, HTTP request, browser navigation, or URL mutation.
  - Lowercases the query for case-insensitive substring matching.
  - Reads the current ordered list of `#inbox-list .row` elements from the DOM at filter time.
  - For each source row, normalizes `textContent` by collapsing whitespace and trimming ends, copies `data-worker-id` into the result id, and copies `data-state` into the result state.
  - Builds palette result data entirely from currently rendered inbox-row DOM attributes and text; it does not re-run the server-side [operator inbox](../../operator-inbox.md) query matcher and does not consult workflow objects directly.
  - Filters out source rows whose normalized text does not contain the lowercased query; an empty query keeps every current source row.
  - Replaces `#palette-results` contents with one generated `.presult` row for each match, or an empty string when no rows match.
  - Preserves the source row DOM order for every matching result, without sorting or grouping by state, gate, repository, worker id, or match position.
  - Marks only the first generated result with the `active` class; if there are no matches, no active result exists; later input events recompute the active result from scratch instead of preserving the previous active row.
  - Renders each result with `data-id`, a state dot class, normalized row text, and a trailing hint that is `gate` when the row state is `blocked` and otherwise the row state string.
  - Assigns the generated result markup as HTML; the values are derived from the current DOM, and the layer performs no additional HTML escaping or sanitizer pass before replacing `#palette-results`.
  - Leaves focus on the command palette input, and leaves the selected worker id, selected worker detail, activity mode, repository picker, status bar, websocket connection, browser URL, and server workflow state unchanged until Enter or result click selects a generated result.
  - Does not expose the input/results pair as an ARIA combobox/listbox, update `aria-activedescendant`, make result rows focusable, or announce result-count changes through an `aria-live` region.
  - Calls no groom first-party JavaScript or Python symbol beyond this layer; all helper calls are browser DOM APIs or JavaScript built-ins.
- code: groom/groom/templates/dashboard.html::renderPalette

### select-command-palette-result

- on: [command palette result](#command-palette-result)
- trigger: pointer click or tap on a generated `.presult` row or any descendant of that row, captured by the delegated `#palette-results` click listener; the same selection outcome is also available through the document-level Enter key branch while the palette is open.
- role: none for pointer activation because the generated result is a clickable `div`; keyboard activation is a shortcut-like document handler, not focus on an individual option.
- name: none as a robust control name; selection is keyed by generated `data-id`, while visible normalized row text and hint text are not exposed through a named interactive role.
- keyboard: Enter selects `#palette-results .presult.active` while the palette is open, or the first `.presult` if none is active; individual rows cannot receive focus and do not support Enter, Space, arrows, `j`, or `k` as row-local interactions.
- when:
  - The groom dashboard shell is loaded and the command palette has been opened by [command palette shortcut](#command-palette-shortcut), or otherwise contains generated palette results from [filter command palette results](#filter-command-palette-results).
  - For pointer activation, the click event bubbles to `#palette-results`; the original target or one of its ancestors inside that result container may match `.presult`.
  - Pointer clicks in empty result space, on `#palette-results` itself, or on descendants that are not inside a `.presult` have no palette-selection effect.
  - For keyboard activation, `#palette` currently has the `open` class and the key event is `Enter`; this branch runs after the `Ctrl+K`/`Meta+K` toggle and Escape close branches, and before the later text-entry guard and `j`/`k` inbox-row movement branch.
  - Keyboard activation chooses `#palette-results .presult.active` when present; otherwise it falls back to the first generated `.presult` row; if neither exists, Enter returns without changing selection or closing the palette.
  - A selectable result normally has `data-id` copied from an [inbox worker row](#inbox-worker-row) `data-worker-id`; the handler does not validate that the value is non-empty, still exists in `#inbox-list`, or still exists in the server workflow registry before attempting selection.
- does:
  - For pointer activation, resolves the actionable row by walking from the original event target to the nearest `.presult`; if no result row is found, returns without selecting a worker, changing mode, closing the palette, preventing default behavior, or stopping event propagation.
  - For keyboard activation with no active or first result, returns from the Enter branch without preventing default behavior, changing dashboard mode, selecting a worker, fetching detail, closing the palette, or running `j`/`k` row movement for the same event.
  - Reads the selected workflow container id from the clicked result's `data-id`, or from the active-or-first result's `data-id` for Enter activation, exactly as stored in the DOM.
  - For a clicked result row or Enter activation with a selectable result, runs the dashboard-local operations in this order: switch to inbox mode, select the result's worker id, and close the command palette.
  - Calls `setMode("inbox")`, which writes `data-mode="inbox"` to the root `.app`, makes the inbox pane the visible activity pane, recomputes the activity-bar `active` class so the inbox icon is active and files, diff, and settings are inactive, and closes the repository picker overlay if it is open.
  - The inbox mode switch retains selected repository browser state, repository picker labels, existing files tree, file view, diff tree, parsed diff cache, diff view, visible inbox rows, selected worker detail, status bar, websocket connection, and browser URL; it does not load files or diff data because the selected mode is neither `files` nor `diff`.
  - Calls the shared row selection handler with the result id, stores that id as the browser-local [dashboard selected worker state](../../dashboard-selected-worker-state.md), and performs no trimming, normalization, empty-string rejection, or existence check before persisting it.
  - Recomputes `selected` class state through the [dashboard inbox selection applier](../../concepts/dashboard-inbox-selection-applier.md) across every `[data-worker-id]` element currently in the document, marking each element whose `data-worker-id` equals the selected id and clearing the class from every other worker-bearing element.
  - Sends `GET /worker/{encodeURIComponent(id)}` to [get worker detail](../../http/groom.md#get-worker-detail) through htmx with target `#detail` and `innerHTML` swap; the request has no query string, request body, history update, or browser navigation.
  - When the worker-detail response swaps into `#detail`, the normal htmx `afterSwap` listener rerenders escaped gate markdown and wires the worker-detail working-tree diff disclosure for the newly selected detail fragment.
  - If the server no longer knows the selected worker id, the worker-detail endpoint supplies its not-found detail fragment; the client-side palette selection path does not special-case that response.
  - Calls the command-palette close helper after issuing the detail request, before the asynchronous detail response settles.
  - Removes only the `open` class from `#palette`, closing the command palette overlay; the operation is idempotent if the palette has already lost `open`.
  - Leaves `#palette-input` value, `#palette-results` generated result markup, the result row `active` class, and the `#palette` DOM subtree in place until the next palette render or page teardown.
  - Leaves repository selection, files tree, diff tree, status bar, toast stack, websocket connection, browser URL, and server workflow state unchanged by the client-side selection itself.
  - Does not move focus after closing the palette, restore focus to a visible opener, clear palette contents, send a websocket message, submit an answer form, mutate server state, announce the detail-load state through an `aria-live` region, or expose selected result state through `aria-selected`.
- code: groom/groom/templates/dashboard.html::palRes click listener
- code: groom/groom/templates/dashboard.html::keydown
- code: groom/groom/templates/dashboard.html::setMode
- code: groom/groom/templates/dashboard.html::select
- code: groom/groom/templates/dashboard.html::closePalette
