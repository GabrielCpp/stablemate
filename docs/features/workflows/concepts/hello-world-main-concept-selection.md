---
type: concept
slug: hello-world-main-concept-selection
title: Hello-world main concept selection
---
# Hello-world main concept selection

`workflows/src/workhorse_workflows/hello_world/workflow.py::main` is one callable returned by
`console_script` for the registry entry point. It is not a second workflow implementation or a
separate command dispatcher: the bound registry and Workhorse CLI determine the behavior a
caller reaches.

Use the main-contexts concept to orient between the two views. Use the workflow-composition-root
concept when the question concerns the registry's blueprint, `HelloWorld` binding, or deterministic
dry-run reply. Use the command-selection concept when the question concerns the CLI operation:
`run` executes the workflow, `dot` renders its state graph, and `version` reports the engine
version. These concepts are all current; neither supersedes another because each describes a
different context of the same callable.

- rule: choose the concept by the question about `main`: main contexts for orientation, workflow composition root for registry binding and dry-run behavior, and command selection for the requested Workhorse CLI operation; none supersedes another
