---
type: format
slug: agent-record
title: Agent record
---
# Agent record

An agent record is one Markdown file, `library/agents/<name>.md`, that declares one [helper agent](../concepts/helper-agent.md)
with no model in it. The file name is the name a `[user_library.<harness>]` table lists in `agents`. The text below the front
matter is the agent's prompt, and an empty prompt stops the install. An unknown key stops the install and names the file.

- file: `library/agents/<name>.md` in any library layer, the highest layer holding the name winning
- code: `farrier/farrier/home_agents.py::HelperAgent` @a7ffc0e190fa
- detail: [helper agent](../concepts/helper-agent.md)

## Fields

### field: description
- type: string
- required: true
- semantics: what the harness reads to decide when to hand work to this agent, with no model name in it

### field: read_only
- type: boolean
- default: `false`
- semantics: the agent never changes anything, which limits its tools on Claude, denies it edits on OpenCode and opens its prompt with a read-only instruction on Codex
