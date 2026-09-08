---
type: concept
slug: console-script-concept-scope
title: Console script concept scope
---
# Console script concept scope

`workhorse.cli.console_script` is one factory, not a pair of alternative implementations. Its
source constructs an entry callable that closes over the supplied workflow registry and passes
that registry and its name to `main`; `workhorse.console_script` re-exports that same factory
from the package root.

CLI composition and workflow binding describes the factory's command construction and dispatch
contract. Console script import selection describes which import a workflow distribution places
in its `[project.scripts]` target. Neither concept supersedes the other: choose the former to
understand CLI behavior and the latter to choose the public import surface.

- code: `workhorse/workhorse/cli/__init__.py::console_script`
- rule: use CLI composition and workflow binding for factory behavior; use console script import selection for the public `[project.scripts]` import, because both describe the same `console_script` factory from different contexts
- detail: [Console script documentation selection](console-script-documentation-selection.md)
