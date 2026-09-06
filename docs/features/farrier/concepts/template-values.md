---
type: concept
slug: template-values
title: Template values
---
# Template values

Template values are the renderer context collected from the two accepted configuration spellings.

### method: collect_template_values
- sig: `collect_template_values(config: dict[str, Any]) -> dict[str, Any]`
- does: merge `vars` first and legacy `template` second, with later keys winning
- raises: `SystemExit` when either configured value is not a mapping
- code: `farrier/farrier/template_values.py::collect_template_values`
- verify: count(subject="merged renderer template values", equals=1)
