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
and cline take no subagents, so they warn once that the profile's delegates go unused. Each
backend also declares `supports_subagents`, so a workflow can check `Engine.subagents()` before
it asks for a delegate rather than finding out only from the runtime warning.

A turn never loads less of the operator's environment than an interactive session of its CLI.
User settings, permission rules, hooks, model settings, skills, instruction files and plugins all
load. A profile's `confined` box narrows what the turn may write, read and run with a guard layered
on top of that environment, and removes none of it. The directories the CLI loads the operator's
config from stay readable inside the box. Those are `~/.claude` for claude, `~/.codex` and
`~/.agents` for codex, and `~/.config/opencode`, `~/.claude/skills` and `~/.agents/skills` for
opencode. A profile's `tools` map still turns tools off.

A confined codex or claude turn runs with the CLI's own permission prompts and sandbox off,
because a profile's commands bring up the app the turn works on. Every tool call passes a guard
hook first instead. Claude gets the hook through a `--settings` value, so every setting source
still loads. A write tool, which is a patch for codex and `Write`, `Edit`, `MultiEdit` or
`NotebookEdit` for claude, may write only under the turn's working directory. A `Read`, `Glob` or
`Grep` may read only under the working directory, the added directories, the project skill
directory and the operator's config directories. A `Glob` or `Grep` with no path searches the
working directory. A shell call may run one of the profile's commands or a read-only program such
as `cat`, `grep`, `rg`, `ls`, `sort` or `sed -n`, joined by pipes. It may join whole commands with
`;`, `&&` and `||`. A `cd` may move only into a directory the turn reads, and `xargs` runs only what
the turn could run itself. It may name no path outside the directories the turn reads, and a
relative path may not climb with `..` or start at `~`.

A confined opencode turn reads and writes in its working directory and in every added directory,
an added repo beside its own worktree included. It also reads the operator's config directories,
and never writes them. Its permission config alone holds it there, with no opencode plugin. A path
in no allowed directory is refused, and so is one that climbs out of an added directory with `..`.
The turn has no grep, glob or list, because opencode answers those outside its path rules. A
confined turn whose working directory lies in no git worktree fails before it starts with
`a confined opencode turn needs a git worktree`.

Copilot and cline apply no box. A confined profile still runs the turn with the operator's full
permissions, and the backend prints `<cli> does not enforce a confined profile; the turn runs with
the operator's full permissions` once per turn. It does not refuse the turn.

- code: `workhorse/workhorse/runner/backends/__init__.py::AgentBackend` @bd7a03e99213
- code: `workhorse/workhorse/runner/backends/registry.py::get_backend` @da60c2e93d28
- code: `workhorse/workhorse/runner/backends/null.py::NullBackend` @4464f8371e1f
- code: `workhorse/workhorse/runner/backends/claude.py::ClaudeBackend` @d1d9cb14c387
- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlBackend` @f6c5136add76
- code: `workhorse/workhorse/runner/backends/codex.py::CodexBackend` @39b0f1e8c0c2
- code: `workhorse/workhorse/runner/backends/copilot.py::CopilotBackend` @bb84ceeeae1a
- code: `workhorse/workhorse/runner/backends/cline.py::ClineBackend` @368bf532a646
- code: `workhorse/workhorse/runner/backends/opencode.py::OpenCodeBackend` @9f80c4f01201
- code: `workhorse/workhorse/runner/backends/turn.py::TurnState` @53dc2823fd84
- code: `workhorse/workhorse/runner/backends/turn.py::OnEvent.__call__` @53dc2823fd84
- code: `workhorse/workhorse/runner/backends/delegates.py::Delegate` @543f51f3d262
- code: `workhorse/workhorse/runner/backends/guard.py::Policy` @d037c4d084f4
- code: `workhorse/workhorse/runner/backends/guard_shell.py::shell_denial` @17d1634259b6
- code: `workhorse/workhorse/runner/backends/README.md` @62fdedd35d86
- code: `workhorse/docs/BACKENDS.md` @595130c671ae
- rule: a turn never loads less of the operator's environment than an interactive session of its CLI, and confinement is a guard layered on top of it
- rule: a confined opencode turn gets read and write on its added directories through permission config, never through a plugin or shared state file
