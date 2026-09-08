---
type: concept
slug: coder-entry-point-view-selection
title: Coder entry point view selection
---
# Coder entry point view selection

The Coder distribution exposes one console entry point: `main` passes the Coder registry's
default `Coder` flow to the console-script factory. The entry point therefore has one execution
boundary and one registry, while its documentation separates the different questions a reader
may need to answer about that boundary.

Use [Coder command selection](coder-command-selection.md) to choose the console operation, use
[Coder entry point responsibilities](coder-entry-point-responsibilities.md) to understand the
boundary between the console script and the default flow, and use [Coder workflow composition
root](coder-workflow-composition-root.md) to inspect the registry, named flows, prompt root, and
dry-run replies. These are complementary views of the same `main` symbol; none replaces or is
preferred over another.

- rule: choose the concept by the question being answered: console operation, entry-point boundary, or registry composition; none supersedes the others
