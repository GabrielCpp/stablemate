---
type: concept
slug: main-dispatcher-concept-scope
title: Main dispatcher concept scope
---
# Main dispatcher concept scope

`workhorse/workhorse/__init__.py` re-exports `main` from `workhorse.cli`, so
`workhorse.main` and `workhorse.cli.main` are the same dispatcher rather than alternate
implementations. The dispatcher in `workhorse/workhorse/cli/__init__.py::main` builds the
workflow parser, binds the supplied registry and workflow name, and runs the selected command.

Read [Main import selection](main-import-selection.md) when choosing the public import path for
a direct caller. Read [CLI composition and workflow binding](cli-composition.md) when learning
how a workflow binds that dispatcher into a console script and how the dispatcher processes
arguments. Neither concept supersedes the other: their scopes are complementary, and no source
evidence establishes a general ranking between them.

- rule: use Main import selection for a direct caller's import-path choice; use CLI composition and workflow binding for workflow console-script wiring and dispatcher behavior
