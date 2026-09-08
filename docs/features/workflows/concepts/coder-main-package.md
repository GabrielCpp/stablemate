---
type: concept
slug: coder-main-package
title: Coder main package
---
# Coder main package

The `main` package is the entry-point flow's composition boundary. It sequences eight specialist
sub-flows (dev, docs, fix, fix-ci, qa, review, and genesis) and retains the queue and transition
decisions here. It is the default flow entered by a bare `workhorse-coder run`, and composes epic
and story mode queue processing with mode-specific sub-flow handoffs.

The machine returns to queue processing after each sub-flow, so deterministic stages fold forward
into the queue state that branches on them, while expensive or irreversible work (agent turns,
operator gates, PR operations) starts a new resumable state. This staging strategy ensures that
kills or pauses in any sub-flow do not re-run prior completed stages.

The package's entry-point composition is implemented by the `Coder` workflow class, which is
the default flow entered by a bare `workhorse-coder run`. The queue and transition logic is
documented in related concepts including [coder main PR boundary](coder-main-pr-boundary.md),
[coder entry-point view selection](coder-entry-point-view-selection.md), and [coder command
selection](coder-command-selection.md).

The entry point is deliberately **not** registered in `add_flows` — it is reached as the default
at runtime, and naming it twice would give one machine two registry entries. The `main` package
sits at `coder/main/`, housing the machine (`flow.py`) and the nodes only this graph calls
(`nodes/`). The wider registry composition — the blueprint, the flow table, the dry-run stubs,
and the console script — lives at `../workflow.py`, which remains at the package root so that
every flow's prompt paths and `.agents/flavors/coder/` resolve correctly.

- code: `workflows/src/workhorse_workflows/coder/main/__init__.py`
- code: `workflows/src/workhorse_workflows/coder/main/flow.py::Coder`
- tests: `workflows/tests/coder/test_workflow.py::test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue`
- detail: [coder workflow composition root](coder-workflow-composition-root.md)

