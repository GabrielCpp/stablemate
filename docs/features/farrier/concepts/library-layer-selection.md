---
type: concept
slug: library-layer-selection
title: Library layer selection
---
# Library layer selection

`Layer` in `farrier/farrier/layers.py::Layer` requires both fields because they describe
different aspects of the same library layer. Resolution helpers join requested paths beneath
`root`, while `searched_layers` renders `name` in provenance and error output. `set_layers`
uses the resolved overlay path as its name and labels the base `base-library (base)`, making a
shadowing overlay visible to the operator.

The fields are complementary rather than competing implementations: select `root` for
filesystem resolution and `name` for diagnostics. Neither field ranks above or replaces the
other.

- code: `farrier/farrier/layers.py::Layer`
- rule: use `root` for filesystem resolution and `name` for provenance diagnostics; neither field is preferred or deprecated
- detail: [library layer usage rule](library-layer-usage-rule.md)
