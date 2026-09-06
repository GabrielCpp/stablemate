---
type: concept
slug: author-main-package
title: Author main package
---
# Author main package

The `main` package is the entry-point flow's private composition boundary. Importing its `nodes`
package registers the deterministic Author nodes on one `Blueprint("author")`; the package itself
does not register another flow name. The parent registry imports `Author` lazily through this package,
so importing a node does not eagerly import the composition flow.

- code: `workflows/src/workhorse_workflows/author/main/__init__.py::__getattr__`
- code: `workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py::blueprint`
- tests: `workflows/tests/author/test_workflow.py::test_every_flat_stage_is_directly_registered`

## Methods

### __getattr__
- sig: `__getattr__(name: str) -> Any`
- does: resolves `Author` from `main.flow` when that attribute is requested
- verify: count(subject="lazy Author exports", equals=1)
- raises: raises `AttributeError` for any attribute other than `Author`
- verify: absent(subject="an undeclared main package export")
- returns: the `Author` workflow class for the declared `Author` attribute
- verify: count(subject="resolved Author workflow classes", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/__init__.py::__getattr__`

### blueprint
- sig: `Blueprint("author") -> Blueprint`
- does: provides the single registration target used by every node module under `main.nodes`
- verify: count(subject="main Author blueprints", equals=1)
- returns: a blueprint named `author`
- verify: json_path(path="$.name", equals="author")
- code: `workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py::blueprint`
