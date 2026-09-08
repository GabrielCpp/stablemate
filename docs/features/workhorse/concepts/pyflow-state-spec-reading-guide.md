---
type: concept
slug: pyflow-state-spec-reading-guide
title: Pyflow state specification reading guide
---
# Pyflow state specification reading guide

The source declares one frozen `StateSpec` record with `name`, `fn`, and `aliases`. Workflow
registration constructs that record once for each state, indexes its live name and aliases, and
resolution returns the same record for either kind of name. These documents are therefore views of
one implementation, not alternatives ranked by the source.

Use [pyflow state specification](pyflow-state-spec.md) for the record's definition and member API,
[pyflow state specification fields](pyflow-state-spec-fields.md) for the concern served by each
member, and [pyflow state specification registration data](pyflow-state-spec-registration-data.md)
for construction, indexing, and checkpoint-name resolution. Use [pyflow state specification
documentation scopes](pyflow-state-spec-documentation-scopes.md) when explaining why those views
share one source symbol. No view supersedes or deprecates another.

- rule: choose the state specification for the record and member API, fields for member roles, registration data for indexing and resolution, and documentation scopes for how those views relate; the source ranks none of them
