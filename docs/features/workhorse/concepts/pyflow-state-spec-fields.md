---
type: concept
slug: pyflow-state-spec-fields
title: pyflow state specification fields
---
# pyflow state specification fields

Every `StateSpec` carries all three fields. They are complementary registration data, not
alternative state representations: `name` is the live identifier, `fn` is the callable the
driver invokes, and `aliases` preserves retired identifiers for checkpoint resolution.

Registration constructs one record with each value. Consumers use the member whose concern they
need rather than choosing one field in place of another.

For registration and state resolution as a whole, see [pyflow state specification registration
data](pyflow-state-spec-registration-data.md).

- code: `workhorse/workhorse/pyflow/workflow.py::StateSpec`
- rule: use `name`, `fn`, and `aliases` for their respective identifier, callable, and retired-checkpoint concerns; none replaces another
- detail: [pyflow state specification reading guide](pyflow-state-spec-reading-guide.md)
