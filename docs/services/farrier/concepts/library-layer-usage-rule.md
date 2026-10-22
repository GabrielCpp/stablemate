---
type: concept
slug: library-layer-usage-rule
title: Library layer usage rule
---
# Library layer usage rule

`Layer.root` and `Layer.name` describe different aspects of one library layer. Resolution
helpers join requested paths beneath `root`; `searched_layers` renders `name` in provenance
and error output. `set_layers` supplies both values, using the resolved overlay path or
`base-library (base)` as the diagnostic name.

- rule: use `root` to resolve library content and `name` to report its provenance; both fields are current, and neither is preferred or deprecated
