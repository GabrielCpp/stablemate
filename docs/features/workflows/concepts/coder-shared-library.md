---
type: concept
slug: coder-shared-library
title: Coder shared library
---
# Coder shared library

The Coder flows share this package for the contracts and state transitions that must mean the
same thing in more than one machine. The package exposes only the common blueprint from its
initializer; the individual modules below own the behavior and models they provide.

- code: `workflows/src/workhorse_workflows/coder/shared/__init__.py::__all__`

`blueprint` is the single node-registration namespace. `paths` derives repository, document,
story, operator-gate, and decision paths from explicit workflow inputs and Ostler's configured
roots. `schemas` supplies agent reply and node-result models, while `stubs` supplies dry-run
values with the same result shapes. `commits` and `worktree` provide shared commit-message and
working-tree boundaries.

The shared node modules are grouped by responsibility: `contract` validates service roots;
`story` resolves stories and workspaces, protects code trees during planning, and stamps spec
documents; `story_status` reads and writes story outcomes; `queue` selects and records epic and
story work; `backlog` files and drains deferred fixes; `dev` runs implementation gates; `ci`
handles CI outcomes; `docs` and `okf` build documentation and obligation context; `review` and
`resolution` support review and operator decisions; `escalation` writes human-gate context;
`failure` normalizes gate failures; `qa_support` parses QA run logs; `scenarios` parses QA
scenarios; and `conversation` tracks turn budgets. `roles` resolves prompt envelopes and
replacement bodies.

Each listed module is a separate bounded source contract. The next crawl pass should document
its public functions, classes, and schema members, then connect their results to the flows that
consume them. No shared module imports a Coder flow or the workflow composition root.
