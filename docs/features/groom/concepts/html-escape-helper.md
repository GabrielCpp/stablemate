---
type: concept
slug: html-escape-helper
title: HTML escape helper
---
# HTML escape helper

HTML escape helper is the [groom render module](groom-render-module.md) utility used by dashboard fragments such as the [inbox worker row](../gui/screens/groom-dashboard.md#inbox-worker-row), [worker detail renderer](worker-detail-renderer.md), [workflow state dot renderer](workflow-state-dot-renderer.md), [workflow type badge renderer](workflow-type-badge-renderer.md), and [dashboard shell renderer](dashboard-shell-renderer.md) to turn optional untrusted text into browser-safe HTML attribute or text-node content. It is the boundary helper for dynamic strings that originate from [workflow containers](workflow-container.md), [gate info](gate-info.md), sidecar state, Docker metadata, or operator-visible workflow labels before those strings are concatenated into server-rendered HTML.

- code: groom/groom/render.py::esc
- verify: groom/tests/test_render.py::test_gate_question_rendered_as_escaped_data_md_text_node

## Contract

- purpose: convert one optional string value into a safe HTML string for attribute values or text nodes in groom-rendered fragments.
- input: optional string; `None` is treated exactly like the empty string.
- output: escaped string; never `None`; `None` and empty-string input both return the empty string.
- escaping: escapes ampersands, less-than signs, greater-than signs, double quotes, and single quotes so the result is safe for quoted HTML attributes as well as text nodes; double quotes become `&quot;` and single quotes become `&#x27;`.
- quote handling: quote escaping is always enabled; callers do not choose a text-only mode.
- trust boundary: callers may pass workflow names, repository labels, branch names, container ids, gate paths, current-node names, gate questions, exit-code text, and other display values without pre-escaping them.
- caller scope: the helper protects loading messages, workflow state values, workflow type badges, repository-menu attributes and labels, inbox row attributes and text, answer-form hidden values, diff-disclosure attributes, detail-head metadata, no-gate detail text, gate question markdown text nodes, and gate path text.
- idempotence: already-escaped text is not decoded first, so existing entities are escaped again through the leading ampersand.
- non-goals: the helper does not sanitize markdown or HTML documents, validate URLs, allowlist CSS classes, render markdown, mark content as trusted, serialize JavaScript data, or apply DOMPurify; callers that display markdown keep using the escaped text-node path before the browser sanitizer reads the text.
- state mutation: escaping does not mutate workflow containers, gate records, registry state, sidecar state, Docker state, browser DOM state, answer files, or gate files.

## Inputs

### field-value

- type: `str | None`
- default: none
- required: true
- meaning: the display value to place into a server-rendered HTML attribute or text node.

## Output

### field-escaped-value

- type: `str`
- default: empty string when input is `None` or empty
- required: true
- meaning: the escaped representation of the input value, with quote characters encoded for quoted attribute contexts.

## Methods

### method-escape-html-value

- sig: `esc(value: str | None) -> str`
- abstract: false
- raises: none intentionally raised for `None`, empty strings, quote characters, markup-like text, already-escaped entity text, or non-ASCII text.
- code: groom/groom/render.py::esc
- verify: groom/tests/test_render.py::test_gate_question_rendered_as_escaped_data_md_text_node

Escapes a single dynamic value for insertion into groom HTML fragments. The method first normalizes `None` input to the empty string, then applies HTML escaping with quote escaping enabled and returns the escaped string to the caller.

#### Effects

- Reads: the supplied optional string only.
- Normalizes: `None` to the empty string before escaping.
- Returns: an empty string for `None` and empty-string input.
- Preserves: non-empty input text other than the escaped character substitutions; the method does not trim, lowercase, truncate, normalize whitespace, decode entities, parse markdown, or inspect the semantic meaning of the value.
- Escapes: `&`, `<`, `>`, double quote, and single quote characters for HTML-safe output, including `&quot;` and `&#x27;` substitutions suitable for double-quoted attribute values.
- Calls: Python standard-library `html.escape` with quote escaping enabled; this is a standard-library boundary and does not create a deeper groom layer.
- Does not validate: workflow ids, repository names, branch names, gate paths, markdown content, CSS class names, URLs, websocket frames, or htmx attributes.
- Does not mutate: workflow containers, open gates, registry membership, scanning state, selected-row state, websocket queues, browser DOM state, sidecar state, Docker state, answer logs, answer files, or gate files.
