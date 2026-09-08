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
- tests: `workflows/tests/coder/test_docs.py`
- detail: [coder docs subflow](coder-docs-subflow.md)

