---
type: format
slug: home-config
title: Home config file (config.toml)
---
# Home config file (config.toml)

The shared, machine-local settings file both `farrier` and `workhorse` read and write — currently
holding the [library directory](concepts/library-directory.md) candidate and the local
`stablemate` checkout path. Read by `read_config`, written key-by-key by `_write_config_key`
(shared by `write_library_dir` and `write_stablemate_dir`), and surfaced to the user by
[`farrier config show`](farrier.md#config).

- file: `config.toml` at `CONFIG_PATH` (OS-appropriate, via `platformdirs.user_config_dir("farrier")`
  — e.g. `~/.config/farrier/config.toml` on Linux, `~/Library/Application Support/farrier/config.toml`
  on macOS, `%APPDATA%\farrier\config.toml` on Windows)
- code: `farrier/farrier/install.py::read_config`

## Fields

A flat TOML table of string values. `_write_config_key` merges into whatever keys already exist
rather than replacing the file, so any key is legal — these two are the ones farrier/workhorse
actually read back.

### library_dir
- type: `string` — required: no — default: unset

The [library directory](concepts/library-directory.md) resolution's third-precedence candidate
(after `--library` and `$FARRIER_LIBRARY_DIR`). Written by
[`farrier config set-library <path>`](farrier.md#config) via `write_library_dir`, after the path
is validated with `is_library_dir` (must contain `library/` and `packs/`).

### stablemate_dir
- type: `string` — required: no — default: unset

The local `stablemate` checkout path (holds the workhorse runtime and the farrier installer
source) used for `SRC=1` local-source runs of the generated agent launcher. Written by
[`farrier config set-stablemate <path>`](farrier.md#config) via `write_stablemate_dir` — unlike
`library_dir`, the path is persisted as-is with no directory-shape validation. Read back by
`resolve_stablemate_dir`, which returns `None` when the key is unset.

- code: `farrier/farrier/install.py::write_stablemate_dir`

## Reading and writing

- `read_config()` — returns `{}` if `CONFIG_PATH` does not exist; otherwise parses the file with
  `tomllib.load`.
- `_write_config_key(key, value)` — creates `CONFIG_PATH`'s parent directory if needed, reads the
  existing config via `read_config`, sets `key = value` in the merged mapping, then rewrites the
  **whole file** from that mapping as `key = "escaped-value"` lines (backslashes and double quotes
  escaped) — so a single-key write preserves every other key already stored.

- code: `farrier/farrier/install.py::_write_config_key`
