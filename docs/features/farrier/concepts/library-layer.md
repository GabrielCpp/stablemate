---
type: concept
slug: library-layer
title: Library layer
---
# Library layer

`Layer` names one library root in the ordered resolution stack. `root` identifies the filesystem
tree and `name` is the human-readable provenance label used in diagnostics; the overlay uses its
resolved path as its name and the base uses `base-library (base)`. The stack is ordered from
highest to lowest precedence, so the first matching layer wins.

- code: `farrier/farrier/layers.py::Layer`
- tests: `farrier/tests/test_config_resolution.py::test_overlay_shadows_base`
- detail: [library layer attribute selection](library-layer-attribute-selection.md)
- detail: [library layer usage rule](library-layer-usage-rule.md)
- detail: [library layer selection](library-layer-selection.md)
- detail: [library directory](library-directory.md#the-layer-stack)

## Fields

### field: root
- type: `Path`
- required: true
- verify: json_path(path="$.root", matches="^/.+")
- semantics: filesystem root of this library layer
- verify: json_path(path="$.root", matches=".+")
- code: `farrier/farrier/layers.py::Layer`
- detail: [library layer field selection](library-layer-field-selection.md)

### field: name
- type: `str`
- required: true
- verify: json_path(path="$.name", matches=".+")
- semantics: provenance label shown when a source is selected or an error lists searched layers
- code: `farrier/farrier/layers.py::Layer`
- detail: [library layer field selection](library-layer-field-selection.md)
