---
type: concept
slug: library-layer-field-selection
title: Library layer field selection
---
# Library layer field selection

`Layer` records two complementary attributes rather than alternative representations. Use `root`
when resolving or inspecting the filesystem location of a library layer. Use `name` when presenting
the layer's provenance in diagnostics, including searched-layer lists. Both fields are required by
the dataclass, and neither supersedes the other.

`set_layers` constructs each layer with its resolved path as `root` and a diagnostic label as
`name`: an overlay is labelled with its resolved path, while the base uses `base-library (base)`.
The fields therefore have no ranking and must remain distinct.

- code: `farrier/farrier/layers.py::Layer`
- rule: use `root` for the library filesystem location and `name` for its diagnostic provenance label; neither field is preferred or deprecated
- detail: [library layer usage rule](library-layer-usage-rule.md)
- detail: [library layer selection](library-layer-selection.md)
