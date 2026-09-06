---
type: concept
slug: pyflow-names
title: pyflow name indexes
---
# pyflow name indexes

`NameIndex` is shared by workflow states and blueprint nodes. Live names map to targets;
retired aliases map to live names in the same namespace. Registration rejects duplicate
live names, aliases that shadow live names, and aliases claimed by two targets. Copies
used for substitution preserve the namespace and do not mutate the source index.

- code: `workhorse/workhorse/pyflow/names.py::NameIndex`
- tests: [pyflow tests](../../../../workhorse/tests/test_pyflow.py)

## Methods

### NameIndex.register
- sig: `register(name: str, target: T, aliases: tuple[str, ...] = ()) -> None`
- does: records one live target and its retired aliases
- raises: `WorkflowDefinitionError` for any live-name or alias collision
- verify: count(subject="live names after one registration", equals=1)
- code: `workhorse/workhorse/pyflow/names.py::NameIndex.register`

### NameIndex.merge
- sig: `merge(other: NameIndex[T]) -> None`
- does: imports live names and aliases from another index
- raises: `WorkflowDefinitionError` when the namespaces collide
- verify: count(subject="live names after merging one index", equals=1)
- code: `workhorse/workhorse/pyflow/names.py::NameIndex.merge`

### NameIndex.replacing
- sig: `replacing(targets: dict[str, T]) -> NameIndex[T]`
- does: returns a copy with existing live or alias names rebound to replacement targets
- raises: `WorkflowDefinitionError` when a replacement name is unknown
- verify: count(subject="live names in a replacement copy", equals=1)
- code: `workhorse/workhorse/pyflow/names.py::NameIndex.replacing`

### NameIndex.get
- sig: `get(name: str) -> T | None`
- returns: the target for a live name or alias, or `None` when unknown
- verify: json_path(path="$.missing", absent=true)
- code: `workhorse/workhorse/pyflow/names.py::NameIndex.get`

### NameIndex.canonical
- sig: `canonical(name: str) -> str | None`
- returns: the live name selected by a live name or alias, or `None`
- verify: json_path(path="$.canonical", equals="live")
- code: `workhorse/workhorse/pyflow/names.py::NameIndex.canonical`

### NameIndex.aliases_of
- sig: `aliases_of(name: str) -> list[str]`
- returns: aliases pointing at the supplied live name
- verify: count(subject="aliases returned for one live name", equals=1)
- code: `workhorse/workhorse/pyflow/names.py::NameIndex.aliases_of`
