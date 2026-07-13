---
type: concept
slug: control-accessible-name-detector
title: Control accessible name detector
---
# Control accessible name detector

The control accessible name detector is the private boolean helper used by
[Groom a11y lint](groom-a11y-lint.md) to decide whether a parsed
[Groom a11y node](../groom-a11y-node.md) has any accessible name accepted by
the A11Y006 button, linked-anchor, and ARIA-widget branch. It composes the
[Explicit accessible name attribute detector](explicit-accessible-name-attribute-detector.md)
with the [Accessible subtree text collector](accessible-subtree-text-collector.md): a control is named
when it has a non-empty explicit naming attribute or when its accessible subtree text is non-empty.

- code: groom/groom/a11y_lint.py::_has_accessible_name
- verify: groom/tests/test_a11y_lint.py::test_icon_only_button_flagged,
  groom/tests/test_a11y_lint.py::test_button_with_text_ok,
  groom/tests/test_a11y_lint.py::test_button_with_aria_label_ok,
  groom/tests/test_a11y_lint.py::test_aria_hidden_text_does_not_name_a_button,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- refs: [Groom a11y node](../groom-a11y-node.md),
  [Explicit accessible name attribute detector](explicit-accessible-name-attribute-detector.md),
  [Accessible subtree text collector](accessible-subtree-text-collector.md)

## Contract

- sig: `_has_accessible_name(node: Node) -> bool`
- input: one parsed [Groom a11y node](../groom-a11y-node.md), usually a `<button>`, linked `<a>`,
  or ARIA widget-role element whose A11Y006 accessible-name status is being checked.
- output: `True` when the node has a non-empty explicit accessible-name attribute or non-empty
  accessible subtree text; otherwise `False`.
- explicit-name: non-empty `aria-label`, `aria-labelledby`, or `title` attributes satisfy the
  contract before subtree text is considered.
- subtree-name: when the node lacks an explicit name, any non-empty text returned by the
  [Accessible subtree text collector](accessible-subtree-text-collector.md) satisfies the contract.
- empty-values: missing attributes, whitespace-only explicit attributes, and an empty accessible-text
  result do not name the control.
- scope: the detector only evaluates data already captured on the parsed node tree; it does not
  resolve label associations, `aria-labelledby` target text, CSS visibility, generated content,
  browser accessibility trees, or JavaScript-mutated DOM state.
- mutation: none; the node and its descendants are read without changing attributes, text, children,
  or parent pointers.
- raises: no accessibility-rule exception is part of the contract for a well-formed
  [Groom a11y node](../groom-a11y-node.md) tree.

## Methods

### method-_has_accessible_name

- sig: `_has_accessible_name(node: Node) -> bool`
- abstract: false
- raises: no accessibility-rule exception is part of the contract for a well-formed
  [Groom a11y node](../groom-a11y-node.md) tree.
- code: groom/groom/a11y_lint.py::_has_accessible_name
- verify: groom/tests/test_a11y_lint.py::test_icon_only_button_flagged,
  groom/tests/test_a11y_lint.py::test_button_with_text_ok,
  groom/tests/test_a11y_lint.py::test_button_with_aria_label_ok,
  groom/tests/test_a11y_lint.py::test_aria_hidden_text_does_not_name_a_button,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- does:
  - Returns `True` immediately when the node has a non-empty explicit accessible-name attribute.
  - Otherwise computes the node's accessible subtree text.
  - Returns `True` when that subtree-text result is non-empty.
  - Returns `False` when both the explicit-name check and subtree-text check are empty.

## Algorithm

1. Evaluate the node with the
   [Explicit accessible name attribute detector](explicit-accessible-name-attribute-detector.md).
2. If that explicit-name result is `True`, return `True` without requiring text content.
3. Otherwise, compute accessible subtree text with the
   [Accessible subtree text collector](accessible-subtree-text-collector.md).
4. Return `True` when the subtree text is non-empty; return `False` when it is empty.

## Consumers

- [Groom a11y lint](groom-a11y-lint.md) uses this detector for the A11Y006 control accessible-name
  rule on `<button>`, linked `<a>` controls, and ARIA widget-role controls.
- [Groom a11y lint](groom-a11y-lint.md) does not use this detector for submit, reset, or button
  inputs; those input types are evaluated directly by their `value` or explicit accessible-name
  attributes.
