---
type: concept
slug: run-configuration-concept-selection
title: Run configuration concept selection
---
# Run configuration concept selection

`RunConfig` is the immutable value that carries configuration for one run. The per-run
configuration concept documents when that value is created and consumed. The field-selection
concept documents how to choose among its distinct policy fields when constructing or reading
that same value.

Neither concept is an alternate implementation or a replacement for the other. `RunConfig`
constructs `resilience` from environment-derived settings and captures the remaining
environment-derived fields in `from_env`; the CLI separately supplies the resolved `backend`
and selected `profile`. Use the per-run configuration concept for the value's lifecycle and
immutability, and use field selection for the policy a particular field represents. No ranking
exists because both concepts describe complementary aspects of the same class.

- code: `workhorse/workhorse/config_run.py::RunConfig`
- rule: use per-run configuration to understand the immutable value's lifecycle; use field selection to choose the distinct policy field being constructed or read, because neither concept supersedes the other
- detail: [run configuration concept selection](run-configuration-concept-selection.md)
