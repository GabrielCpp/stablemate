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

The imported node package is the deterministic work surface for the main machine: configuration
loading is documented in [Author workflow configuration](../author-config.md), intake in [Author
main intake](author-main-intake.md), epic selection in [Author main epic selection](author-main-epic-selection.md),
artifact gates in [Author artifact gates](author-artifact-gates.md), and stage selection in
[artifact-derived author stage selection](artifact-derived-author-stage-selection.md). Story
registration, selection, validation, feedback, and backlog cleanup are documented in the [Author
main story processing](author-main-story-processing.md) concept. The package's explicit re-export
surface is recorded in [Author main node exports](author-main-node-exports.md).

- code: `workflows/src/workhorse_workflows/author/main/flow.py`
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author`
- code: `workflows/src/workhorse_workflows/author/main/__init__.py::__getattr__`
- code: `workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py::blueprint`
- code: `workflows/tests/author/test_workflow.py::test_every_flat_stage_is_directly_registered`
- code: `workflows/tests/author/test_workflow.py::test_the_labels_name_the_story_and_the_epic.capture`
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
- code: `workflows/src/workhorse_workflows/author/main/__init__.py::__getattr__`

### blueprint
- sig: `Blueprint("author") -> Blueprint`
- does: provides the single registration target used by every node module under `main.nodes`
- verify: count(subject="main Author blueprints", equals=1)
- returns: a blueprint named `author`
- verify: json_path(path="$.name", equals="author")
- code: `workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py::blueprint`
