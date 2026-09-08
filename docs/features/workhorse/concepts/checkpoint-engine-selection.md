---
type: concept
slug: checkpoint-engine-selection
title: Checkpoint engine selection
---
# Checkpoint engine selection

New checkpoints use `PyflowCheckpoint`. Its `engine` marker is the fail-closed discriminator for
the current engine, and its required `state` is the value a resume consumes. A
`NodeGraphCheckpoint` has a `current_id` instead; it is not an alternative resume format.

`NodeGraphCheckpoint` remains in the checkpoint union only so a reader of a run directory created
by the retired YAML engine can recognize that record and refuse it by name. Nothing writes the
retired shape, so no new checkpoint or resumed run should select it.

- code: `workhorse/workhorse/records.py::Checkpoint`
- rule: use `PyflowCheckpoint` for every new checkpoint; accept `NodeGraphCheckpoint` only to identify and refuse a retired YAML-engine record
- prefers: [PyflowCheckpoint](run-records.md#pyflowcheckpoint)
- deprecates: [NodeGraphCheckpoint](run-records.md#field-nodegraphcheckpoint)
