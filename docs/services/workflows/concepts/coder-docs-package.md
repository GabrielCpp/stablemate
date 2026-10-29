---
type: concept
slug: coder-docs-package
title: Coder docs package
---
# Coder docs package

The `docs` machine writes one story into the current OKF book, either before dev (the `spec`
phase, from the story's behaviour model, with no diff to read) or after it (the `build` phase).
In the build phase it first distinguishes an
unmanaged book from an unusable one, then, only for a usable book, resolves the story and
documentation context, optionally grounds the code diff locally, asks one owner turn to write,
review and repair the graph, and gates the result against direct grounding. It is a sub-flow
entered by the Coder main flow twice per story: first in the spec phase before dev, then in the
build phase after implementation is complete. It can also be run directly with
`workhorse-coder run docs`.

The machine creates the OKF book root when the repository has none, and fails before documentation
when the book is unusable. For a usable
book, a failed grounding gate goes back to the owner as a report for another repair lap, and a
spent lap budget escalates to the resolver and then to an operator gate.

- code: `workflows/src/workhorse_workflows/coder/docs/flow.py` @09559fc3bd97
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs` @ea9cbe7a4c39
- tests: `workflows/tests/coder/docs/test_flow.py`
- detail: [coder docs subflow](coder-docs-subflow.md)

The docs package operates against a docs repository carrying one epic with its `## Stories`
listing and one authored story, against a named workspace listing the source repositories the
context classifier decides between, and against the flow machinery that drives the agent turns.
The `docs`, `elsewhere`, and `alongside` test fixtures stand those inputs up — `docs` builds
the ostler-loadable repo with an epic, a story, and a spec dir; `elsewhere` builds a sibling
git repo that a named workspace lists outside the docs worktree so the classifier
returns `semantic`; `alongside` names the docs worktree itself as the workspace member so
the classifier returns `local` — so the routing the flow describes runs against the same worktree
shapes `Docs` is asked to handle in production.

## Methods

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: combines the run labels with the `docs.` counters for `laps`, `blocks` and `number` that the state carries
- verify: count(subject="docs counter labels", equals=1)
- returns: returns labels used for state telemetry
- verify: count(subject="docs state label sets", equals=1)
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs.state_labels` @f1e323205eb6
- tests: `workflows/tests/coder/test_telemetry.py::test_docs_reports_its_repair_laps_and_its_blocks`

