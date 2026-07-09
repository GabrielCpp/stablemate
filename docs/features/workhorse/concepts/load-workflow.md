---
type: concept
slug: load-workflow
title: load_workflow — parse a workflow.yaml into a Graph
---
# load_workflow

Parses a [workflow file](../workflow-format.md) into the validated `Graph` model that
[workhorse run](../workhorse.md#run) walks. The single parse+validate entry for the format.

- code: `workhorse/workhorse/graph/loader.py::load_workflow`

## Contract

- **Input:** `path: str | Path` — a `workflow.yaml`.
- **Output:** a validated `Graph` (see the [workflow file format](../workflow-format.md) for the
  field contract).
- **Raises:** `ValueError` on any invalid workflow (unparsable YAML, missing `start`, an
  unresolved `next`/branch/flow target, or a `flow` node naming an absent flow). The pydantic
  `ValidationError` is caught and re-raised as `ValueError("Invalid workflow '<path>': …")`.

## Algorithm

1. Read the file and parse YAML into a dict (`yaml.safe_load`).
2. **Shape** the raw dict into model form: build the `nodes` map by keying each entry of the
   `nodes:` list by its `id`; recurse the same shaping into every entry of `flows:` (each flow is
   a full workflow, its default `name` = its map key); carry `name` (defaulting to the file stem),
   `start`, and `vars`.
3. **Validate** the shaped dict into a `Graph`. The discriminated union resolves each node by its
   `type`. Edge validation then asserts: `start` is a known node; every `agent`/`script`/`call`
   `next`, every `flow` `next`, every `branch` `cases`/`conditions`/`default` target resolves to a
   node in the *same* graph; and every `flow` node's `name` is a key in that graph's `flows`.
4. Return the `Graph` (each sub-graph in `flows` self-validates the same way).
