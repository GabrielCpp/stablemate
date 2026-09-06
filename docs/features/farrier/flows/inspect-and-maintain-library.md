---
type: flow
slug: inspect-and-maintain-library
title: Inspect and maintain library
---
# Inspect and maintain library

This flow uses the same resolved layer stack for catalog inspection and source lookup, then applies
a repository scaffold without overwriting files the repository already owns.

- start: a configured library layer stack contains the source of a generated adapter
- start: the target repository enables a scaffold
- start: the target repository has an existing file at one scaffold path
- verify: count(subject="active library layers shown before maintenance", equals=2)
- steps:
  - [library](../farrier.md#library)
  - [source](../farrier.md#source)
  - [scaffold](../farrier.md#scaffold)
- end: the operator can identify the winning library layer for the library item
- end: the generated adapter resolves to its editable library source
- end: the scaffold creates absent paths and retains the existing repository file
- verify: count(subject="resolved winning library layer", equals=1)
- verify: count(subject="generated adapter source paths", equals=1)
- verify: created(subject="new scaffold paths")
- verify: unchanged(subject="existing repository file at a scaffold path")
- detail: [library view](../concepts/library-view.md)
- detail: [scaffold operations](../concepts/scaffold-operations.md)
- tests: `farrier/tests/test_library_browse.py::test_show_prints_the_winning_layers_source`
- tests: `farrier/tests/test_source_command.py::test_source_resolves_to_library_file`
- tests: `farrier/tests/test_scaffold_command.py::test_scaffold_never_overwrites_existing_files`
