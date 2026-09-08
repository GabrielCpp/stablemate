---
type: concept
slug: research-main-entry-point-views
title: Research main entry point views
---
# Research main entry point views

`main` is the single `workhorse-research` console-script adapter over the Research registry
(`workflows/src/workhorse_workflows/research/workflow.py::main`). The command-selection and
composition-root concepts describe complementary views of that adapter: choose a command by the
caller task, and use the composition-root description to understand the registry and workflow it
enters.

The adapter does not establish a preferred or deprecated view. Its `console_script` construction
wraps `workflow.entry_point(Research)`, while the registry supplies the shared entry point and its
dry-run agent replies.

- rule: choose the command-selection concept for `run`, `dot`, or `version` behavior and the composition-root concept for the registry and Research state-machine behavior; neither supersedes the other
