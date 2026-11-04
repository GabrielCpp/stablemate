---
type: concept
slug: home-guard
title: Home guard
---
# Home guard

A home guard is a check a harness runs before each tool call it watches, so the same refusals hold
whether the user works in Claude Code, Codex or OpenCode. One [guard record](../formats/guard-record.md) renders
to a hook group in `~/.claude/settings.json` and in `~/.codex/hooks.json`, and its scripts install once
into `~/.agents/hooks/<name>`. Each group is a [merged home entry](merged-home-entry.md) in the
`hooks.PreToolUse` container, named by the command it runs because a group has no name of its own.
OpenCode has no command hooks, so farrier generates one plugin, `~/.config/opencode/plugins/farrier-guards.ts`,
that calls each guard's command before a watched tool runs.
A `[user_library.<harness>]` table in the [user library](user-library.md) selects guards in `hooks`, or a pack does.

- rule: Claude spells `shell` as `Bash`, `edit` as `Write|Edit|MultiEdit`, `read` as `Read` and `search` as `Grep`
- rule: Codex spells `shell` as `Bash` and `edit` as `apply_patch`, and has no `read` or `search` tool because it reads through the shell
- rule: OpenCode spells `shell` as `bash`, `edit` as `edit|write|apply_patch`, `read` as `read` and `search` as `grep`
- rule: the bridge hands a guard each call in Claude's shape, because every guard reads that shape and a guard must not learn another harness
- rule: the bridge reads a verdict as a harness does, so exit 2 or a `permissionDecision` of `deny` blocks the call, and any other exit or a command that fails to start allows it
- rule: the bridge gives a guard with no `timeout` 60 seconds, because a plugin has no harness default to fall back on
- rule: OpenCode's `bash` tool takes `timeout`, so a guard that requires one works there as it does on Claude
- rule: OpenCode needs no approval for a guard, because a plugin in the home runs at startup
- rule: the bridge leaves the home with the last guard an OpenCode table names, and a hand-written plugin of another name stays untouched
- rule: a hand-written plugin at the bridge's path stops the install and survives it
- rule: a guard installed on a harness must deny there what it denies on Claude, so a guard that watches nothing the harness has stops the install instead of installing and checking nothing
- rule: a guard that would block ordinary work on a harness stays off that harness, by `not_on` in its record, and the install prints the guard it left out
- rule: Copilot takes no guard, because its home setup is skills only
- rule: farrier never grants Codex's approval, because that approval is the user's consent to run a command on every tool call
- rule: Codex skips a new or changed guard until the user approves it in `/hooks`, so an install that moves a Codex guard says so and `--check` names each guard with no approval recorded
- rule: `--check` reads that a guard has an approval and not whether the approval still matches, because the hash belongs to Codex, so a guard whose definition changed reads as approved until Codex asks again
- rule: a new group goes after the existing groups, because Codex keys an approval by the group's position, and dropping a group can move the ones after it
- rule: a group holding a second handler beside a farrier guard no longer matches the library, so the next install replaces the whole group
- rule: guards belong to a home and not to a repository, so a pack's `hooks:` key takes effect at user scope only

## Methods

### method: load_guard
- sig: `load_guard(name: str) -> Guard`
- does: read `library/hooks/<name>/hook.yml` from the highest library layer holding it
- raises: `SystemExit` naming the available guards when no layer holds the record
- verify: stderr(text="unknown guard")
- raises: `SystemExit` naming the file when a key is unknown, `command` is missing or `watches` is empty or holds another kind
- verify: stderr(text="unknown keys")
- code: `farrier/farrier/home_guards.py::load_guard` @a219af53b691

### method: guard_names
- sig: `guard_names(table: Selection) -> set[str]`
- does: return the guards a harness table selects, directly in `hooks` or through its packs
- verify: count(subject="selected guard names", equals=1)
- code: `farrier/farrier/home_guards.py::guard_names` @bc083ced1427

### method: selected_guards
- sig: `selected_guards(home: HomeConfig) -> dict[str, list[Guard]]`
- does: load each harness's guards in a stable order, leaving out a harness with none
- raises: `SystemExit` when a table of a harness with no guard dialect names a guard
- verify: stderr(text="names guards")
- code: `farrier/farrier/home_guards.py::selected_guards` @d3faeb6188d5

### method: installed_command
- sig: `installed_command(guard: Guard, home: Path) -> str`
- does: return the record's command with `{dir}` replaced by the shell-quoted installed folder
- verify: contents(subject="installed guard command", text="/.agents/hooks/")
- code: `farrier/farrier/home_guards.py::installed_command` @2a81f7f36b5b

### method: watched_tools
- sig: `watched_tools(guard: Guard, harness: str) -> str`
- does: return the harness's tools for the kinds the guard watches, as a matcher
- raises: `SystemExit` naming the guard and the harness when the guard watches no tool the harness has
- verify: stderr(text="has no tool for")
- code: `farrier/farrier/home_guards.py::watched_tools` @b7d19e02ce59

### method: guard_group
- sig: `guard_group(guard: Guard, harness: str, home: Path) -> dict[str, Any]`
- does: return the hook group that runs the guard, with a matcher in the harness's tool names and a `timeout` and `statusMessage` when the record has them
- verify: contents(subject="installed guard group", text="matcher")
- code: `farrier/farrier/home_guards.py::guard_group` @92afdc99f1d8

### method: guard_entries
- sig: `guard_entries(config: HomeConfig, home: Path) -> list[Entry]`
- does: return one merged home entry per guard and harness, leaving out a bridged harness and a guard whose `not_on` names the harness
- verify: count(subject="guard entries per harness", equals=1)
- code: `farrier/farrier/home_guards.py::guard_entries` @5f75adf0b50a

### method: excepted_guards
- sig: `excepted_guards(config: HomeConfig) -> list[str]`
- does: return one line per guard a table selects and the guard's `not_on` excludes
- verify: stdout(text="Left out on codex")
- code: `farrier/farrier/home_guards.py::excepted_guards` @cbaaa0a32c58

### method: bridge_text
- sig: `bridge_text(guards: list[Guard], harness: str, home: Path) -> str`
- does: return the plugin that calls each guard's installed command before a tool the guard watches runs, marked as generated on its first line
- verify: contents(subject="guard bridge", text="// generated by farrier")
- code: `farrier/farrier/home_guards.py::bridge_text` @7b6d97e2c366

### method: guard_files
- sig: `guard_files(config: HomeConfig, home: Path) -> dict[Path, Rendered]`
- does: return the bridge of a harness with no command hooks when a guard serves it
- verify: contents(subject="guard bridge", text="// generated by farrier")
- does: return every file of each guard some harness installs, leaving out its `tests` and `__pycache__` folders
- verify: count(subject="installed guard folders", equals=1)
- does: keep each script's executable bit
- verify: count(subject="executable guard scripts", equals=1)
- does: mark the installed record as generated, so farrier owns the folder
- verify: contents(subject="installed guard record", text="# generated by farrier")
- code: `farrier/farrier/home_guards.py::guard_files` @7968f66becb6

### method: approval_keys
- sig: `approval_keys(path: Path) -> dict[str, str]`
- does: map each command in the Codex guard file to the key Codex records its approval under, the resolved file path, `pre_tool_use`, the group's position and the handler's position
- verify: contents(subject="approval key", text=":pre_tool_use:")
- code: `farrier/farrier/home_guards.py::approval_keys` @e14899e52074

### method: pending_guards
- sig: `pending_guards(config: HomeConfig, home: Path) -> list[str]`
- does: return each installed Codex guard with no `trusted_hash` under its key in the `hooks.state` table of `~/.codex/config.toml`
- verify: count(subject="guards with no approval", equals=1)
- code: `farrier/farrier/home_guards.py::pending_guards` @429b547fcdf2

### method: check_pending
- sig: `check_pending(config: HomeConfig, home: Path) -> int`
- does: print one line per pending guard, then how to approve them
- returns: `1` when a guard is pending, and `0` otherwise
- verify: stdout(text="pending approval")
- code: `farrier/farrier/home_guards.py::check_pending` @de8ee4315339

### method: codex_guards_move
- sig: `codex_guards_move(home: Path, intended: list[Entry]) -> bool`
- does: return whether the intended entries differ from what `~/.codex/hooks.json` holds
- verify: count(subject="moved Codex guard files", equals=1)
- code: `farrier/farrier/home_guards.py::codex_guards_move` @ae0b737a5739
