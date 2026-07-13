---
type: concept
slug: widget-focusability-detector
title: Widget focusability detector
---
# Widget focusability detector

The widget focusability detector is the private boolean helper used by
[Groom a11y lint](groom-a11y-lint.md) to decide whether a parsed
[Groom a11y node](../groom-a11y-node.md) with an ARIA widget role can receive keyboard focus for
the A11Y005 widget-focusability rule. It accepts explicit tab stops, native interactive HTML controls,
and content-editable elements; it rejects removed tab stops, non-interactive elements, and bare anchors
without `href`.

- code: groom/groom/a11y_lint.py::_is_focusable
- verify: groom/tests/test_a11y_lint.py::test_role_button_without_tabindex_flagged,
  groom/tests/test_a11y_lint.py::test_role_button_with_tabindex_ok,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- refs: [Groom a11y lint](groom-a11y-lint.md), [Groom a11y node](../groom-a11y-node.md)

## Contract

- sig: `_is_focusable(node: Node) -> bool`
- input: one parsed [Groom a11y node](../groom-a11y-node.md), normally an element whose `role`
  attribute is one of the widget roles checked by A11Y005.
- output: `True` when the element is keyboard-focusable by the static rules available from markup;
  otherwise `False`.
- true-when:
  - The element has a `tabindex` attribute whose stripped value is not `-1`.
  - The element tag is `button`, `input`, `select`, `textarea`, or `summary`.
  - The element tag is `a` and it has an `href` attribute.
  - The element has a `contenteditable` attribute.
- false-when:
  - The element has `tabindex="-1"`, even when it is natively interactive or content-editable.
  - The element tag is `a` without an `href` attribute.
  - The element is not natively interactive and lacks both an accepted `tabindex` and `contenteditable`.
- tabindex-rule: the presence of `tabindex` takes precedence over every other focusability source;
  `0`, positive values, empty strings, and non-`-1` values are accepted, while stripped `-1` is
  rejected.
- native-rule: native interactive status is determined by the owning module's recognized native-tag
  set; anchors are a special case because only linked anchors are focusable controls.
- contenteditable-rule: the attribute's presence is enough; its value is not interpreted.
- scope: the detector only evaluates the parsed tag name and attributes; it does not compute browser
  focus order, disabled state, CSS visibility, inert ancestors, shadow DOM, or JavaScript-mutated DOM.
- mutation: none; the node's attributes, text, children, and parent pointer are read without changes.
- raises: no accessibility-rule exception is part of the contract for a well-formed
  [Groom a11y node](../groom-a11y-node.md).

## Methods

### method-_is_focusable

- sig: `_is_focusable(node: Node) -> bool`
- abstract: false
- raises: no accessibility-rule exception is part of the contract for a well-formed
  [Groom a11y node](../groom-a11y-node.md).
- code: groom/groom/a11y_lint.py::_is_focusable
- verify: groom/tests/test_a11y_lint.py::test_role_button_without_tabindex_flagged,
  groom/tests/test_a11y_lint.py::test_role_button_with_tabindex_ok,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- does:
  - Reads the node's parsed attribute map.
  - When `tabindex` exists, returns whether its stripped value is anything other than `-1`.
  - When no `tabindex` exists and the tag is natively interactive, returns `True` for every native
    tag except bare anchors, and returns `True` for anchors only when `href` exists.
  - When no `tabindex` exists and the tag is not an accepted native focus source, returns whether
    the `contenteditable` attribute exists.

## Algorithm

1. Inspect the node attributes for `tabindex`.
2. If `tabindex` is present, strip its value and return `False` only for `-1`; return `True` for all
   other present values.
3. If no `tabindex` is present and the tag is in the native interactive tag set, return `True` unless
   the tag is `a` without `href`.
4. If neither branch applies, return `True` when `contenteditable` is present and `False` otherwise.

## Consumers

- [Groom a11y lint](groom-a11y-lint.md) uses this detector only for A11Y005, after confirming the
  node's `role` value is one of the recognized ARIA widget roles.
- A `False` result causes A11Y005 to emit a [Groom a11y finding](../groom-a11y-finding.md) with the
  message `role=ROLE on <TAG> is not keyboard focusable (add tabindex=0)`.
