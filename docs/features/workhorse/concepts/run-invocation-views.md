---
type: concept
slug: run-invocation-views
title: Run invocation views
---
# Run invocation views

`RunInvocation` is the single immutable CLI boundary for a pyflow run. Its source
documentation defines the value as the workflow selection, artifact location, inputs, and
resume spelling chosen by the operator; `run_pyflow` then projects that one value into the
local state used to execute the run.

Read [pyflow run invocation](pyflow-run.md) when following the lifecycle after that boundary
reaches `run_pyflow`, including preflight, run resolution, telemetry, control, reload, and
terminal handling. Read [run invocation documentation](run-invocation-documentation.md) for
the boundary's role between the CLI and the runner. Read [run invocation fields](run-invocation-fields.md)
when selecting or understanding one named input. These are complementary views of the same
value, not competing implementations, so no view supersedes another.

- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- rule: choose the lifecycle, boundary, or field view according to the question being answered; no view replaces another
- detail: [run invocation reading guide](run-invocation-reading-guide.md)
