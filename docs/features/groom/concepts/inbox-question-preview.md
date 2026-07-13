---
type: concept
slug: inbox-question-preview
title: Inbox question preview
---
# Inbox question preview

Inbox question preview is the operator-facing summary derived from a [gate info](gate-info.md) question for a blocked [inbox worker row](../gui/screens/groom-dashboard.md#inbox-worker-row) in the [operator inbox](../operator-inbox.md). It is consumed by the row-rendering path inside the operator inbox and returns plain text that the row renderer passes through the [HTML escape helper](html-escape-helper.md) before inserting into browser HTML.

- code: groom/groom/render.py::_question_preview
- verify: groom/tests/test_render.py::test_inbox_shows_only_workers_with_open_gates

## Contract

- purpose: reduce a possibly multiline, markdown-like operator gate question to a one-line inbox summary that can fit in a worker row.
- input: `question` is a string from [gate info](gate-info.md) `question`; callers pass an already string-normalized gate question.
- output: returns a plain text string suitable for later escaping and insertion into an inbox row; returns an empty string when no line contains visible content after normalization.
- line selection: scans source lines in their original order and selects the first line that remains non-empty after whitespace and marker trimming.
- normalization: trims leading and trailing whitespace, removes any leading run made only of Markdown heading (`#`), quote (`>`), list (`*` or `-`), backtick, and space marker characters, then trims whitespace again; this is character trimming rather than Markdown parsing.
- marker stripping: every leading character in the marker set is removed until the first character outside the set; a literal preview that intentionally begins with those characters loses them the same way a Markdown prompt marker does.
- length cap: returns at most the first 140 code points of the selected normalized line; it does not append an ellipsis or otherwise mark truncation.
- escaping boundary: does not HTML-escape the returned text; the inbox row renderer escapes the preview before appending it to the `.q` text node.
- consumer condition: the inbox row renderer asks for a preview only for a blocked workflow with a selected gate; running, idle, finished, or gate-less rows render no preview container through this concept.
- display boundary: contains no row markup, state classes, worker identity, gate path, or answer controls; it is only the visible question summary text for the row renderer to place under the row's first line.
- empty result: suppresses visible preview text only by returning the empty string; the blocked row renderer still emits the `.q` container for a selected gate even when the contained preview text is empty.
- whitespace handling: internal whitespace in the selected line is preserved exactly; only the line boundary whitespace and leading marker run are removed.
- multiline handling: later lines are ignored after the first normalized non-empty line; the method never joins lines, collects paragraphs, renders markdown, or inspects gate status.
- side effects: does not mutate the gate record, workflow state, inbox selection, browser state, files, network connections, or renderer globals.

## Fields

### field-question

- type: `str`
- default: none
- required: true
- meaning: source question text from [gate info](gate-info.md), potentially empty, multiline, markdown-like, or longer than the row preview budget.
- constraints: callers must provide a string; non-string values are outside the supported contract.

### field-source-lines

- type: `list[str]`
- default: derived from `question.splitlines()`
- required: true
- meaning: ordered source lines examined for the first visible preview candidate.

### field-marker-character-set

- type: `set[str]`
- default: `#`, `>`, `*`, `-`, backtick, and space
- required: true
- meaning: characters stripped from the beginning of each already-trimmed source line before the final whitespace trim.

### field-preview-text

- type: `str`
- default: empty string when no source line normalizes to visible text
- required: true
- meaning: first normalized non-empty line truncated to the inbox preview cap, returned as unescaped text for the row renderer.

### field-preview-length-cap

- type: integer code-point count
- default: `140`
- required: true
- meaning: maximum returned preview length; excess text after the first 140 code points is discarded without a truncation marker.

## Methods

### method-build-question-preview

- sig: `_question_preview(question: str) -> str`
- abstract: false
- raises: none intentionally raised for empty, whitespace-only, marker-only, multiline, or long question text.
- code: groom/groom/render.py::_question_preview

Builds the text preview for one gate question. The method treats every source line independently, ignores leading empty or marker-only lines, strips common Markdown prompt/list/code decoration from the first useful line, and truncates the final text to the inbox preview cap without adding any truncation marker.

#### Effects

- Reads: only the supplied gate question string.
- Splits: the source question into lines using ordinary line-boundary splitting; line break characters are never emitted in the preview.
- Normalizes: each line by trimming surrounding whitespace, stripping every leading character in the marker set `#>*-` plus backtick and space, then trimming surrounding whitespace again.
- Filters: ignores source lines whose normalized text is empty after marker and whitespace trimming.
- Emits: the first normalized non-empty line truncated to no more than 140 code points, or an empty string when no useful line exists.
- Preserves: internal spaces, punctuation, markdown syntax after the leading marker run, non-ASCII characters, and casing in the selected line.
- Leaves escaping to: [method-escape-html-value](html-escape-helper.md#method-escape-html-value) through the inbox row renderer, so this method's return value must be treated as text rather than trusted HTML.
- Calls: no first-party groom symbols; it uses only string operations.
- Does not mutate: [gate info](gate-info.md), [workflow containers](workflow-container.md), [operator inbox](../operator-inbox.md) ordering, selected worker state, or browser DOM state.

#### Algorithm

1. Split the question text into source lines in order.
2. For each line, trim surrounding whitespace, remove all leading marker characters in the set `#`, `>`, `*`, `-`, backtick, and space, then trim surrounding whitespace again.
3. Return the first normalized line whose text is not empty, truncated to the first 140 code points.
4. Return the empty string when every source line is empty or marker-only after normalization.

## Failure Semantics

- Empty input: an empty string, whitespace-only string, marker-only string, or multiline string with no normalized visible line succeeds and returns the empty string.
- Long input: a useful line longer than the preview cap succeeds and returns only the first 140 code points; there is no error, ellipsis, or length metadata.
- Markup-like input: HTML or markdown-like characters in the returned preview are not escaped or sanitized here; safety depends on the row renderer passing the result through the [HTML escape helper](html-escape-helper.md).
- Unsupported input type: values without `splitlines()` support are outside the supported contract and can fail with ordinary Python attribute errors; the concept does not coerce arbitrary objects.
- Delegated exceptions: this method defines no domain-specific exception, partial-result object, status code, logging path, or fallback renderer.

## Invariants

- first-useful-line: at most one source line contributes to the preview.
- plain-text-boundary: the returned preview is always plain text, never HTML markup, markdown-rendered HTML, or a DOM fragment.
- deterministic-preview: the same question string always returns the same preview string and does not depend on workflow state, selected worker, registry membership, browser state, time, filesystem state, or network state.
- consumer-owned-visibility: whether the preview is visible is decided by the blocked-row renderer; this concept only computes the text it is given.
