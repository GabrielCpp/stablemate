---
type: concept
slug: research-workflow-composition-root
title: Research workflow composition root
---
# Research workflow composition root

The installed `workhorse-research` command imports `main` from this module. Its `workflow`
registry is the composition boundary for a single gate-at-a-time research machine: a bare run
enters `Research`, whose states select a gate, design and rehearse an experiment, submit a
detached measurement, classify its artifacts, and record a lead's verdict. The state machine
and its response models are documented as deeper layers; deterministic work is delegated to the
research node package.

The registry is rooted at `workhorse_workflows.research`, so every prompt path resolves from this
workflow package. Its dry-run replies make gate selection report an exhausted ladder and make the
goal lead report `reached`; that gives a static dry run a terminating path without inventing an
experiment. The registry registers the research node blueprint, and `main` adapts its default
entry point into the callable required by the console-script installation.

- code: `workflows/src/workhorse_workflows/research/workflow.py::Research`
- code: `workflows/src/workhorse_workflows/research/workflow.py::workflow`
- code: `workflows/src/workhorse_workflows/research/workflow.py::main`
- tests: `workflows/tests/research/test_workflow.py::test_a_gate_designed_built_measured_and_approved_drives_the_program_to_its_goal`
- tests: `workflows/tests/research/test_workflow.py::test_the_checkpoint_carries_the_counters_an_operator_would_edit`
- tests: `workflows/tests/research/test_workflow.py::test_a_resume_rebuilds_the_budget_from_the_checkpoint`
