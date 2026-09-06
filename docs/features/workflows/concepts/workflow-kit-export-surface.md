---
type: concept
slug: workflow-kit-export-surface
title: Workflow kit export surface
---
# Workflow kit export surface

`workhorse_workflows.kit` is the workflow-side helper facade. It exposes the Git, GitHub,
workspace, path, JSON, inbox, and external-tool operations implemented by its sibling modules
without making workflow nodes import a particular implementation module. Attribute access resolves
the defining module at access time, so a test that patches that module continues to affect a node
that imports a helper from this facade. The facade itself owns no Git, network, filesystem, or
subprocess behavior.

- code: `workflows/src/workhorse_workflows/kit/__init__.py::__getattr__`

## Methods

### __getattr__

- sig: `__getattr__(name: str) -> object`
- does: resolves a declared facade name from its defining kit submodule on every attribute access
- raises: raises `AttributeError` when the requested name is not in the facade's declared export map
- returns: the current attribute value declared by the selected submodule
- verify: absent(subject="unknown workflow kit facade attribute")
- code: `workflows/src/workhorse_workflows/kit/__init__.py::__getattr__`

### __dir__

- sig: `__dir__() -> list[str]`
- does: exposes exactly the facade's declared export names for introspection
- returns: the sorted facade export names
- verify: count(subject="workflow kit facade export names", equals=49)
- code: `workflows/src/workhorse_workflows/kit/__init__.py::__dir__`
