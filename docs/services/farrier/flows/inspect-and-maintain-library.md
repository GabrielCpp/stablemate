---
type: flow
slug: inspect-and-maintain-library
title: Inspect and maintain library
---
# Inspect and maintain library

This flow uses the same resolved layer stack for catalog inspection and source lookup, then applies
a repository scaffold.

- start: a configured library layer stack contains the source of a generated adapter
- start: the target repository enables a scaffold
- steps:
  - [list the layer stack](../farrier-invocations.md#list-the-layer-stack)
  - [resolve a generated file](../farrier-invocations.md#resolve-a-generated-file)
  - [apply a scaffold](../farrier-invocations.md#apply-a-scaffold)
  - [eject a skill](../farrier-invocations.md#eject-a-skill)
- end: the operator can identify the winning library layer for the library item (commands: [library](../farrier-commands-init.md#library), [source](../farrier-commands-init.md#source), [scaffold](../farrier-commands-init.md#scaffold), [eject](../farrier-commands-init.md#eject))
- end: the generated adapter resolves to its editable library source
- end: the scaffold creates the paths the repository lacks
- end: an ejected skill's generated folder carries no farrier provenance
- verify: created(subject="c207/api/.gitignore")
- fixture: overlay-over-base dir=c205
- fixture: generated-demo-skill dir=c206
- fixture: scaffold-library dir=c207
- fixture: own-skill-repo dir=c905
- detail: [library view](../concepts/library-view.md)
- detail: [scaffold operations](../concepts/scaffold-operations.md)
- tests: `farrier/tests/test_library_browse.py::test_show_prints_the_winning_layers_source`
- tests: `farrier/tests/test_source_command.py::test_source_resolves_to_library_file`
- tests: `farrier/tests/test_scaffold_command.py::test_scaffold_never_overwrites_existing_files`
