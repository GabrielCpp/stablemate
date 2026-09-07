---
type: concept
slug: pyflow-state-spec
title: pyflow state specification
---
# pyflow state specification

`StateSpec` is the immutable registration record for one workflow state. It keeps the live
method name, callable, and retired aliases that may appear in checkpoints.

- code: `workhorse/workhorse/pyflow/workflow.py::StateSpec`
- tests: [pyflow tests](../../../../workhorse/tests/test_pyflow.py)

## Fields

### field: name
- type: `str`
- required: true
- semantics: current live state name used by graph rendering and checkpoints
- code: `workhorse/workhorse/pyflow/workflow.py::StateSpec`

### field: fn
- type: `Callable[..., Any]`
- required: true
- semantics: state method invoked by the driver
- code: `workhorse/workhorse/pyflow/workflow.py::StateSpec`

### field: aliases
- type: `tuple[str, ...]`
- default: empty tuple
- required: true
- semantics: retired state names accepted when resolving a resume checkpoint
- code: `workhorse/workhorse/pyflow/workflow.py::StateSpec`
