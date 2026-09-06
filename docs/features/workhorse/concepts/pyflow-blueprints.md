---
type: concept
slug: pyflow-blueprints
title: pyflow blueprints and node registration
---
# pyflow blueprints and node registration

`Blueprint` collects plain logger-first functions into a named node index. Registration
stamps the function with its `NodeSpec`; the registry later merges those indexes and the
engine resolves calls by the stamped live name. Aliases preserve reads of old artifact
directories, while dry-run stubs replace bodies without changing the registered contract.

- code: `workhorse/workhorse/pyflow/blueprint.py::Blueprint`
- tests: [pyflow tests](../../../../workhorse/tests/test_pyflow.py)

## Fields

### field: NodeSpec
- type: frozen dataclass containing `fn`, `name`, `blueprint`, `aliases`, `retries`, `returns`, `dir_names`, and optional `stub`
- semantics: registration metadata used for node lookup, retrying, output revival, aliases, and dry-run substitution
- verify: keys_unchanged(subject="NodeSpec metadata across dry-run substitution")
- code: `workhorse/workhorse/pyflow/blueprint.py::NodeSpec`

## Methods

### Blueprint.__init__
- sig: `Blueprint(name: str)`
- does: creates a named blueprint with an empty node index
- returns: the blueprint instance
- verify: count(subject="node names in a newly created blueprint", equals=0)
- code: `workhorse/workhorse/pyflow/blueprint.py::Blueprint.__init__`

### Blueprint.node
- sig: `node(fn=None, *, aliases=(), retries=0, stub=None)`
- does: registers a function under its Python function name
- does: records aliases as retired names that resolve to the live node
- does: records retry count and optional dry-run stub
- raises: `WorkflowDefinitionError` when a live name or alias collides in the shared index
- returns: the decorated function, preserving direct calls
- verify: count(subject="live nodes after decorating one function", equals=1)
- code: `workhorse/workhorse/pyflow/blueprint.py::Blueprint.node`

### Blueprint.node_names
- sig: `node_names() -> list[str]`
- returns: live node names only, excluding aliases
- verify: count(subject="live names returned after registering a node with an alias", equals=1)
- code: `workhorse/workhorse/pyflow/blueprint.py::Blueprint.node_names`

### node_spec
- sig: `node_spec(fn) -> NodeSpec`
- raises: `UnknownNodeError` when the function was not decorated by a blueprint
- verify: exit_status(code=1)
- returns: metadata stamped on a registered node function
- code: `workhorse/workhorse/pyflow/blueprint.py::node_spec`
