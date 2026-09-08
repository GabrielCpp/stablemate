---
type: concept
slug: coder-handoff-boundary
title: Coder handoff boundary contract
---
# Coder handoff boundary contract

The Coder workflow sequences seven specialized sub-flows — `dev`, `docs`, `fix_ci`, `qa`, and `review` as handoff targets, plus `genesis` and `fix` as standalone entry points — each reachable through `Engine.handoff(SubflowClass, ...)`. The handoff mechanism creates an intentional boundary that governs state isolation and resource management.

## The boundary contract

A sub-flow entered via `handoff()` operates under four constraints that are invisible from the callsite but essential to understand:

**Return value is the only crossing mechanism.** The sub-flow's `Done(...)` value is the only data structure the caller receives. A parent flow cannot access any node results produced within the sub-flow via `self.output(node)` — that call is scoped to the sub-flow's own nodes and cannot see the parent's work. Conversely, a sub-flow's `self.output()` cannot reach the parent's nodes. Values crossing the boundary must be explicitly passed as arguments on entry or returned in the `Done` value on exit.

**Prompt paths resolve upward.** Each sub-flow's prompts are written as paths from the parent `coder/` package root (`dev/prompts/implement-plan.md`, `docs/prompts/document-story.md`, `qa/prompts/qa-story.md`, etc.), not as paths from the sub-package directory. This is because `Engine.handoff` subscopes only the run writer, not the environment, so the package resolution context remains the parent's.

**Each sub-flow has its own transition budget.** `Engine.handoff` drives the sub-flow through a fresh `drive()` call with its own state-transition budget. An implementation loop that exhausts its budget inside one sub-flow (e.g., a per-repo poll in `fix_ci` or a QA repair loop in `qa`) does not starve the parent flow's budget. The per-sub-flow budgets are independent: `MAX_PLAN_BLOCKS`, `MAX_REVIEW_BLOCKS`, `MAX_QA_BLOCKS` each cap their own sub-flow.

**Sub-flows are registered, standalone flows.** The seven sub-flows are not just internal orchestration helpers — each is a registered flow in the coder `Registry` and can be run standalone with `workhorse-coder run <dev|docs|fix_ci|qa|review>` or `workhorse-coder run <genesis|fix>`. This means the same nodes and logic execute both when handed off to from the main loop and when entered directly by name.

## The seven sub-flows

- **`Dev`** — plan a story and implement it, one service layer at a time (`dev/__init__.py`).
- **`Docs`** — fold a finished story into the as-built OKF book, and refuse to believe it was (`docs/__init__.py`).
- **`FixCi`** — walk the workspace one repo at a time and get the epic branch's CI green (`fix_ci/__init__.py`).
- **`Qa`** — plan QA for a story, run it, and refuse to believe it passed (`qa/__init__.py`).
- **`Review`** — review a story's implementation and drive the findings to settled (`review/__init__.py`).
- **`Genesis`** — bootstrap the preconditions the main loop assumes (`genesis/__init__.py`); entered directly, never handed off to.
- **`Fix`** — drain the coder's own backlog, one filed item at a time (`fix/__init__.py`); entered directly, never handed off to.

## When the boundary matters most

The transition-budget independence of `fix_ci` is a canonical use case. A per-repo CI loop inside that sub-flow might retry a flaky check three times; if that exhausts `fix_ci`'s budget but the parent `main` flow still has budget remaining, the retry loop waits at an operator gate without starving the parent's ability to plan or review. This is why the contract mandates a fresh `drive()` call rather than reusing the parent's budget pool.

The prompt-path resolution is why each sub-flow packages its own prompts directory. The same `implement-plan.md` name exists under `main/prompts/`, `dev/prompts/`, and `fix/prompts/`, each free to diverge — the caller and callee are not coupled through shared prompt files, even though they may do similar work.

- code: `workflows/src/workhorse_workflows/coder/__init__.py`
- code: `workflows/src/workhorse_workflows/coder/dev/__init__.py`
- code: `workflows/src/workhorse_workflows/coder/docs/__init__.py`
- code: `workflows/src/workhorse_workflows/coder/fix_ci/__init__.py`
- code: `workflows/src/workhorse_workflows/coder/qa/__init__.py`
- code: `workflows/src/workhorse_workflows/coder/review/__init__.py`
- code: `workflows/src/workhorse_workflows/coder/genesis/__init__.py`
- code: `workflows/src/workhorse_workflows/coder/fix/__init__.py`

