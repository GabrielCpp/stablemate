---
type: concept
slug: power-mapping
title: Power mapping
---
# Power mapping

Power resolution returns the three optional settings a backend may receive from a power tier or a
backend default. Missing or malformed tables produce an empty mapping rather than an error.

- code: `farrier/farrier/_vendor/stablemate_core/config.py::PowerMapping` @451a081294d0
- detail: [home config](../formats/home-config.md)

## Fields

### model
- type: `str | None`
- default: `None`
- required: false
- semantics: optional model name selected for the backend
- verify: json_path(path="$.model", absent=true)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::PowerMapping.model` @451a081294d0

### effort
- type: `str | None`
- default: `None`
- required: false
- semantics: optional effort setting selected for the backend
- verify: json_path(path="$.effort", absent=true)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::PowerMapping.effort` @451a081294d0

### timeout_scale
- type: `float | None`
- default: `None`
- required: false
- semantics: multiplier applied to every per-node wall-clock budget resolved at this tier, so a slower model's clock is pinned alongside its name
- verify: json_path(path="$.timeout_scale", equals=2.0)
- semantics: only a strictly positive finite number is honoured
- verify: json_path(path="$.timeout_scale", equals=2.0)
- semantics: every other value reads as unset
- verify: json_path(path="$.timeout_scale", absent=true)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::PowerMapping.timeout_scale` @451a081294d0
