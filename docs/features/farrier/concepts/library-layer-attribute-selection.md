---
type: concept
slug: library-layer-attribute-selection
title: Library layer attribute selection
---
# Library layer attribute selection

`Layer` in `farrier/farrier/layers.py::Layer` deliberately carries both attributes: `root`
is the filesystem location used to locate content, while `name` identifies that location in
provenance banners and error messages. An overlay uses its resolved path as its label; the base
uses `base-library (base)`. The label makes an overlay shadowing a base file visible to the
operator, so replacing either attribute with the other would lose required information.

Neither attribute is an implementation alternative or has a ranking. Consumers resolving files
use `root`; consumers reporting the selected or searched layer use `name`.

- code: `farrier/farrier/layers.py::Layer`
- rule: use `root` for filesystem resolution and `name` for provenance diagnostics; neither attribute is preferred or deprecated
- detail: [library layer usage rule](library-layer-usage-rule.md)
- detail: [library layer selection](library-layer-selection.md)
