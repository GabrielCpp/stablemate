---
type: concept
slug: power-mapping
title: Power mapping
---
# Power mapping

Power resolution returns the two optional settings a backend may receive from a power tier or a
backend default. Missing or malformed tables produce an empty mapping rather than an error.

- code: `farrier/farrier/_vendor/stablemate_core/config.py::PowerMapping`
- detail: [home config](../home-config.md)

## Fields

### model
- type: `str | None`
- default: `None`
- required: false
- semantics: optional model name selected for the backend
- verify: json_path(path="$.model", absent=true)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::PowerMapping.model`

### effort
- type: `str | None`
- default: `None`
- required: false
- semantics: optional effort setting selected for the backend
- verify: json_path(path="$.effort", absent=true)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::PowerMapping.effort`
