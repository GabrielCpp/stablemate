---
type: concept
slug: exited-push-documentation-scopes
title: Exited push documentation scopes
---
# Exited push documentation scopes

`push_exited` is one residual HTTP-push handler, not two implementations to choose between. It
accepts an exited payload, rejects one without a usable container id, then ensures volume
metadata, upserts the workflow as finished, clears its gates, releases any active attend claim on
the container, dispatches an attendant to it when the stored exit code signals a death rather than
a clean exit, a supervisor-triggered reload, or an interrupt, broadcasts the changed run, and
retains the workflow record until a later discovery or refresh prune removes its container.

Read [push exited](groom-app-module.md#method-push-exited) for the handler's request-facing
contract: payload validation, metadata resolution, registry update, and dashboard broadcast.
Read [exited push transition](workflow-state.md#transition-exited-push) when the question is how
that same handler changes lifecycle state: it establishes `finished`, retains a numeric exit code
only when supplied, clears gates, and does not itself remove the workflow. Neither view supersedes
the other; each describes the same source operation from its own documented scope.

- code: groom/groom/app.py::push_exited
- rule: use the handler node for residual HTTP-push behavior and the transition node for the resulting workflow lifecycle change; neither is preferred because both describe one current handler.
