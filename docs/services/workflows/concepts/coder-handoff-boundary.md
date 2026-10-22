---
type: concept
slug: coder-handoff-boundary
title: Coder handoff boundary contract
---
# Coder handoff boundary contract

The Coder registry holds six specialist flows: `genesis`, `dev`, `docs`, `qa`, `fix` and `fix_ci`. The main `Coder` flow hands off to five of them through `self.handoff(SubflowClass, ...)`. `genesis` is entered only by name. The handoff creates a boundary that governs what crosses between the caller and the sub-flow.

## The boundary contract

A sub-flow entered by `handoff()` runs under three constraints that the call site does not show.

**Return value is the only crossing mechanism.** The sub-flow's `Done(...)` value is the only data the caller receives. A parent flow cannot read a node result recorded inside the sub-flow with `self.output(node)`, because the sub-flow records its outputs under its own writer scope. A sub-flow cannot read the parent's node outputs for the same reason. Values cross as arguments on entry or as the `Done` value on exit.

**Prompt paths belong to the sub-flow.** Each flow resolves its prompt envelope to `<flow>/prompts/<role>.md` from the module that defines the flow class. The caller and callee share no prompt file, so each is free to diverge from the other.

**Sub-flows are registered, standalone flows.** Every sub-flow is a registered flow in the coder `Registry`. It runs standalone with `workhorse-coder run <genesis|dev|docs|qa|fix|fix_ci>`. The same nodes and logic execute when the main loop hands off and when an operator enters the flow by name.

## The six sub-flows

- **`Dev`** hands one work item to a dev owner that builds, reviews and fixes it through subagents.
- **`Docs`** folds a finished story into the as-built OKF book and refuses to believe it was.
- **`FixCi`** walks the workspace one repo at a time and gets the epic branch's CI green.
- **`Qa`** plans QA for a story, runs it, and refuses to believe it passed.
- **`Fix`** drains the coder's own backlog, one filed item at a time.
- **`Genesis`** turns a directory into something the author and coder can both stand on. It is entered directly, never handed off to.

## When the boundary matters most

The separate prompt directories are why a role name such as `dev-story` can exist once under `dev/prompts/` and a repo or library body can replace it without touching any other flow's envelope.

- code: `workflows/src/workhorse_workflows/coder/workflow.py::workflow` @a28e84f788c2
- code: `workflows/src/workhorse_workflows/coder/main/flow.py::Coder.dev` @d70dfde3a1bd
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev` @9db388afe7e0
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs` @7ec0db695dc8
- code: `workflows/src/workhorse_workflows/coder/fix_ci/flow.py::FixCi` @a82754789574
- code: `workflows/src/workhorse_workflows/coder/qa/flow.py::Qa` @0a4bcedfcbb5
- code: `workflows/src/workhorse_workflows/coder/genesis/flow.py::Genesis` @94e8836d807e
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix` @3221c750e52d
- detail: [Coder prompt role resolution](coder-prompt-role-resolution.md)
