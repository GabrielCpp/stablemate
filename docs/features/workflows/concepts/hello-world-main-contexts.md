---
type: concept
slug: hello-world-main-contexts
title: Hello-world main contexts
---
# Hello-world main contexts

`main` is the console-script callable created from the hello-world registry's entry point. It
does not select between two implementations: the workflow composition-root concept describes
what the bound registry contains, while the command-selection concept describes which Workhorse
operation to request from that same callable.

Use [Hello-world workflow composition root](hello-world-workflow-composition-root.md) when
understanding or changing the registry binding, its blueprint, and its deterministic dry-run
agent reply. Use [Hello-world command selection](workhorse-hello-world-command-selection.md)
when choosing `run`, `dot`, or `version` at the console. Both views are current because they
answer different questions about `main`; neither replaces the other.

- code: `workflows/src/workhorse_workflows/hello_world/workflow.py::main`
- rule: use the composition-root concept for the registry and dry-run binding, and the command-selection concept for choosing a console operation; neither concept supersedes the other
- detail: [Hello-world main concept selection](hello-world-main-concept-selection.md)
