---
type: environment
slug: depot-stack
title: The depot stack
---
# The depot stack

- selector: the `dev` stack, and there is no other. `Pulumi.dev.yaml` beside the program is the
  whole of its configuration, and `make -C pulumi plan` selects it.
- backing:
  - state: a local file backend at `pulumi/.pulumi-state`, created by the first `stack select`
    and ignored by git. No `pulumi login` runs anywhere in this repository.
  - project: `depot-example` in `us-central1`, which does not exist. The plan names it; nothing
    reaches it.
- local-only: true
- code: pulumi/Pulumi.yaml
- code: pulumi/main.go
- code: pulumi/Makefile
- code: pulumi/go.mod
- code: pulumi/go.sum
- code: pulumi/.gitignore

Nothing in this stack runs, and that is the shape rather than an omission. There is no container,
no port and no process to reach: the program declares resources, and the only thing it produces is
a plan. So every claim this book makes is a claim about that plan, and the way to observe one is to
read the JSON `pulumi preview --json` writes — not to call an endpoint that does not exist.

The backend and the passphrase are stated in `pulumi/Makefile` rather than left to whoever runs it,
so a preview taken by a person and a preview taken by a check are the same preview. Neither is a
secret: the state they protect is a plan for a project nobody owns, and the one configured value
that would be (`depot:deployToken`) is a fixed placeholder.

A preview needs no credential and reaches no Google API, but it does need two things already on the
machine: the Go module cache for the provider SDK, and the `gcp` resource plugin. Both are warmed
once, and both are documented with the fixture rather than here.
