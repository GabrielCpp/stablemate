---
type: concept
slug: run-configuration-field-selection
title: Run configuration field selection
---
# Run configuration field selection

`RunConfig` fields are complementary parts of one immutable per-run value, not alternate
implementations. Select the field that expresses the policy being supplied or read; do not
substitute one field for another or treat any field as the general-purpose default.

At the CLI boundary, `RunConfig.from_env` captures the environment-derived fields together.
The CLI separately resolves and validates `backend` and selects `profile`; tests may construct
the complete value directly with an explicit or null backend. No ranking exists among these
fields because each controls a distinct part of the run contract. The shared selection concept
also distinguishes this field-focused view from the per-run lifecycle view.

- code: `workhorse/workhorse/config_run.py::RunConfig`
- rule: use each field only for its documented run policy; construct or read the complete immutable `RunConfig`, with `backend` and `profile` supplied by the CLI boundary rather than selected from the environment
- detail: [run configuration concept selection](run-configuration-concept-selection.md)
