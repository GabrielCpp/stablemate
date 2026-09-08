---
type: concept
slug: pyflow-state-spec-documentation-scopes
title: Pyflow state specification documentation scopes
---
# Pyflow state specification documentation scopes

`StateSpec` has one implementation: the frozen record constructed during workflow class
registration. Its three values serve complementary concerns: `name` identifies the live state,
`fn` is the callable the driver invokes, and `aliases` preserves retired checkpoint names.

Use the whole-record and registration-data concepts to understand how registration indexes and
resolves a state. Use the fields concept when the question concerns one member's identifier,
callable, or retired-checkpoint role. Neither is an alternative implementation, so no ranking,
deprecation, or migration rule exists.

- code: `workhorse/workhorse/pyflow/workflow.py::StateSpec`
- rule: use the whole-record and registration-data concepts for registration and resolution, and the fields concept for an individual member; they document complementary scopes of one `StateSpec`, not alternatives
- detail: [pyflow state specification reading guide](pyflow-state-spec-reading-guide.md)
