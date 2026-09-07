---
type: concept
slug: run-invocation-documentation
title: Run invocation documentation
---
# Run invocation documentation

`RunInvocation` is one immutable value assembled from the CLI's run decisions. The class's
docstring identifies its fields as the CLI contract: which workflow runs, where artifacts go,
which inputs it receives, and which resume spelling the operator selected. `run_pyflow` projects
that value into local execution state before resolving the run directory and constructing the
workflow environment.

Read [pyflow run invocation](pyflow-run.md) for the lifecycle carried out after the boundary
reaches `run_pyflow`, including preflight, run-directory resolution, telemetry, control, reload,
and terminal handling. Read [run invocation fields](run-invocation-fields.md) when selecting or
understanding a particular CLI-boundary input. The two documents describe complementary views of
the same value; neither is an alternative implementation or a replacement for the other.

- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- rule: use pyflow run invocation for the run lifecycle and run invocation fields for a named CLI-boundary input; neither view replaces the other
- detail: [run invocation reading guide](run-invocation-reading-guide.md)
- detail: [run invocation views](run-invocation-views.md)
