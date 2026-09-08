---
type: concept
slug: pyflow-workflow-field-selection
title: Pyflow workflow field selection
---
# Pyflow workflow field selection

`Workflow` fields are complementary configuration and registration slots, not alternative
implementations. Select `repo_dir` and `library_dirs` for the run inputs a workflow consumes;
select `injects` to control which of those inputs cross a node or sub-workflow seam when the
callsite omitted them; and select `INFRA_NODES` to classify declared node spans as infrastructure
work.

Select `states` and `start_state` to register and resume the state machine. Select
`max_transitions` for a workflow-specific transition ceiling, or leave it at zero to use the
run-configured budget; select `REFUEL_ON` only for state parameters whose changed values prove
forward progress and refill that budget. No field is a replacement or default choice for another:
each describes a distinct input, registration, telemetry, or transition-policy concern.

- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`
- rule: select the field for its distinct workflow concern; the fields are complementary and have no ranking or replacement relationship
- detail: [pyflow workflow reading guide](pyflow-workflow-reading-guide.md)
