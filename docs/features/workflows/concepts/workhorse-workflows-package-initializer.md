---
type: concept
slug: workhorse-workflows-package-initializer
title: Workhorse workflows package initializer
---
# Workhorse workflows package initializer

The package root defines no workflow API. Each workflow subpackage owns its own console-script
entry point and its private state-machine implementation; importing `workhorse_workflows` does
not expose those names.

- code: `workflows/src/workhorse_workflows/__init__.py::__all__`

## Fields

### __all__

The explicit export list keeps the package root free of public names.

- type: `list[str]`
- default: `[]`
- verify: count(subject="package-root exports", equals=0)
- required: true
- verify: count(subject="package-root exports", equals=0)
- semantics: importing the package root exposes no public workflow symbols
- verify: count(subject="package-root exports", equals=0)
- code: `workflows/src/workhorse_workflows/__init__.py::__all__`
