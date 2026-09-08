---
type: concept
slug: workflow-container-conversion-contexts
title: Workflow container conversion contexts
---
# Workflow container conversion contexts

`container_from_inspect` has two current documentation contexts because its one conversion
creates both a baseline lifecycle record and the structured workflow-container value that
other consumers use. Neither description supersedes the other.

Use the [initial workflow-state transition](workflow-state.md#transition-discovery-initial)
when deciding how Docker's running signal establishes the state before later discovery
evidence. Use the [Docker inspect container object conversion](../docker-inspect-container-object.md#consumer-workflow-container-conversion)
when deciding which inspect fields form the converted value and which conversion has no side
effects. The conversion starts with `running` or `idle` from `State.Running`; sidecar snapshots
and volume reconstruction may subsequently refine that baseline.

- code: groom/groom/discovery.py::container_from_inspect
- rule: select the lifecycle-transition context for initial state semantics and the Docker-inspect format context for the conversion input, output, and side-effect contract; neither context is preferred because both describe the same current conversion at different boundaries
