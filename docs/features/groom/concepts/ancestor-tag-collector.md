---
type: concept
slug: ancestor-tag-collector
title: Ancestor tag collector
---
# Ancestor tag collector

The ancestor tag collector is the private helper used by [Groom a11y lint](groom-a11y-lint.md)
to decide whether a parsed [Groom a11y node](../groom-a11y-node.md) is wrapped by a `<label>`
ancestor for the A11Y002 form-control-label rule. It returns the set of tag names on the node's
parent chain, excluding the node itself, so the lint rule can treat `"label" in ancestors` as the
wrapped-label pass condition.

- code: groom/groom/a11y_lint.py::_ancestor_tags
- verify: groom/tests/test_a11y_lint.py::test_input_wrapped_in_label_ok,
  groom/tests/test_a11y_lint.py::test_input_with_only_placeholder_flagged,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- refs: [Groom a11y lint](groom-a11y-lint.md), [Groom a11y node](../groom-a11y-node.md)

## Contract

- sig: `_ancestor_tags(node: Node) -> set[str]`
- input: one parsed [Groom a11y node](../groom-a11y-node.md) whose ancestors may affect a lint rule.
- output: a `set[str]` containing each parsed tag name found by following the node's `parent` pointer
  until the root sentinel has been included and the chain ends.
- includes: direct parent, higher ancestors, and the parser root sentinel tag when the node is attached
  to the tree.
- excludes: the supplied node's own tag, child tags, descendant tags, sibling tags, attribute names,
  text content, and duplicate ancestor tag occurrences.
- empty-result: returns an empty set when the supplied node has no parent.
- ordering: none; callers must treat the result as membership data, not as a path sequence.
- mutation: none; the node tree is read without changing parent pointers, children, attributes, text,
  or source-line metadata.
- scope: the helper only reports parsed tag names already present in the in-memory node tree; it does
  not validate HTML ancestry, normalize namespaces, inspect browser DOM repair behavior, or resolve
  label associations by id.

## Methods

### method-_ancestor_tags

- sig: `_ancestor_tags(node: Node) -> set[str]`
- abstract: false
- raises: no accessibility-rule exception is part of the contract for a well-formed
  [Groom a11y node](../groom-a11y-node.md) tree.
- code: groom/groom/a11y_lint.py::_ancestor_tags
- verify: groom/tests/test_a11y_lint.py::test_input_wrapped_in_label_ok,
  groom/tests/test_a11y_lint.py::test_input_with_only_placeholder_flagged,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- does:
  - Starts with the supplied node's parent rather than the node itself.
  - Adds each visited ancestor's tag name to the result set.
  - Advances through each ancestor's parent pointer until no parent remains.
  - Returns the accumulated set of ancestor tag names.

## Algorithm

1. Create an empty result set.
2. Set the current node pointer to the supplied node's parent.
3. While the current pointer is not empty, add the current tag name to the result set and move the
   pointer to the current node's parent.
4. Return the result set.

## Consumers

- [Groom a11y lint](groom-a11y-lint.md) uses this helper only in the A11Y002 form-control-label rule,
  after checking explicit accessible-name attributes and `<label for="...">` associations.
- A result containing `label` makes a non-hidden `<input>`, `<textarea>`, or `<select>` pass A11Y002
  as a label-wrapped form control.
- A result without `label` leaves the form control unlabeled unless another accepted label source has
  already been found.
