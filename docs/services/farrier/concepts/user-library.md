---
type: concept
slug: user-library
title: User library
---
# User library

User-library configuration selects skills, prompts, always-on rules, MCP servers, guards and
[helper agents](helper-agent.md) once for all repositories, by harness, in the shared stablemate configuration. MCP servers and
[home guards](home-guard.md) land as [merged home entries](merged-home-entry.md), because the files
holding them belong to the harness.

- rule: a home's always-on rules are one library root per harness, so the same text reaches `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md` and `~/.config/opencode/AGENTS.md`, and a root that must differ per harness branches on the `target` template variable
- rule: the library is the only place to edit a home's rules, so `--check` reports an edit to the generated file as drift and the next install overwrites it
- rule: farrier never replaces a hand-written instruction file, so moving existing rules into the library means deleting or renaming the file once
- rule: an OpenCode table writes no skills, and the skills it names are left out in silence so a shared pack can serve it, because OpenCode reads skills from `~/.claude/skills` and `~/.agents/skills`
- rule: Copilot takes no root at user scope, because its home setup is skills only

## Methods

### method: user_library_tables
- sig: `user_library_tables(home: HomeConfig) -> dict[str, Selection]`
- does: return non-empty Claude, Codex, Copilot and OpenCode tables in fixed harness order
- raises: `SystemExit` for unknown harness tables
- verify: count(subject="configured user-library harness tables", equals=1)
- code: `farrier/farrier/user_library.py::user_library_tables` @c71b69ee84ae

### method: user_template_values
- sig: `user_template_values(home: HomeConfig) -> dict[str, Any]`
- does: return the template mapping of the loaded home config shared by every configured harness
- verify: count(subject="shared user-library template values", equals=1)
- code: `farrier/farrier/user_library.py::user_template_values` @ec4996d8b8ce
