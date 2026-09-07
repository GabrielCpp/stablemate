---
type: concept
slug: run-invocation-reading-guide
title: Run invocation reading guide
---
# Run invocation reading guide

`RunInvocation` has one implementation, not four alternatives. Its source docstring defines the
value as the CLI's complete decision record, and `run_pyflow` projects that record into execution
state. The documentation is split by question because the same boundary has a role, named inputs,
and a lifecycle; the source records no preference or deprecation among those views.

Read [pyflow run invocation](pyflow-run.md) for the complete run lifecycle and the methods that
carry it out. Read [run invocation documentation](run-invocation-documentation.md) for why the
value is the boundary between CLI decisions and the runner. Read
[run invocation fields](run-invocation-fields.md) for the meaning of a named input. Read
[run invocation views](run-invocation-views.md) for the short map of those perspectives. Choosing
one view narrows the question; it does not select a different implementation.

- rule: choose the lifecycle, boundary-role, field, or overview document according to the question; all describe the same `RunInvocation`, and none supersedes another
