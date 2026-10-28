---
type: concept
slug: coder-owner-step-cost
title: Coder owner step cost
---
# Coder owner step cost

An owner turn pays for its steps more than for its output. Each step the agent takes resends the
whole conversation, and an owner conversation runs between about 80k and 170k tokens once it has
compacted. Most of a story's cost is that re-read, multiplied by the number of steps.

Every owner prompt therefore carries one shared step-cost section. The dev, QA, fix, CI-fix and
documentation owners all render it. The dev owner carries it among the story's standing rules, so
the plan, build and review phases of one conversation read it once. The section asks the agent to
send independent reads and commands in one message, to chain dependent shell commands into one
command, and to read a file once, whole. A question that would take three or more steps goes to
a lookup subagent, which answers in a short conversation on a cheaper model. The agent named
`lookup` exists when the operator's profile names a model for the `lookup` delegate role.

Nothing gates the rule after the turn. Groom measures it: the calls per visit and the tool calls
per message of an owner node, read before and after a change.

- code: `workflows/src/workhorse_workflows/coder/shared/prompts/_step-cost.md` @56cdebd43469
- code: `workflows/src/workhorse_workflows/coder/dev/prompts/_dev-rules.md` @c7825d3c1bfd
- rule: every owner prompt renders the shared step-cost section, once per conversation where one conversation spans several phases
- rule: a question that takes three or more steps goes to a lookup subagent, not to the owner's own conversation
- detail: [agent backends](../../workhorse/concepts/agent-backends.md)
- detail: [coder dev-build prompt](../formats/coder-dev-build-prompt.md)
