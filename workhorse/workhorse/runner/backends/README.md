# backends

The agent-CLI port lives in `__init__.py`. Each other module adapts one CLI to it, or
holds a piece several adapters share. A new CLI gets its own module and a line here.

## Map

- `claude.py`: the Claude Code CLI's stream-json, resume and compact protocol, and its adapter.
- `cline.py`: the Cline CLI's event vocabulary and adapter.
- `codex.py`: the Codex CLI's event vocabulary and adapter, including how a confined turn runs behind its guard hook.
- `codex_guard.py`: the hook that holds a confined codex turn to its policy. It owns the policy, the patch check and the hook entry.
- `codex_shell.py`: the judge of one shell call a confined codex turn makes.
- `copilot.py`: the GitHub Copilot CLI's event vocabulary and adapter.
- `jsonl.py`: the newline-delimited JSON event loop the CLIs that speak one share.
- `null.py`: the absence of an agent CLI, as an adapter.
- `opencode.py`: the OpenCode CLI's event vocabulary and adapter, and the probe for its provider's usage-window reset.
- `registry.py`: the table from a backend name to its adapter class.
- `turn.py`: what one non-Claude turn yielded, and the one place such a turn is classified.
