---
type: concept
slug: research-workflow-documentation-boundaries
title: Research workflow documentation boundaries
---
# Research workflow documentation boundaries

The `Research` class has two current documentation views because its state methods both route the
gate loop and render the persona prompts that make its bounded decisions. The state methods and
the `workflow` registry establish the entry point, checkpointed input, transitions, deterministic
handoffs, and terminal outcomes. The `agent()` calls establish each prompt's template, supplied
arguments, response model, and persona responsibility.

Neither view supersedes the other. A routing change can alter a prompt invocation, and a prompt
contract change can alter the state that consumes its reply; readers working across that boundary
need both views.

- rule: use [research workflow composition root](research-workflow-composition-root.md) for the command entry point, state-machine routing, and deterministic handoffs; use [research prompt contracts](research-prompt-contracts.md) for template inputs, reply models, and persona responsibilities; use both when a state changes a prompt invocation or consumes its reply
