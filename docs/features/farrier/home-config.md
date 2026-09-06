---
type: format
slug: home-config
title: Home config file (config.toml)
---
# Home config file (config.toml)

The shared, machine-local settings file every stablemate tool reads and writes — holding the
overlay [library directory](concepts/library-directory.md) candidate, the base-library path, the
local `stablemate` checkout path, and the per-backend `power`/`harness` tables workhorse resolves
against. It lives in `stablemate_core`, not in farrier: the keys are shared, so workhorse
inheriting a farrier-set `library_dir` is the point rather than a leak. Read by `load_config`
(farrier spells the same function `read_config`; it is an alias, not a second implementation),
written key-by-key by `write_config_key`, and surfaced to the user by
[`farrier config show`](farrier.md#config).

- file: `config.toml` under `platformdirs.user_config_dir("stablemate")` — e.g.
  `~/.config/stablemate/config.toml` on Linux, `~/Library/Application Support/stablemate/config.toml`
  on macOS, `%APPDATA%\stablemate\config.toml` on Windows. `$STABLEMATE_CONFIG` (or the
  pre-unification `$WORKHORSE_CONFIG`) overrides the path outright.
- code: `farrier/farrier/_vendor/stablemate_core/config.py::load_config`
- code: `farrier/farrier/_vendor/stablemate_core/config.py`
- detail: [configuration version guard](concepts/config-version-guard.md)
- detail: [power mapping](concepts/power-mapping.md)
- detail: [profile selection](concepts/profile-selection.md)

## Fields

A TOML table. `write_config_key` merges into whatever keys already exist rather than replacing the
file, so any key is legal — these are the ones the tools actually read back. (`power.*` and
`harness.*` are nested tables owned by workhorse; see workhorse's own docs for their shape.)

### library_dir
- type: `string` — required: no — default: unset

The [library directory](concepts/library-directory.md) resolution's third-precedence *overlay*
candidate (after `--library` and `$FARRIER_LIBRARY_DIR`). Written by
[`farrier config set-library <path>`](farrier.md#config) via `write_library_dir`, after the path is
validated with `is_library_dir` (must contain `library/`).

### base_dir
- type: `string` — required: no — default: unset

An explicit on-disk path to the *base* library content — the persisted form of
`$STABLEMATE_BASE_DIR`. Written by `write_base_dir`. Consulted by `base_library_dir()` second,
after the env var and before a `stablemate_dir`-derived checkout path; a configured-but-invalid
value is skipped rather than raised on, because the base is additive and failing soft keeps an
overlay-only setup working.

### stablemate_dir
- type: `string` — required: no — default: unset
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_stablemate_dir`

### worktree_dir
- type: `string` — required: no — default: unset
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_worktree_dir`

### user_library
- type: `table of tables` — required: no — default: absent (nothing is installed at user scope)
- code: `farrier/farrier/user_library.py::user_library_tables`

### config_version
- type: `integer` — required: no — default: absent (treated as version 0)

The schema version this file was last written under, stamped on **every** write. It is not the
`stablemate-core` package version: coupling the two would bump the schema on every patch release and
lock out every tool that had not upgraded yet. A file newer than the running build's
`CONFIG_VERSION` makes `write_config_key` refuse with `ConfigVersionError` rather than clobber it —
the one guard that holds however the tools were installed, because it defends the file rather than
trusting the code that reaches it. An older file is carried forward by `_migrate_forward` before the
write lands, so a write never mixes schemas.

## Reading and writing

- `load_config()` — returns the parsed unified file if it exists. If it does not, and the path was
  **not** named explicitly, the pre-unification per-tool files (`user_config_dir("workhorse")` then
  `user_config_dir("farrier")`, merged in that order) are read as a fallback; an explicitly named
  `$STABLEMATE_CONFIG` that happens not to exist means "this file", not "and also whatever is in
  `~/.config/workhorse`". A corrupt or unreadable file parses to `{}` rather than raising — an
  unattended run must not die on a bad config, and every caller already handles "nothing
  configured".
- `write_config_key(key, value)` — creates the config directory if needed, reads the existing config
  via `load_config`, applies the version guard/migration above, sets `key = value`, stamps
  `config_version`, and rewrites the whole file with a real TOML writer (`tomli_w`). When only
  legacy files exist, this is what merges them into the unified path. Using a TOML writer is
  load-bearing: the hand-rolled `f'{k} = "{v}"'` it replaced stringified nested tables, so a single
  `config set-base` turned `[power.*]` into a Python-repr string and every node silently fell back
  to the default model with no error anywhere.

- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_config_key`
- detail: [config write documentation contexts](concepts/config-write-context.md)

## Methods

### legacy_config_paths
- sig: `legacy_config_paths() -> list[Path]`
- does: returns the legacy workhorse and farrier config paths in migration order
- returns: one path for each legacy application config location
- verify: count(subject="legacy config paths", equals=2)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::legacy_config_paths`

### config_path
- sig: `config_path() -> Path`
- does: uses `$STABLEMATE_CONFIG`, then `$WORKHORSE_CONFIG`, then the platform shared config path
- returns: the expanded path selected for reads and writes
- verify: json_path(path="$.config_path", matches="config\\.toml$")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::config_path`

### config_version_of
- sig: `config_version_of(cfg: dict[str, Any]) -> int`
- does: treats an absent, boolean, non-integer, or below-one version as schema version 1
- returns: the integer schema version declared by the mapping
- verify: json_path(path="$.config_version", equals=1)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::config_version_of`

### check_config_version
- sig: `check_config_version(cfg: dict[str, Any] | None = None) -> int`
- does: checks the supplied config or loaded config against the supported schema
- raises: `ConfigVersionError` when the config declares a newer schema
- returns: the supported schema version when the config is acceptable
- verify: exit_status(code=1)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::check_config_version`

### profile_names
- sig: `profile_names(cfg: dict[str, Any] | None = None) -> list[str]`
- does: reads names from the config's `profiles` table
- returns: names sorted lexicographically, or an empty list when none are defined
- verify: count(subject="sorted profile names", equals=1)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::profile_names`

### select_profile
- sig: `select_profile(cfg: dict[str, Any] | None, name: str) -> dict[str, Any]`
- does: returns the original config unchanged when `name` is empty
- does: replaces top-level resolution tables with the named profile mapping
- raises: `UnknownProfileError` when the named profile is not defined
- returns: the selected profile mapping
- verify: json_path(path="$.power.high.claude.model", equals="haiku")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::select_profile`

### profile_backends
- sig: `profile_backends(profile: dict[str, Any]) -> list[str]`
- does: collects backend names from tier tables and the profile default table
- does: excludes each tier's `default` fallback key
- returns: distinct backend names sorted lexicographically
- verify: count(subject="profile backend names", equals=1)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::profile_backends`

### profile_has_backend
- sig: `profile_has_backend(profile: dict[str, Any], backend: str) -> bool`
- does: reports true when a tier backend, tier fallback, or default backend can provide a mapping
- returns: false when no mapping can resolve the backend
- verify: json_path(path="$.profile_has_backend", equals=true)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::profile_has_backend`

### resolve_power
- sig: `resolve_power(power: str | None, backend: str, cfg: dict[str, Any] | None = None) -> PowerMapping`
- does: returns an empty mapping when no power tier, tier table, backend table, or fallback exists
- does: chooses the backend table before the tier's `default` fallback
- returns: the selected non-empty `model` and `effort` strings
- verify: json_path(path="$.model", equals="haiku")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::resolve_power`

### resolve_backend_default
- sig: `resolve_backend_default(backend: str, cfg: dict[str, Any] | None = None) -> PowerMapping`
- does: reads the backend mapping from the top-level `default` table
- returns: an empty mapping when the table or backend entry is absent or malformed
- verify: json_path(path="$.model", equals="opus")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::resolve_backend_default`

### resolve_harness_env
- sig: `resolve_harness_env(backend: str, cfg: dict[str, Any] | None = None) -> dict[str, str]`
- does: selects `harness.<backend>.env`
- does: drops non-string keys and values instead of coercing them
- returns: the valid string environment mapping, or `{}` when absent or malformed
- verify: json_path(path="$.OPENCODE_DISABLE_AUTOCOMPACT", equals="1")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::resolve_harness_env`

### resolve_default_cli
- sig: `resolve_default_cli(cfg: dict[str, Any] | None = None) -> str`
- does: reads and trims the configured `default_cli` value
- returns: the lower-case configured CLI, or `claude` when absent, empty, or non-string
- verify: json_path(path="$.default_cli", equals="claude")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::resolve_default_cli`

### write_default_cli
- sig: `write_default_cli(name: str) -> None`
- does: persists a trimmed, lower-case `default_cli` value
- returns: `None`
- verify: persists(subject="default_cli")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_default_cli`

### get_config_value
- sig: `get_config_value(name: str, cfg: dict[str, Any] | None = None) -> Any`
- does: walks a dotted key path through the selected config mapping
- returns: the value at the path, or `None` when a segment is absent or not a mapping
- verify: json_path(path="$.value", equals="configured")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::get_config_value`

### write_library_dir
- sig: `write_library_dir(path: Path) -> None`
- does: persists the overlay library path under `library_dir`
- returns: `None`
- verify: persists(subject="library_dir")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_library_dir`
- detail: [config write documentation contexts](concepts/config-write-context.md)

### write_stablemate_dir
- sig: `write_stablemate_dir(path: Path) -> None`
- does: persists the stablemate checkout path under `stablemate_dir`
- returns: `None`
- verify: persists(subject="stablemate_dir")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_stablemate_dir`

### write_base_dir
- sig: `write_base_dir(path: Path) -> None`
- does: persists the base library path under `base_dir`
- returns: `None`
- verify: persists(subject="base_dir")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_base_dir`

### write_worktree_dir
- sig: `write_worktree_dir(path: Path) -> None`
- does: persists the parent directory for new worktrees without requiring it to exist
- returns: `None`
- verify: persists(subject="worktree_dir")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_worktree_dir`

### resolve_stablemate_dir
- sig: `resolve_stablemate_dir() -> Path | None`
- does: reads the configured `stablemate_dir` value
- returns: its expanded absolute path, or `None` when unset or not a non-empty string
- verify: json_path(path="$.stablemate_dir", equals="/checkout")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::resolve_stablemate_dir`

### resolve_worktree_dir
- sig: `resolve_worktree_dir() -> Path | None`
- does: reads the configured `worktree_dir` value without requiring the directory to exist
- returns: its expanded absolute path, or `None` when unset or not a non-empty string
- verify: json_path(path="$.worktree_dir", equals="/worktrees")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::resolve_worktree_dir`
