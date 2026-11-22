story: none
date: 2026-11-22
elements: InstallUser

A `[user_library.codex]` table takes settings, as the Claude and Copilot tables do. Codex keeps its settings in
`~/.codex/config.toml`, the file that also holds its MCP servers and the projects the person trusted. Farrier merges
each top-level key of a library settings file into that TOML and leaves every other key, table and comment in place.

A library settings file stays JSON for every harness, so one loader reads them all. A key that holds an object, such
as `features`, becomes a TOML table, and farrier owns that table whole. A person who adds a key of their own under it
sees the next install stop with the conflict, as it does for a nested object in Claude's settings.

OpenCode still takes no settings, because its config is the JSONC file farrier only reads.
