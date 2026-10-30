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

A profile can name subagent delegates for a turn to hand work to on another model. There are
three roles. `lookup` answers one narrow read-only question about the code or a log. `worker`
does one bounded task the caller specifies in full. `advisor` answers one design question
read-only, such as whether a finding is a defect, from the paths the caller names. A delegate
name outside these three is ignored with a warning. A profile that names no `advisor` still gets
one on a CLI that takes subagents: it runs on the model the profile's `max` power tier maps to.
A profile whose `max` tier names no model gets no default advisor. Claude, codex and opencode
define the delegates when the turn launches. Copilot and cline take no subagents, so they get no
default advisor, and they warn once that the delegates the profile names go unused. Each backend
also declares `supports_subagents`, so a workflow can check `Engine.subagents()` before it asks
for a delegate rather than finding out only from the runtime warning. A workflow asks
`Engine.has_delegate(role)` whether a turn it runs will be offered one named role.

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

A claude turn holds the models of its subagents to its profile. The Agent tool lets the model pick
any model alias for a subagent, and a prompt cannot stop that. The backend passes a `PreToolUse`
hook on the `Agent` tool through `--settings`, run as a Python module. The hook denies a call whose
`model` is outside the allowed set, and its reason lists the allowed aliases. The allowed set is
every model the profile names, which is its `default`, each `powers` tier and each `delegates`
role, plus the family alias of each one: `claude-opus-5-5` allows `opus`. A call with no `model`
inherits the turn's model and passes. A run on no profile names no models, so the hook is not
passed. A model that is not 5.5 under a profile of 5.5 models, such as `fable` or
`claude-fable-5-1`, is denied.

A claude turn names its brief in its system prompt. The engine writes each turn's rendered prompt
to a file, and the backend passes `--append-system-prompt` with that file's absolute path and an
instruction to read it again after a compaction. Claude compacts a long turn's conversation on its
own, and the summary can drop a path the brief gave. The system prompt is never compacted, so the
turn can always recover its inputs from disk. A turn with no prompt file gets no appended system
prompt.

Copilot and cline apply no box. A confined profile still runs the turn with the operator's full
permissions, and the backend prints `<cli> does not enforce a confined profile; the turn runs with
the operator's full permissions` once per turn. It does not refuse the turn.

- code: `workhorse/workhorse/runner/backends/__init__.py::AgentBackend` @bba883206087
- code: `workhorse/workhorse/runner/backends/registry.py::get_backend` @97728ec5a6f0
- code: `workhorse/workhorse/runner/backends/null.py::NullBackend` @2bae7c6d5353
- code: `workhorse/workhorse/runner/backends/claude.py::ClaudeBackend` @e0c48e164248
- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlBackend` @5cb576f3f346
- code: `workhorse/workhorse/runner/backends/codex.py::CodexBackend` @b0d7c09a1dec
- code: `workhorse/workhorse/runner/backends/copilot.py::CopilotBackend` @64b712777b3b
- code: `workhorse/workhorse/runner/backends/cline.py::ClineBackend` @4ca16506e4dd
- code: `workhorse/workhorse/runner/backends/opencode.py::OpenCodeBackend` @66339f656dfb
- code: `workhorse/workhorse/runner/backends/turn.py::TurnState` @375ce5ec8206
- code: `workhorse/workhorse/runner/backends/turn.py::OnEvent.__call__` @a6fcb85e3163
- code: `workhorse/workhorse/runner/backends/delegates.py::Delegate` @234ee3903391
- code: `workhorse/workhorse/runner/backends/guard.py::Policy` @0c9ee87d8c0e
- code: `workhorse/workhorse/runner/backends/model_guard.py::model_refusal` @8740b7720e05
- code: `workhorse/workhorse/runner/backends/guard_shell.py::shell_denial` @112a24f311f5
- code: `workhorse/workhorse/runner/backends/README.md` @b194b9459849
- code: `workhorse/docs/BACKENDS.md` @51dfb498850f
- code: `workhorse/workhorse/profile.py::resolve_delegates_for` @514c3066aced
- code: `workhorse/workhorse/profile.py::profile_models` @e16bd2a4cda8
- code: `workhorse/workhorse/pyflow/engine.py::Engine.has_delegate` @72ec254d7ec8
- rule: a turn never loads less of the operator's environment than an interactive session of its CLI, and confinement is a guard layered on top of it
- rule: a confined opencode turn gets read and write on its added directories through permission config, never through a plugin or shared state file
- rule: a claude turn's subagents run only on models its profile names, because a prompt cannot hold the Agent tool's model pick and one run spent most of its cost on subagents from a model the workplace does not have
- rule: a claude turn's system prompt names the turn's brief file, because a compaction summary once lost the spec dir and the turn returned a false `blocked` after searching its working directory for a plan it had already written
- tests: `workhorse/tests/test_backends.py::test_claude_names_the_turn_brief_in_the_system_prompt`
- tests: `workhorse/tests/test_backends.py::test_claude_without_a_brief_file_appends_no_system_prompt`
- tests: `workhorse/tests/test_model_guard.py::test_a_model_outside_the_profile_is_denied_with_the_allowed_aliases`
- tests: `workhorse/tests/test_model_guard.py::test_the_profile_models_and_their_family_aliases_pass`
- tests: `workhorse/tests/test_model_guard.py::test_a_call_with_no_model_passes`
- tests: `workhorse/tests/test_model_guard.py::test_the_claude_command_line_carries_the_hook_on_the_agent_tool`
- tests: `workhorse/tests/test_delegates.py::test_the_advisor_defaults_to_the_max_tier_model`
- tests: `workhorse/tests/test_delegates.py::test_an_explicit_advisor_wins_over_the_default`
- tests: `workhorse/tests/test_delegates.py::test_no_default_advisor_when_the_cli_takes_no_subagents`
- tests: `workhorse/tests/test_delegates.py::test_no_max_model_means_no_advisor`
- tests: `workhorse/tests/test_pipeline.py::test_a_dry_run_has_a_delegate_only_when_the_environment_grants_subagents`
