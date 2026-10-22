---
type: concept
title: Agent backends
---
# Agent backends

An agent backend adapts one agent CLI to the engine, so a workflow's turns run unchanged on any
of them. Five CLIs are selectable by name: `claude`, `codex`, `copilot`, `cline` and `opencode`.
The run picks one as [profiles and config](profiles-and-config.md) describes, and each
[agent turn](agent-turns.md) goes through it.

A name outside the five fails before any turn with
`unknown CLI backend '<name>' (set AGENT_CLI, --cli or the config's default_cli to one of: claude,
cline, codex, copilot, opencode)`. A run with no CLI at all still starts. Its first agent node
fails with `node '<id>' needs an agent CLI and this run has none`, and the message tells the
operator to pass `--cli` or set `AGENT_CLI`.

Claude speaks its own stream-json protocol, with session resume and compaction. The other four
emit newline-delimited JSON events, which one shared loop reads. A non-Claude turn is classified
in one place from what it yielded. Each backend also maps its CLI's events to the one live
transcript form that [agent turns](agent-turns.md) describes, so a dashboard reads every CLI the
same way.

A profile can name subagent delegates for a turn to hand narrow work to on cheaper models. There
are two roles. `lookup` answers one narrow read-only question about the code or a log. `worker`
does one bounded task the caller specifies in full. A delegate name outside these two is ignored
with a warning. Claude, codex and opencode define the delegates when the turn launches. Copilot
and cline take no subagents, so they warn once that the profile's delegates go unused.

A confined codex turn runs outside the codex sandbox, because a profile's commands bring up the
app the turn works on. Every shell call and every patch passes a guard hook first instead. A
patch may write only under the turn's working directory. A shell call may run one of the
profile's commands or a read-only program such as `cat`, `grep`, `rg`, `ls` or `sed -n`, joined
by pipes at most. It may name no path outside the directories the turn reads, and a relative path
may not climb with `..` or start at `~`.

- code: `workhorse/workhorse/runner/backends/__init__.py::AgentBackend` @0cb3ab1a7936
- code: `workhorse/workhorse/runner/backends/registry.py::get_backend` @da60c2e93d28
- code: `workhorse/workhorse/runner/backends/null.py::NullBackend` @c9e7cd53f690
- code: `workhorse/workhorse/runner/backends/claude.py::ClaudeBackend` @c7e767f9f0c4
- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlBackend` @f6c5136add76
- code: `workhorse/workhorse/runner/backends/codex.py::CodexBackend` @f614c07420da
- code: `workhorse/workhorse/runner/backends/copilot.py::CopilotBackend` @9fc651d4051b
- code: `workhorse/workhorse/runner/backends/cline.py::ClineBackend` @26aae80e73ab
- code: `workhorse/workhorse/runner/backends/opencode.py::OpenCodeBackend` @418bf37a3893
- code: `workhorse/workhorse/runner/backends/turn.py::TurnState` @53dc2823fd84
- code: `workhorse/workhorse/runner/backends/turn.py::OnEvent.__call__` @53dc2823fd84
- code: `workhorse/workhorse/runner/backends/delegates.py::Delegate` @543f51f3d262
- code: `workhorse/workhorse/runner/backends/codex_guard.py::Policy` @736e50949720
- code: `workhorse/workhorse/runner/backends/codex_shell.py::shell_denial` @3366bb96722b
- code: `workhorse/workhorse/runner/backends/README.md` @ab7920b1b4ff
- code: `workhorse/docs/BACKENDS.md` @595130c671ae
