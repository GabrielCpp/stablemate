---
type: concept
slug: template-values
title: Template values
---
# Template values

Template values are the renderer context collected from the manifest's `template:` table. The loader folds the older `vars:` spelling into it.

### method: collect_template_values
- sig: `collect_template_values(config: ConfigLike) -> dict[str, Any]`
- does: return the manifest's `template` values, with the keys of a legacy `vars` table merged underneath and `template` winning a clash
- raises: `SystemExit` naming the key path when either configured value is not a mapping
- code: `farrier/farrier/template_values.py::collect_template_values` @ed69e298525a
- verify: count(subject="merged renderer template values", equals=1)
