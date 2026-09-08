---
type: concept
slug: repo-state-concept-selection
title: RepoState concept selection
---
# RepoState concept selection

`RepoState` is one frozen record for one working tree at one moment. The source assigns every
field an observation role: empty strings and `None` mean a fact was not observed, and the
telemetry projection omits those unavailable facts. It does not designate a different
representation or a preferred documentation view.

Use [RepoState fields](repo-state-fields.md) when selecting or interpreting a fact on the
record. Use [Repository observation](repository-observation.md) when the question concerns how
the module obtains, caches, scopes, or projects repository evidence. Neither concept supersedes
the other: both describe the same `RepoState` in different contexts.

- code: `workhorse/workhorse/gitstate.py::RepoState`
- rule: use RepoState fields for field-level semantics and Repository observation for observation lifecycle and diagnostic context; neither is preferred
- detail: [RepoState concept selection](repo-state-concept-selection.md)
