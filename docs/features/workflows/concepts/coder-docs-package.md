---
type: concept
slug: coder-docs-package
title: Coder docs package
---
# Coder docs package

The `docs` machine folds one completed story into the current OKF book. It resolves the story and
documentation context, distinguishes an unmanaged book from an unusable one, optionally grounds
the code diff locally, asks an author turn to write the graph, gates the result against direct
grounding, and obtains an independent documentation review. It is a sub-flow entered by the Coder
main flow after implementation is complete, and can also be run directly with `workhorse-coder run docs`.

The machine returns not-applicable without an agent turn when the repository has no OKF book, and
fails before documentation when the book is unusable. For a usable book, it chains documentation
prompts with grounding validation and independent review, each failure offering an automatic
resolver bounded repair cycles before escalation to an operator gate.

- code: `workflows/src/workhorse_workflows/coder/docs/flow.py`
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs`
- code: `workflows/tests/coder/docs/test_flow.py::docs`
- code: `workflows/tests/coder/docs/test_flow.py::elsewhere`
- code: `workflows/tests/coder/docs/test_flow.py::alongside`
- tests: `workflows/tests/coder/test_docs.py`
- tests: `workflows/tests/coder/docs/test_flow.py`
- detail: [coder docs subflow](coder-docs-subflow.md)

The docs package operates against a docs repository carrying one epic with its `## Stories`
listing and one authored story, against a workspace file naming the source repositories the
context classifier decides between, and against the flow machinery that drives the agent turns.
The `docs`, `elsewhere`, and `alongside` test fixtures stand those inputs up — `docs` builds
the ostler-loadable repo with an epic, a story, and a spec dir; `elsewhere` builds a sibling
git repo with an `.code-workspace` file that points outside the docs worktree so the classifier
returns `semantic`; `alongside` rewrites the same workspace to point inside the docs worktree so
the classifier returns `local` — so the routing the flow describes runs against the same worktree
shapes `Docs` is asked to handle in production.

## Methods

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: combines run labels with telemetry labels for the `docs` machine
- does: emits every budget counter from the carried `DocsLoop` under the `docs.` prefix, using the names enumerated by `DocsLoop.COUNT_LABELS`
- does: emits every progress-bundle counter and verdict from the carried `DocsLoop.progress` under the `docs.` prefix, using the names enumerated by `DocsProgress.COUNT_LABELS` and `DocsProgress.VERDICT_LABELS`
- does: returns the base run labels alone when no `DocsLoop` is present in the state, so `setup` and the first entry to `start` (which run before any loop exists) report no counters or verdicts
- does: omits a verdict label when the underlying value is empty, so a lane that has not yet spoken claims no verdict rather than emitting `""` or `cleared` by default
- returns: returns labels used for state telemetry
- verify: count(subject="docs state label sets", equals=1)
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs.state_labels`
- tests: `workflows/tests/coder/test_telemetry.py::test_a_state_with_no_loop_yet_reports_only_the_base_labels`

