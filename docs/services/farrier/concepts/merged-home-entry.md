---
type: concept
slug: merged-home-entry
title: Merged home entry
---
# Merged home entry

A merged home entry is one named value farrier keeps inside a file another program also writes, so
the same MCP servers reach Claude Code, Codex and OpenCode while everything else in those files stays theirs.
The Claude entries live under `mcpServers` in `~/.claude.json`, the Codex entries live under
`mcp_servers` in `~/.codex/config.toml`, and the OpenCode entries live under `mcp` in
`~/.config/opencode/opencode.json`. The server definitions are [tool server records](../formats/tool-server-record.md),
and the [home entry ledger](../formats/home-entry-ledger.md) records which entries farrier installed.
A `[user_library.<harness>]` table in the [user library](user-library.md) selects them.
A [home guard](home-guard.md) is a merged home entry too, in the settings file each harness reads its hooks from.

- rule: one record in the library renders to both harnesses, so a server is declared once and spelled by each harness's dialect
- rule: farrier never changes or removes a value it did not install, and the ledger is what tells its entries from everyone else's
- rule: an entry farrier did not install, holding a different value under an intended name, stops the install before any write and is named without its value
- rule: an entry farrier did not install that matches the library stays and is not adopted, so dropping the server from the library never deletes it
- rule: comments and unrelated keys in a shared file survive an install, and removing the last server of a Codex config returns the file to its earlier bytes
- rule: empty `args` or `env` compare equal to absent ones, because a harness may write or omit them
- rule: `--check` writes nothing and prints entry names only, because an `env` value can be a secret
- rule: each edit reads the file, changes one entry and renames a new file into place, so a harness writing at the same moment can lose only the one write that the next `--check` reports
- rule: farrier never writes `opencode.jsonc`, because that file is the user's and comments do not survive a rewrite, so OpenCode's entries go in `opencode.json`, which OpenCode merges over it
- rule: a selected name that `opencode.jsonc` holds with another value stops the install, because the `opencode.json` entry would silently replace the user's
- rule: a home with no selected server gets no ledger and no shared file
- rule: servers are stdio commands, because every server in a home today is a local program
- rule: Copilot takes no server, because its home setup is skills only
- rule: servers belong to a home and not to a repository, so a pack's `mcp:` key takes effect at user scope only and an `mcp:` key in `agents.yml` is a stray key

## Methods

### method: load_tool_server
- sig: `load_tool_server(name: str) -> ToolServer`
- does: read `library/mcp/<name>.yml` from the highest library layer holding it
- raises: `SystemExit` naming the available servers when no layer holds the record
- verify: stderr(text="unknown MCP server")
- raises: `SystemExit` naming the file when a key is unknown or `command` is missing
- verify: stderr(text="unknown keys")
- code: `farrier/farrier/home_entries.py::load_tool_server` @451a58ecca5e

### method: tool_server_names
- sig: `tool_server_names(table: Selection) -> set[str]`
- does: return the servers a harness table selects, directly in `mcp` or through its packs
- verify: count(subject="selected server names", equals=1)
- code: `farrier/farrier/home_entries.py::tool_server_names` @f6f1ca57b06b

### method: user_entries
- sig: `user_entries(home: HomeConfig) -> list[Entry]`
- does: spell every selected server in the dialect of the harness whose table selected it
- raises: `SystemExit` when a table of a harness with no dialect names a server
- verify: exit_status(code=1)
- code: `farrier/farrier/home_entries.py::user_entries` @7f94d59cb214

### method: entry_drift
- sig: `entry_drift(home: Path, intended: list[Entry], ledger: Ledger) -> list[EntryDrift]`
- does: classify each difference as `missing`, `changed` for an owned entry that holds another value, `foreign` for an unowned one or for a differing entry in the file it overrides, or `extra` for an owned entry no longer intended
- verify: count(subject="entry drift kinds", equals=4)
- code: `farrier/farrier/home_entries.py::entry_drift` @ab56759e958b

### method: check_entries
- sig: `check_entries(home: Path, intended: list[Entry], regenerate: str) -> int`
- does: print one line per drifted entry with the repair command, and return `1`, or return `0` when nothing drifted
- verify: exit_status(code=1)
- code: `farrier/farrier/home_entries.py::check_entries` @8616903d89b9

### method: refuse_foreign_entries
- sig: `refuse_foreign_entries(home: Path, intended: list[Entry]) -> None`
- does: stop before any write when an intended name holds a value farrier did not install
- raises: `SystemExit` listing each entry by file and name
- verify: stderr(text="will not overwrite entries it did not install")
- code: `farrier/farrier/home_entries.py::refuse_foreign_entries` @0705a9be8f63

### method: install_entries
- sig: `install_entries(home: Path, intended: list[Entry]) -> int`
- does: record the entries about to be written in the ledger, write the drifted entries, delete the owned entries no longer intended, then record what remains and return how many changed
- verify: count(subject="changed entries", equals=1)
- code: `farrier/farrier/home_entries.py::install_entries` @5fbe653177e0

### method: read_entry_file
- sig: `read_entry_file(path: Path) -> EntryFile`
- does: open a `.json`, `.jsonc` or `.toml` config by suffix, an absent file reading as empty
- raises: `SystemExit` naming the file when it does not parse, with nothing written
- verify: stderr(text="cannot parse")
- code: `farrier/farrier/home_entries.py::read_entry_file` @14bdb7a4a2ac

### method: plain_json
- sig: `plain_json(text: str) -> str`
- does: return JSONC text as JSON, without its comments and trailing commas and with its strings untouched
- verify: count(subject="comments left in the parsed config", equals=0)
- code: `farrier/farrier/home_entries.py::plain_json` @9a9125e9cb9c

### method: replace_file
- sig: `replace_file(path: Path, text: str) -> None`
- does: swap the text in with one rename, following a symlink and keeping the file's mode, a new file getting mode `600`
- verify: count(subject="renames per write", equals=1)
- code: `farrier/farrier/home_entries.py::replace_file` @aa4ce15b04c5
