---
type: concept
slug: workflow-state-dot-renderer
title: Workflow state dot renderer
---
# Workflow state dot renderer

Workflow state dot renderer is the groom render-layer helper that turns one [workflow state](workflow-state.md) enum member into the compact visual marker used by [inbox worker rows](../gui/screens/groom-dashboard.md#inbox-worker-row), [repository menu options](../gui/screens/groom-dashboard.md#repository-menu-option), status-bar counts, and [worker detail renderer](worker-detail-renderer.md) headers. It uses the [HTML escape helper](html-escape-helper.md) for attribute safety and emits only the marker span; surrounding renderers decide the row text, count text, selection state, accessible contract, and whether the marker appears beside a [workflow type badge](workflow-type-badge-renderer.md). The [command palette result](../gui/screens/groom-dashboard.md#command-palette-result) mirrors the same `dot {state}` fragment shape client-side from an already-rendered inbox row rather than calling this server helper.

- code: groom/groom/render.py::_state_dot

## Contract

- purpose: serialize one workflow lifecycle value as a CSS-addressable state marker for dashboard fragments.
- input: a required [workflow state](workflow-state.md) enum member.
- output: one HTML `<span>` fragment with base class `dot`, one state-specific class equal to the escaped enum value, no attributes other than `class`, no children, and no trailing whitespace; the fragment is complete and can be concatenated directly into any larger server-rendered HTML fragment.
- fragment template: `<span class="dot {escaped_state_value}"></span>`.
- state values: the state-specific class is one of `running`, `blocked`, `idle`, or `finished` when the caller supplies a supported workflow state.
- text content: none; the marker is purely visual and must be paired by callers with surrounding text, attributes, or labels when state must be perceivable without color.
- accessibility: no role, accessible name, focusability, or keyboard operation is added by this helper; it is not an interactive control and does not by itself announce state to assistive technology.
- escaping: the enum value is HTML-escaped before being inserted into the class attribute; the helper performs HTML attribute escaping only, not CSS-token validation or lifecycle normalization.
- value preservation: the helper does not lowercase, translate, alias, trim, split, or fallback the lifecycle value; supported callers must supply a canonical [workflow state](workflow-state.md) member whose `value` is already one of the dashboard state class tokens.
- visual mapping: dashboard CSS treats `.dot` as an 8-by-8 pixel non-flexing circular marker, maps `.dot.blocked`, `.dot.running`, `.dot.idle`, and `.dot.finished` to the service state colors, animates blocked dots with a pulse, and disables that pulse when `prefers-reduced-motion: reduce` is active.
- composition: callers concatenate the fragment into larger server-rendered HTML rather than wrapping it here; the same renderer output is used in list rows, option rows, status segments, and detail headers.
- unsupported input: the helper relies on the supplied object exposing `value`; unsupported objects are outside the supported contract and are not normalized into a fallback state.
- caller obligation: any consumer that needs the state to be perceivable must pair the dot with visible text, `data-state`, a count label, row metadata, or another accessible state announcement outside this helper.
- side effects: rendering performs no workflow lookup, registry mutation, HTTP response construction, websocket send, browser event dispatch, CSS mutation, or dashboard DOM mutation.
- state mutation: rendering does not mutate workflow containers, workflow state, gate records, registry membership, selected row state, websocket queues, sidecar state, Docker state, answer files, or gate files.

## Fields

### field-state

- type: [workflow state](workflow-state.md)
- default: none
- required: true
- meaning: lifecycle enum member whose string value supplies the visual marker class.

### field-state-dot-fragment

- type: HTML fragment
- default: none
- required: true
- meaning: `<span class="dot {state.value}"></span>` with the state value escaped for attribute context, no text node, and no semantic role.

### field-state-class

- type: CSS class token
- default: none
- required: true
- meaning: escaped `state.value` appended after the base `dot` class; canonical values are `running`, `blocked`, `idle`, and `finished`.

### field-visual-style

- type: CSS contract
- default: service stylesheet rules for `.dot` and `.dot.{state}`
- required: true for visible dashboard state markers
- meaning: an 8-by-8 circular, non-flexing marker whose color and optional blocked-state pulse are supplied by dashboard stylesheet rules, not by inline style or this renderer's HTML output.

## Usage Sites

- inbox worker row: appears before the optional workflow type badge and before repository, worker-id, gate-path, exit-code, or current-node text; the row also exposes the same state through `data-state`.
- repository option: appears inside each `role="option"` repository-picker row before the optional workflow type badge and label.
- status bar state segment: appears before the numeric count and visible state text, so the count remains perceivable without relying on dot color.
- worker detail header: appears before the optional workflow type badge, repository label, short id, visible state text, optional current node, and optional exit hint.
- palette result row: client-side palette rendering copies an already-rendered row state into a `dot` class token and visible hint, mirroring this marker contract without invoking the server helper.

## Methods

### method-render-workflow-state-dot

- sig: `_state_dot(state: WorkflowState) -> str`
- abstract: false
- raises: none intentionally raised for supported workflow-state enum members.
- returns: one empty HTML span fragment with classes `dot` and the escaped state value.
- code: groom/groom/render.py::_state_dot
- summary: render the non-interactive visual marker for a single workflow lifecycle state.
- args:
  - `state`: required [workflow state](workflow-state.md) enum member; its `value` string supplies the state-specific CSS class.
- does:
  - Reads the supplied workflow state's `value` string.
  - Calls [method-escape-html-value](html-escape-helper.md#method-escape-html-value) once to escape that string for quoted HTML attribute context.
  - Concatenates the escaped value after the base `dot` class in the returned span's `class` attribute.
  - Preserves the workflow state's value exactly after HTML escaping; no state-order lookup, CSS color lookup, fallback class, or accessibility label is selected here.
  - Emits no text node, role, accessible name, focus target, keyboard binding, htmx attribute, websocket attribute, data attribute, inline style, or script.
  - Leaves all perceivable state text, counts, repository labels, workflow type badges, row selection classes, palette hints, and detail metadata to the caller.
  - Does not mutate workflow containers, open gates, registry membership, scanning state, selected-row state, websocket queues, browser DOM state, sidecar state, Docker state, answer logs, answer files, or gate files.

Builds the visual state marker from the supplied lifecycle enum. The method reads only `state.value`, delegates attribute escaping to the local HTML escaping helper, and returns the completed span fragment for its caller to concatenate into a larger row, option, status segment, or detail header.

## Failure Semantics

- supported input: every canonical [workflow state](workflow-state.md) enum member is successful and returns the marker fragment for that state.
- unsupported object: an object without a `value` attribute is outside the supported contract and can fail through ordinary attribute access rather than returning a fallback marker.
- unsupported state token: a non-canonical value string is escaped and emitted as a class token, but groom supplies only the documented workflow-state enum values; the renderer does not validate the token against the stylesheet's state classes.
- delegated escaping failure: ordinary exceptions from the [HTML escape helper](html-escape-helper.md#method-escape-html-value) propagate; this renderer does not catch them or replace the dot with a neutral state.

## Invariants

- pure fragment: the returned string is always one span and never includes sibling text, labels, counts, badges, scripts, htmx attributes, websocket attributes, or data attributes.
- caller-owned perception: because the marker has no text, role, or accessible name, every accessible state announcement must come from the surrounding row, option, status segment, detail header, or visible state/count text.
- no lifecycle decision: this renderer never chooses state priority, changes workflow state, derives a state from gates or exit codes, or decides whether a workflow belongs in the inbox, repository picker, status bar, command palette, or detail pane.
