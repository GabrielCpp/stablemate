---
type: concept
slug: coder-docs-subflow
title: Coder docs subflow package
---
# Coder docs subflow package

The `coder.docs` package is the documentation subflow boundary. It exports only `Docs`, which
is the workflow machine that folds one completed story into the as-built OKF book. The complete
state and result contract is documented in the [Coder documentation flow](../flows/coder-docs.md).

The package owns the flow implementation and its three prompt templates. It does not duplicate
the documentation detector, OKF packet builder, schema models, or operator-resolution helpers:
those are shared contracts used by other Coder lanes and are reached through
`workhorse_workflows.coder.shared`.

`Docs` may be entered by the Coder main graph or directly as `workhorse-coder run docs`. A handoff
returns the subflow's `Done` value to the caller; prompt paths remain rooted at the `coder`
package, while this package contributes the `docs/prompts/` segment.

- code: `workflows/src/workhorse_workflows/coder/docs/__init__.py::__all__`
- detail: [coder documentation flow](../flows/coder-docs.md)

## Export

### Docs

`Docs` is the package's only public export. It resolves the story and documentation context,
dispatches the author and reviewer turns, gates local changes against direct OKF grounding, and
returns a passed, blocked, or not-applicable result to its caller. Its state-level contract and
the tests that exercise each branch live in the linked flow node rather than being duplicated in
this package-boundary concept.
