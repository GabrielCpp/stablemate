---
type: concept
slug: run-question-preview
title: Run question preview
---
# Run question preview

Run question preview is the one-line summary derived from a [gate info](gate-info.md) question so a blocked [run row](../gui/screens/groom-dashboard.md#run-row) in the [runs fleet view](../runs-fleet-view.md) says *what* it is asking without the operator having to open it. It is computed by the [groom projection module](groom-projection-module.md) and travels to the browser as data, on a run row's `question` field and on every gate's `preview` field.

It is deliberately a server-side projection rather than a CSS truncation. What the row shows is a judgement — which line of a multi-line, markdown-ish prompt is the *useful* one — and a judgement made in two places drifts. The full question travels alongside it, so the detail pane can render the whole thing without asking again.

Nothing here escapes anything, and nothing needs to: the value is JSON, the client assigns it through Preact's text interpolation, and it never reaches `innerHTML`. That is the difference from the fragment era, where the preview was interpolated into a server-rendered row and its safety depended on an escape helper being called at exactly the right place.

- code: groom/groom/projection.py::question_preview
- refs: [gate info](gate-info.md), [groom projection module](groom-projection-module.md), [runs fleet view](../runs-fleet-view.md)
- verify: groom/tests/test_projection.py::test_gate_question_travels_as_data_not_markup

## Contract

- purpose: reduce a possibly multiline, markdown-like operator gate question to a one-line summary that fits in a fleet row.
- input: `question` is a string from [gate info](gate-info.md) `question`; callers pass an already string-normalized gate question.
- output: plain text; the empty string when no line contains visible content after normalization.
- line selection: scans source lines in their original order and selects the first line that remains non-empty after whitespace and marker trimming.
- normalization: trims surrounding whitespace, removes any leading run made only of Markdown heading (`#`), quote (`>`), list (`*` or `-`), backtick, and space characters, then trims again. This is character trimming, not Markdown parsing.
- marker stripping: every leading character in the marker set is removed until the first character outside it; a line that intentionally begins with those characters loses them the same way a Markdown marker does.
- length cap: at most the first 140 code points of the selected line, with no ellipsis or other truncation marker.
- no escaping: the return value is JSON data. There is no HTML escaping step anywhere on its path, because it never becomes markup — the client sets it as text.
- row condition: a run row carries a non-empty `question` only when the run is blocked *and* has a gate; running, idle, finished, and gate-less rows carry `""`.
- gate condition: every projected gate carries a `preview` regardless of its run's state, because the detail pane shows gates directly.
- full text travels too: the row's preview never replaces the question. `gate_dict` carries both `question` and `preview`, so the pane can show the whole prompt without a second request.
- display boundary: contains no markup, state class, run identity, gate path, or answer control — only the summary text.
- whitespace: internal whitespace in the selected line is preserved exactly; only line-boundary whitespace and the leading marker run are removed.
- multiline: later lines are ignored once a normalized non-empty line is found; the function never joins lines, collects paragraphs, renders markdown, or inspects gate status.
- side effects: none. It does not mutate the gate record, workflow state, selection, or any module state.

## Fields

### field-question

- type: `str`
- default: none
- required: true
- meaning: source question text from [gate info](gate-info.md), potentially empty, multiline, markdown-like, or longer than the preview budget.
- constraints: callers must provide a string; non-string values are outside the supported contract.

### field-source-lines

- type: `list[str]`
- default: derived from `question.splitlines()`
- required: true
- meaning: ordered source lines examined for the first visible preview candidate.

### field-marker-character-set

- type: `str` of characters passed to `lstrip`
- default: `#`, `>`, `*`, `-`, backtick, and space
- required: true
- meaning: characters stripped from the beginning of each already-trimmed source line before the final whitespace trim.

### field-preview-text

- type: `str`
- default: empty string when no source line normalizes to visible text
- required: true
- meaning: the first normalized non-empty line truncated to the preview cap, returned as data.

### field-preview-length-cap

- type: integer code-point count
- default: `140`
- required: true
- meaning: maximum returned preview length; excess text is discarded without a truncation marker.

## Methods

### method-build-question-preview

- sig: `question_preview(question: str) -> str`
- abstract: false
- raises: none intentionally raised for empty, whitespace-only, marker-only, multiline, or long question text.
- code: groom/groom/projection.py::question_preview

Builds the text preview for one gate question. Each source line is treated independently: leading empty or marker-only lines are skipped, common Markdown prompt/list/code decoration is stripped from the first useful line, and the result is truncated to the cap without a marker.

#### Effects

- Reads: only the supplied gate question string.
- Splits: the source question into lines using ordinary line-boundary splitting; line-break characters never appear in the preview.
- Normalizes: each line by trimming surrounding whitespace, stripping every leading character in the marker set, then trimming again.
- Filters: ignores lines whose normalized text is empty.
- Emits: the first normalized non-empty line truncated to no more than 140 code points, or an empty string when no useful line exists.
- Preserves: internal spaces, punctuation, markdown syntax after the leading marker run, non-ASCII characters, and casing.
- Calls: no first-party groom symbol; only string operations.
- Does not mutate: [gate info](gate-info.md), [workflow containers](workflow-container.md), fleet ordering, selection, or any browser state.

#### Algorithm

1. Split the question text into source lines in order.
2. For each line, trim surrounding whitespace, remove all leading marker characters, then trim again.
3. Return the first normalized line that is not empty, truncated to the first 140 code points.
4. Return the empty string when every source line is empty or marker-only after normalization.

## Failure Semantics

- Empty input: an empty, whitespace-only, marker-only, or blank multiline string succeeds and returns the empty string.
- Long input: a useful line longer than the cap returns only its first 140 code points; there is no error, ellipsis, or length metadata.
- Markup-like input: HTML- or markdown-like characters travel through unchanged. That is safe because the value is JSON the client renders as text, not markup — no escaping step has to be remembered for it to hold.
- Unsupported input type: values without `splitlines()` are outside the contract and fail with ordinary Python attribute errors; the function coerces nothing.
- Delegated exceptions: it defines no domain-specific exception, partial result, status code, logging path, or fallback.

## Invariants

- first-useful-line: at most one source line contributes to the preview.
- plain-text-boundary: the returned preview is always plain text, never markup, rendered markdown, or a DOM fragment.
- deterministic-preview: the same question string always returns the same preview and does not depend on workflow state, selection, registry membership, browser state, time, filesystem state, or network state.
- consumer-owned-visibility: whether a preview is shown is decided by the client component; this concept only computes the text.
