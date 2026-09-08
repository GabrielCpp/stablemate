---
type: concept
slug: console-script-documentation-selection
title: Console script documentation selection
---
# Console script documentation selection

`console_script` has one implementation. Its factory in
`workhorse/workhorse/cli/__init__.py::console_script` closes over a workflow registry and
returns the callable that invokes `main`; `workhorse/workhorse/__init__.py` re-exports that
same factory as the package-root import. The three concepts grounded in the factory therefore
describe different reader contexts, not competing entry-point implementations.

Use CLI composition and workflow binding to understand parser construction, registry binding,
and command dispatch. Use console script import selection when declaring a workflow
distribution's `[project.scripts]` target. Use console script concept scope when determining
whether those descriptions name distinct factories: it establishes that they do not. There is no
general ranking because each concept answers a different question.

- rule: use CLI composition and workflow binding for factory behavior, console script import selection for a workflow distribution's public script import, and console script concept scope to establish that both name the same factory
