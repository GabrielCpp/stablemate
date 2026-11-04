---
type: concept
slug: helper-agent
title: Helper agent
---
# Helper agent

A helper agent is a role a session hands narrow work to, such as a cheap lookup, so the same names work
whether the user is in Claude Code, Codex or OpenCode. One [agent record](../formats/agent-record.md) renders to
`~/.claude/agents/<name>.md`, `~/.codex/agents/<name>.toml` and `~/.config/opencode/agents/<name>.md`, on the
model each harness's profile names.
A `[user_library.<harness>]` table in the [user library](user-library.md) selects agents in `agents`, or a pack does.

- rule: the record names no model, because the role is shared and the model is not, so a record with a `model` key stops the install and its description says nothing about a model
- rule: the model comes from `[profiles.<harness>.delegates.<name>]`, the same map workflow runs read, so a session and a workflow turn route one role to one model
- rule: a selected agent with no model in that map stops the install and names the table, because guessing a model would spend the wrong quota in silence
- rule: a `read_only` agent gets only read tools on Claude, which Claude enforces
- rule: a `read_only` agent carries a read-only instruction at the top of its prompt on Codex, because a Codex agent inherits its parent's sandbox and its file cannot narrow it, so on Codex the prompt asks and nothing enforces
- rule: a `read_only` agent carries `permission: edit: deny` on OpenCode, which OpenCode enforces on its edit, write and patch tools and not on its shell
- rule: OpenCode's effort is a variant, so `low` renders as `minimal`, `medium` renders as no variant, `xhigh` and `max` render as `max`, and `high` stays `high`
- rule: the generated mark on an OpenCode agent is a comment in its front matter, because OpenCode hands an unknown front matter key to the model provider
- rule: a Codex profile model after an `@` renders as the part after the `@`, and `xhigh` or `max` effort renders as `high`, the same spelling workflow runs use
- rule: a hand-written agent file under a name the table selects stops the install and survives it, and an agent file under any other name stays untouched
- rule: Copilot takes no agent, because its home setup is skills only
- rule: agents belong to a home and not to a repository, so a pack's `agents:` key takes effect at user scope only

## Methods

### method: load_agent
- sig: `load_agent(name: str) -> HelperAgent`
- does: return the agent record from the highest library layer holding the name
- raises: `SystemExit` for an unknown name, an unknown key, a missing `description` or an empty prompt
- verify: stderr(text="unknown agent")
- code: `farrier/farrier/home_agents.py::load_agent` @1068e6710331

### method: agent_names
- sig: `agent_names(table: Selection) -> set[str]`
- does: return the agents a harness table selects, directly in `agents` or through its packs
- verify: count(subject="selected agent names", equals=1)
- code: `farrier/farrier/home_agents.py::agent_names` @433892c9a1b3

### method: role_model
- sig: `role_model(config: HomeConfig, harness: str, name: str) -> PowerMapping`
- does: return the model the harness's profile names for the role
- raises: `SystemExit` naming the table and the missing profile key when the profile names no model
- verify: stderr(text="names no model")
- code: `farrier/farrier/home_agents.py::role_model` @cbf153aecbf8

### method: claude_agent
- sig: `claude_agent(agent: HelperAgent, role: PowerMapping) -> str`
- does: return the Claude agent file, with the role's model and effort, the agent's tools and the generated mark in its front matter
- verify: contents(subject="Claude agent file", text="generated_by: farrier")
- code: `farrier/farrier/home_agents.py::claude_agent` @4248e03a967d

### method: codex_agent
- sig: `codex_agent(agent: HelperAgent, role: PowerMapping) -> str`
- does: return the Codex agent file, marked as generated on its first line, with the prompt as `developer_instructions`
- verify: contents(subject="Codex agent file", text="developer_instructions")
- code: `farrier/farrier/home_agents.py::codex_agent` @ad09af9277b3

### method: opencode_agent
- sig: `opencode_agent(agent: HelperAgent, role: PowerMapping) -> str`
- does: return the OpenCode agent file in `subagent` mode, with the role's model and variant and the prompt below its front matter
- verify: contents(subject="OpenCode agent file", text="mode: subagent")
- code: `farrier/farrier/home_agents.py::opencode_agent` @254c4e7d4d07

### method: agent_files
- sig: `agent_files(config: HomeConfig, home: Path) -> dict[Path, Rendered]`
- does: return every agent file the user-library tables intend
- raises: `SystemExit` when a table of a harness with no agent dialect names an agent
- verify: stderr(text="names agents")
- code: `farrier/farrier/home_agents.py::agent_files` @11e02e8ffc96
