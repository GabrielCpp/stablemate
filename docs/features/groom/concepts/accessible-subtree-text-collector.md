---
type: concept
slug: accessible-subtree-text-collector
title: Accessible subtree text collector
---
# Accessible subtree text collector

The accessible subtree text collector is the private helper used by
[Groom a11y lint](groom-a11y-lint.md) to derive the visible or announced text of
one parsed [Groom a11y node](../groom-a11y-node.md) subtree for A11Y006 control
accessible-name checks. It ignores branches hidden with `aria-hidden="true"`,
includes direct text chunks, treats child image `alt` text as subtree text, and
delegates explicit naming-attribute recognition to the
[Explicit accessible name attribute detector](explicit-accessible-name-attribute-detector.md).

- code: groom/groom/a11y_lint.py::_accessible_text
- verify: groom/tests/test_a11y_lint.py::test_button_with_text_ok,
  groom/tests/test_a11y_lint.py::test_icon_only_button_flagged,
  groom/tests/test_a11y_lint.py::test_aria_hidden_text_does_not_name_a_button,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- refs: [Groom a11y node](../groom-a11y-node.md),
  [Explicit accessible name attribute detector](explicit-accessible-name-attribute-detector.md)

## Contract

- sig: `_accessible_text(node: Node) -> str`
- input: one parsed [Groom a11y node](../groom-a11y-node.md), usually a control
  whose accessible name is being tested, with populated `attrs`, `text`, and
  `children` fields.
- output: a stripped string containing the whitespace-joined accessible text
  fragments discovered in the node's subtree, or the empty string when no
  acceptable text is present.
- scope: uses only parser-captured node attributes, direct text chunks, child
  nodes, and child image `alt` attributes; it does not resolve `aria-labelledby`
  references, labels, CSS visibility, generated content, browser accessibility
  trees, or JavaScript-mutated DOM state.
- mutation: none; the supplied node tree is read without changing attributes,
  text, children, or parent pointers.
- recursion: descends through child subtrees except for hidden branches, image
  leaves, and explicitly named child elements handled by the branches below.
- ordering: output fragments preserve this helper's traversal order: the current
  node's direct text list first, then each child in child-list order.
- whitespace: empty fragments are dropped; remaining fragments are joined with a
  single space and the final string is stripped at both ends.
- hidden-branch: when the current node has `aria-hidden="true"`, the helper
  returns the empty string immediately and does not inspect that node's own text
  or descendants.
- image-alt: a direct child `<img>` contributes its `alt` attribute value when the
  attribute exists, contributes the empty string when it is missing or empty, and
  is not recursively inspected for children.
- explicit-child-name: a direct child that has a non-empty `aria-label`,
  `aria-labelledby`, or `title` contributes the child's `aria-label` value when
  present; otherwise it contributes the sentinel string `x` to indicate that the
  child is named even when the exact announced text is not statically available.
- descendant-text: a direct child that is not an image and does not have an
  explicit naming attribute contributes the recursive accessible text of its own
  subtree.
- raises: no accessibility-rule exception is part of the contract for a
  well-formed [Groom a11y node](../groom-a11y-node.md) tree.

## Methods

### method-_accessible_text

- sig: `_accessible_text(node: Node) -> str`
- abstract: false
- raises: no accessibility-rule exception is part of the contract for a
  well-formed [Groom a11y node](../groom-a11y-node.md) tree.
- code: groom/groom/a11y_lint.py::_accessible_text
- verify: groom/tests/test_a11y_lint.py::test_button_with_text_ok,
  groom/tests/test_a11y_lint.py::test_icon_only_button_flagged,
  groom/tests/test_a11y_lint.py::test_aria_hidden_text_does_not_name_a_button,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- does:
  - Returns `""` immediately for a node whose `aria-hidden` attribute is exactly
    `"true"`.
  - Starts the candidate fragment list with the node's direct text chunks.
  - Visits direct children in stored child order.
  - Appends a direct child image's `alt` value without requiring that the value be
    non-empty.
  - For a direct child with any accepted explicit naming attribute, appends that
    child's `aria-label` text when non-empty, otherwise appends `x` as a truthy
    stand-in for `aria-labelledby` or `title` naming.
  - Recursively appends the accessible subtree text of every other direct child.
  - Drops empty fragments, joins the rest with one space, strips the result, and
    returns the resulting string.

## Algorithm

1. If the current node has `aria-hidden="true"`, return the empty string.
2. Copy the current node's direct text chunks into the fragment list.
3. For each direct child in source order, classify the child.
4. If the child is an image, append its `alt` attribute value or the empty string
   when the attribute is absent.
5. Otherwise, if the child has an accepted explicit naming attribute, append the
   child's `aria-label` value when present; when only `aria-labelledby` or `title`
   names the child, append `x` so the parent control still counts as having
   subtree text.
6. Otherwise, recurse into the child and append the returned text.
7. Remove empty fragments, join remaining fragments with single spaces, strip the
   joined text, and return it.

## Consumers

- [Groom a11y lint](groom-a11y-lint.md) uses this collector through the A11Y006
  control accessible-name rule after the direct explicit-name check fails for the
  control under inspection.
- [Groom a11y lint](groom-a11y-lint.md) treats a non-empty collector result as
  enough accessible text for a button, linked anchor, or ARIA widget control to
  pass the static accessible-name check.
