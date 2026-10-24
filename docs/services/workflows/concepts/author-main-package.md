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

The imported node package holds the main machine's own deterministic work: filling the work list,
documented in [artifact-derived author stage selection](artifact-derived-author-stage-selection.md).
The main machine reaches the rest through its subflows and the shared author nodes. Configuration
loading is documented in [Author workflow configuration](../formats/author-config.md), intake in
[Author main intake](author-main-intake.md), and artifact gates in [Author artifact
gates](author-artifact-gates.md). Story registration, validation, feedback, and record promotion are
documented in the [Author main story processing](author-main-story-processing.md) concept. The package's explicit re-export
surface is recorded in [Author main node exports](author-main-node-exports.md).

- code: `workflows/src/workhorse_workflows/author/main/flow.py` @006e755d5a80
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author` @006e755d5a80
- code: `workflows/src/workhorse_workflows/author/main/__init__.py::__getattr__` @b16a7b4233aa
- code: `workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py::blueprint` @29102aa5dc01
- tests: `workflows/tests/author/test_workflow.py::test_every_flat_stage_is_directly_registered`
- detail: [author main composition layers](author-main-composition-layers.md)
- detail: [author schemas exports](author-schemas-exports.md)

## Methods

### __getattr__
- sig: `__getattr__(name: str) -> Any`
- does: resolves `Author` from `main.flow` when that attribute is requested
- verify: count(subject="lazy Author exports", equals=1)
- raises: raises `AttributeError` for any attribute other than `Author`
- verify: absent(subject="an undeclared main package export")
- returns: the `Author` workflow class for the declared `Author` attribute
- verify: count(subject="resolved Author workflow classes", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/__init__.py::__getattr__` @b16a7b4233aa

### blueprint
- sig: `Blueprint("author") -> Blueprint`
- does: provides the single registration target used by every node module under `main.nodes`
- verify: count(subject="main Author blueprints", equals=1)
- returns: a blueprint named `author`
- verify: json_path(path="$.name", equals="author")
- code: `workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py::blueprint` @29102aa5dc01
