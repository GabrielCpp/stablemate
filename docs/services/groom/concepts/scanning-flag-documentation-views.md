---
type: concept
slug: scanning-flag-documentation-views
title: Scanning flag documentation views
---
# Scanning flag documentation views

`groom/groom/state.py::SCANNING` is one process-local boolean, not three alternative
implementations. The source declares it once with an import-time value of `True`; its comment
states that it remains true while initial or manual container discovery is in flight so the
dashboard can distinguish a not-yet-scanned fleet from a finished empty fleet.

[Dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md#field-value) is the
semantic reference: read it for writers, readers, lifecycle, UI effect, and overlap behavior.
[Groom state module](groom-state-module.md#field-scanning) is the module-inventory reference:
read it to locate `SCANNING` among the state module's public members. [Dashboard state payload]
(../dashboard-state-payload.md#field-discovery-scanning-flag-input) is the projection-input
reference: read it to understand how that module value enters the payload's `scanning` field.

No source-level ranking exists between these documentation views. They describe the same value
at different boundaries; use the view that matches the question rather than treating any field
as a separate flag.

- code: groom/groom/state.py::SCANNING
- rule: use the semantic, module-inventory, or payload-input view according to the boundary being examined; none is a separate implementation or a preferred replacement
- detail: [scanning flag view precedence](scanning-flag-view-precedence.md)
