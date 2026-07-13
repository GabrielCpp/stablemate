---
type: concept
slug: workflow-type-badge-renderer
title: Workflow type badge renderer
---
# Workflow type badge renderer

Workflow type badge renderer is the groom render-layer helper that turns a workflow kind string from a [workflow container](workflow-container.md#field-workflow-type) into the optional visual chip used by [inbox worker rows](../gui/screens/groom-dashboard.md#inbox-worker-row), [repository menu options](../gui/screens/groom-dashboard.md#repository-menu-option), and [worker detail renderer](worker-detail-renderer.md) headers. It uses the [HTML escape helper](html-escape-helper.md) for the emitted attribute and text nodes, emits only the badge span or no fragment, and relies on the dashboard stylesheet's `.badge` and `.badge[data-type="..."]` rules for presentation; surrounding components decide the row text, selection state, accessible contract, and whether the type is also exposed through other text.

- code: groom/groom/render.py::_type_badge
- verify: groom/tests/test_render.py::test_repo_menu_one_entry_per_container_repo

## Contract

- purpose: serialize one workflow type string as a compact, CSS-addressable badge whose color remains stable for that type without requiring a new stylesheet rule.
- input: optional workflow type string from a workflow container.
- output: empty string when the workflow type is empty; otherwise one HTML `<span>` fragment with class `badge`, a `data-type` attribute, a `--type-hue` inline style, and visible text equal to the escaped workflow type.
- placement: callers concatenate the returned fragment immediately after the workflow state dot and before the repository label, repository option label, or worker-detail header label; this helper does not add separators, wrapper elements, row attributes, or surrounding whitespace outside the single space between the `data-type` and `style` attributes.
- color derivation: start hue at `0`; for each character in the original unescaped workflow type string, replace hue with `(hue * 31 + character code point) % 360`; use the resulting integer as `--type-hue:{hue}`.
- fixed-style compatibility: dashboard CSS gives `.badge` uppercase monospace chip styling with text color `#0c0f14`; `data-type="coder"` uses the fixed `#2f9e8f` background, `data-type="author"` uses the fixed `#8a6ff0` background, and all other type values use `background:hsl(var(--type-hue,210),45%,58%)` from the inline custom property.
- accessibility: no role, accessible name, focusability, or keyboard operation is added by this helper; it is not interactive, and callers must ensure the workflow type remains perceivable through surrounding row or option text when needed.
- escaping: the workflow type is HTML-escaped separately for the `data-type` attribute and visible text node after hue calculation; escaped entities do not affect the hue, and the derived hue is numeric and does not require HTML escaping.
- state mutation: rendering does not mutate workflow containers, workflow state, gate records, registry membership, selected row state, repository selection state, websocket queues, sidecar state, Docker state, answer files, or gate files.

## Presentation

- base selector: `.badge` supplies monospace typography, uppercase visual transform, compact padding, rounded corners, dark text, and the hue-driven fallback background.
- fixed selectors: `.badge[data-type="coder"]` and `.badge[data-type="author"]` override the fallback hue with fixed backgrounds while preserving the same text, spacing, and shape contract.
- fallback selector: all non-empty workflow type values without a fixed selector use the inline `--type-hue` custom property emitted by this helper; the CSS fallback hue of `210` is only used if a badge-shaped fragment lacks the custom property.
- text transform: the helper emits the original escaped workflow type text, and CSS applies uppercase presentation; the underlying `data-type` value remains the original escaped string for selectors and tests.
- layout ownership: margins, row gaps, selected state, active descendant state, and live-region semantics belong to the caller's component rather than the badge fragment.

## Algorithm

1. Receive one workflow type string from the caller.
2. If the string is empty, return the empty string and perform no hue calculation or escaping.
3. Initialize the hue accumulator to integer `0`.
4. For each Unicode character in the original unescaped workflow type string, replace the accumulator with `(hue * 31 + ord(character)) % 360`.
5. Escape the original workflow type for the `data-type` attribute value.
6. Escape the original workflow type again for the visible text node.
7. Return exactly one span: `<span class="badge" data-type="{escaped_type}" style="--type-hue:{hue}">{escaped_type}</span>`.

## Inputs

### field: workflow-type

- type: `str`
- default: empty string
- required: false
- meaning: workflow kind label to render, commonly `author`, `coder`, or another discovery-supplied workflow kind; the helper imposes no enum, trimming, case folding, slug validation, or maximum length.

## Output

### field: type-badge-fragment

- type: HTML fragment or empty string
- default: empty string
- required: false
- meaning: absent for an empty workflow type; otherwise `<span class="badge" data-type="{workflow_type}" style="--type-hue:{hue}">{workflow_type}</span>` with workflow type text escaped for attribute and text contexts.

### field: class-attribute

- type: HTML class attribute
- default: absent when the workflow type is empty; otherwise `badge`
- required: false
- meaning: stable styling hook for dashboard chip presentation; no state, workflow kind, or caller context is added to the class list.

### field: data-type-attribute

- type: HTML data attribute
- default: absent when the workflow type is empty
- required: false
- meaning: escaped original workflow type string used by dashboard CSS for fixed `coder` and `author` colors and by tests as the durable emitted-type hook.

### field: type-hue-style

- type: inline CSS custom-property declaration
- default: absent when the workflow type is empty
- required: false
- meaning: `--type-hue:{hue}` where `hue` is the deterministic integer produced from the original workflow type string by the documented hash algorithm; consumed by the `.badge` fallback background color for workflow types without a fixed `data-type` rule.

### field: visible-type-text

- type: escaped HTML text node
- default: absent when the workflow type is empty
- required: false
- meaning: escaped original workflow type displayed inside the badge; the helper does not uppercase this text itself, leaving uppercase presentation to CSS.

## Methods

### method-render-workflow-type-badge

- sig: `_type_badge(workflow_type: str) -> str`
- abstract: false
- raises: none intentionally raised for empty, known, unknown, short, long, or non-ASCII workflow type strings.
- code: groom/groom/render.py::_type_badge
- verify: groom/tests/test_render.py::test_repo_menu_one_entry_per_container_repo

Builds the optional workflow type chip from the supplied string. Empty type strings return no fragment. Non-empty strings are hashed into a hue by iterating over the string's characters, then the escaped type string is used for both the badge's `data-type` attribute and visible text.

#### Effects

- Reads: the supplied workflow type string only.
- Returns: empty string when `workflow_type` is empty.
- Computes: a deterministic hue integer in the inclusive range `0` through `359` from the complete original workflow type string before HTML escaping.
- Emits: one `<span class="badge" data-type="..." style="--type-hue:{hue}">...</span>` HTML fragment for a non-empty workflow type.
- Emits: no leading or trailing whitespace around the span and no wrapper element around the badge.
- Escapes: the workflow type string once for the `data-type` attribute and once for the visible badge text.
- Excludes: workflow state dots, repository labels, worker ids, gate paths, question previews, row selection classes, htmx attributes, websocket envelopes, and browser-event scripts.
- Calls: [HTML escape helper](html-escape-helper.md#method-escape-html-value) for HTML attribute and text escaping.
- Does not mutate: workflow containers, open gates, registry membership, scanning state, selected-row state, websocket queues, browser DOM state, sidecar state, Docker state, answer logs, answer files, or gate files.
