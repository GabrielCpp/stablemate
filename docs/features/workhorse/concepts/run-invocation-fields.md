---
type: concept
slug: run-invocation-fields
title: Run invocation fields
---
# Run invocation fields

`RunInvocation` carries one complete set of inputs for a single `run_pyflow` call. Its fields
are complementary parts of that boundary, not interchangeable implementations: callers supply
the registry and run location, may choose flow and identity, and can select resume, cache,
dry-run, manifest, configuration, and telemetry behaviour independently.

The run projects these values into local execution state, opens or resumes the run directory,
uses the registry and flow selection to instantiate the workflow, and builds `RunEnv` with the
configuration, dry-run, nodes, and manifest. There is no ranking among the fields: choose a
field only when its named input is needed, and preserve the remaining fields as the same
invocation boundary.

- code: `workhorse/workhorse/pyflow/run.py::RunInvocation`
- rule: use each `RunInvocation` field for its named run input; no field substitutes for another
- detail: [run invocation reading guide](run-invocation-reading-guide.md)
- detail: [run invocation views](run-invocation-views.md)
- detail: [run invocation documentation](run-invocation-documentation.md)
