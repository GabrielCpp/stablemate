---
type: concept
slug: pyflow-state-spec-registration-data
title: pyflow state specification registration data
---
# pyflow state specification registration data

`StateSpec` is one immutable registration record, not two implementations to choose between.
Registration indexes `name` as the live state name, stores `fn` as the state callable, and
registers every `aliases` value as a retired name for that same record. State rendering uses live
names, while checkpoint resolution may use either a live name or an alias; the returned record
still supplies the callable to invoke.

No ranking exists because the two descriptions cover different scopes: the state specification
describes the record as a whole, and the fields concept explains the distinct concern of each
member. Use the whole-record concept to understand state registration and resolution; use the
fields concept when selecting the member needed by an identifier, invocation, or retired
checkpoint name.

- code: `workhorse/workhorse/pyflow/workflow.py::StateSpec`
- rule: use the state specification for the registration record and its fields for their individual identifier, callable, and retired-checkpoint concerns; neither concept supersedes the other
- detail: [pyflow state specification reading guide](pyflow-state-spec-reading-guide.md)
