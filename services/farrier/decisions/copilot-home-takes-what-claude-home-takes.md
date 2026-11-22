story: none
date: 2026-11-22
elements: InstallUser

A `[user_library.copilot]` table takes rules, MCP servers, guards, helper agents and settings, the same keys a
`[user_library.claude]` table takes. Before this, farrier wrote only skills into `~/.copilot` and refused every other
key, so a person who moved from Claude to Copilot lost the home setup the library keeps for them. Every harness farrier
knows now has a writer for each of those keys, so the refusals that named an unsupported harness are gone.

Copilot reads its home rules from `~/.copilot/copilot-instructions.md`, its servers from `~/.copilot/mcp-config.json`,
its agents from `~/.copilot/agents/*.agent.md` and its settings from `~/.copilot/settings.json`. Copilot documents that
settings file as JSONC. Farrier merges it as plain JSON, so a comment the person adds there stops the install with a
parse error. The library's Copilot settings carry no comment, and a person who wants one moves the key elsewhere.

A guard is written for Claude's hook input. Copilot hands a `preToolUse` hook other tool names and other fields, so
farrier writes `~/.copilot/hooks/farrier-guards.py`, a bridge that turns Copilot's input into Claude's, runs the guard,
and turns its verdict back. A guard that crashes allows the call, as it does under Claude. A guard that runs when the
agent stops is written on Copilot's `agentStop` hook, which OpenCode has no counterpart for.

The hook list itself is `~/.copilot/hooks/farrier-guards.json`. JSON holds no comment, so farrier owns that file by its
name and overwrites a hand-written file of the same name. Any other file in `~/.copilot/hooks/` is the person's.

A helper agent that names delegates gets Copilot's `agent` tool, which Copilot does not limit to named agents. The
agent's prompt names whom it hands work to, and Copilot may still let it reach another agent.
