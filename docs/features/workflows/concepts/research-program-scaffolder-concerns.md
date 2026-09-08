---
type: concept
slug: research-program-scaffolder-concerns
title: Research program scaffolder concerns
---
# Research program scaffolder concerns

`new_program.main` is one operator-facing scaffold command with two complementary documented
concerns. The [research program scaffolder](research-program-scaffolder.md) describes the command's
inputs, generated files, overwrite protection, and optional active-program pointer. [Research program
manifest field selection](research-program-manifest-field-selection.md) describes how that same command
maps its inputs into `program.yml`: `code_root` is always written, path and branch fields are written
only for explicit overrides, and the envelope plus containment fields declare measurement constraints.

Neither concern is an alternative implementation or a preferred replacement for the other. Read the
scaffolder node to operate the command and the field-selection node to choose and interpret manifest
settings; both are needed to understand the single `main` entry point.

- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- rule: use the scaffolder concept for the command lifecycle and the manifest field-selection concept for `program.yml` values; neither supersedes the other
- detail: [research program scaffolder documentation scope](research-program-scaffolder-documentation-scope.md)
