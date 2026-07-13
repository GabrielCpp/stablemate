---
type: format
slug: groom-a11y-finding
title: Groom a11y finding
---
# Groom a11y finding

Groom a11y finding is the structured diagnostic item returned by the
[Groom a11y lint](concepts/groom-a11y-lint.md) engine and rendered by the
[groom-a11y-lint CLI](groom-a11y-lint.md) as a stable line-oriented report. It
identifies one accessibility defect in one parsed HTML source label with enough
detail for a caller to show the file, source line, static rule code, and
human-readable remediation hint.

- file: not an on-disk artifact; this is an in-memory finding item and its stdout string form.
- code: groom/groom/a11y_lint.py::Finding

## Contract

- producer: [Groom a11y lint](concepts/groom-a11y-lint.md) creates findings while scanning one HTML document.
- consumer: [groom-a11y-lint CLI](groom-a11y-lint.md) prints each finding with its string form.
- identity: findings are value objects; two findings with equal field values are equivalent.
- mutability: immutable after construction.
- ordering: callers receive findings in parser node order, with rule checks appended in evaluation order for a single node.
- serialization: converting a finding to text yields `PATH:LINE: CODE MESSAGE` with exactly one colon between `PATH` and `LINE`, one colon-space after `LINE`, and one space between `CODE` and `MESSAGE`.
- clean-state: absence of findings is represented by an empty list, not by a success finding.

## Fields

### field-path

- type: `str`
- default: none
- required: true
- source: caller-supplied source label passed to `lint_html`.
- meaning: names the HTML document or fragment being inspected; commonly a filesystem path, but the format accepts any string label.
- serialization: emitted verbatim before the first colon in the string form.

### field-line

- type: `int`
- default: none
- required: true
- source: parser source line for the element that triggered the rule.
- meaning: one-based line number in the supplied HTML text.
- serialization: emitted as decimal digits after `path:` in the string form.

### field-code

- type: `str`
- default: none
- required: true
- enum: `A11Y001`, `A11Y002`, `A11Y003`, `A11Y004`, `A11Y005`, `A11Y006`, `A11Y007`
- source: static accessibility rule that failed.
- meaning: stable machine-readable rule identifier suitable for filtering, assertions, and regression tests.
- serialization: emitted after `PATH:LINE: ` and before the message in the string form.

### field-message

- type: `str`
- default: none
- required: true
- source: static accessibility rule that failed, with tag/action/role details interpolated when relevant.
- meaning: human-readable explanation of the defect and, when the rule has a mechanical remedy, the expected accessible pattern.
- serialization: emitted verbatim after the rule code and one separating space in the string form.
