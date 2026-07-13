---
type: concept
slug: explicit-accessible-name-attribute-detector
title: Explicit accessible name attribute detector
---
# Explicit accessible name attribute detector

The explicit accessible name attribute detector is the private boolean helper used by
[Groom a11y lint](groom-a11y-lint.md) to decide whether a parsed
[Groom a11y node](../groom-a11y-node.md) carries one of the explicit HTML/ARIA naming
attributes accepted by the static accessibility rules. It supplies the shared pass condition for
form-control labels, image-input names, and control accessible-name checks before those rules fall
back to labels, text content, or image alt text.

- code: groom/groom/a11y_lint.py::_has_name_attr
- verify: groom/tests/test_a11y_lint.py::test_input_with_aria_label_ok,
  groom/tests/test_a11y_lint.py::test_button_with_aria_label_ok

## Contract

- sig: `_has_name_attr(node: Node) -> bool`
- input: one parsed [Groom a11y node](../groom-a11y-node.md) whose `attrs` mapping stores normalized
  attribute names and string values from an HTML element.
- output: `True` when the element has a non-empty explicit accessible-name attribute; otherwise
  `False`.
- accepted-attributes:
  - `aria-label`: direct accessible-name text.
  - `aria-labelledby`: one or more referenced element ids that name the element.
  - `title`: tooltip/title text accepted by this static linter as an explicit name fallback.
- empty-values: a missing attribute, an empty string, or a string containing only whitespace is
  treated as absent.
- ignored-input: tag name, parent/child structure, descendant text, `alt`, `value`, `<label>`
  associations, placeholders, role, and focusability do not affect this helper's result.
- mutation: none; the node and its attribute mapping are only read.
- raises: no accessibility-rule exception is part of the contract for a well-formed node record.

## Algorithm

1. Read the node's attribute mapping.
2. Look up `aria-label`, `aria-labelledby`, and `title`, treating each missing key as an empty
   string.
3. Trim whitespace from each retrieved value.
4. Return `True` as soon as any trimmed value is non-empty; otherwise return `False`.

## Consumers

- [Groom a11y lint](groom-a11y-lint.md) uses this detector in the A11Y002 form-control label rule
  so explicit naming attributes satisfy the label requirement before associated or wrapping labels
  are considered.
- [Groom a11y lint](groom-a11y-lint.md) uses this detector in the A11Y003 image-input rule so an
  image submit control can be named by an explicit naming attribute when `alt` text is absent.
- [Groom a11y lint](groom-a11y-lint.md) uses this detector in the A11Y006 control accessible-name
  rule as the explicit-name branch before descendant accessible text is computed.
