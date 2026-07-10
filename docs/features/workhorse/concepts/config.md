---
type: concept
slug: config
title: workhorse config file
---
# workhorse config file

Workhorse's own small persistent settings file — a TOML file holding `library_dir`,
`stablemate_dir`, a `[power.<tier>.<backend>]` model/effort table, and a per-backend
`[default.<backend>]` model/effort fallback table. Read and written by
[workhorse config](../workhorse.md#config); the `power` table is consumed at run time by
`resolve_power` to satisfy a workflow node's [`power:`](../workflow-format.md) tier, and the
`default` table by `resolve_backend_default` to fill whatever that left unset. The
`library_dir` key is also read at run time — via `get_config_value` — by [`workhorse
run`](../workhorse.md#run)'s `_resolve_library_dir`, which resolves a bare workflow NAME against
the prompt library.

- code: `workhorse/workhorse/config.py`

## Location

`config_path()` resolves the file's path:

- **`$WORKHORSE_CONFIG`** env var, if set (expanded via `Path.expanduser()`) — an explicit override.
- otherwise the platform-appropriate default via `platformdirs.user_config_dir("workhorse")`:
  `~/Library/Application Support/workhorse/config.toml` (macOS), `%APPDATA%\workhorse\config.toml`
  (Windows), `~/.config/workhorse/config.toml` (Linux).

- code: `workhorse/workhorse/config.py::config_path`

## load_config

Reads the whole file into a plain dict. Returns `{}` if the file doesn't exist (no error) —
an unconfigured workhorse behaves as an empty config rather than failing. Parses with
`tomllib.loads`; a malformed TOML file raises `tomllib.TOMLDecodeError` uncaught.

- code: `workhorse/workhorse/config.py::load_config`

## get_config_value

Reads one value out of the loaded config (or a `cfg` dict passed in, else `load_config()`) by a
dot-path `name` (e.g. `power.high.claude` reaches `[power.high.claude]`). Walks `name.split(".")`
as successive dict lookups; returns `None` as soon as a segment is missing or a non-dict is
indexed — an unresolved path is silent, never an error. Used directly by
[workhorse config get](../workhorse.md#config) and internally by `resolve_power`.

- code: `workhorse/workhorse/config.py::get_config_value`

## write_config_key

Persists a single top-level string `key`/`value` pair, preserving every other key already in the
file. Loads the current config via `load_config()`, sets `cfg[key] = value`, then rewrites the
**whole file** from that dict as `key = "value"` lines (one per top-level key, value
backslash/quote-escaped) — this only round-trips flat, top-level string keys; it does not
preserve nested `[table]` sections written by hand, so it must not be used to touch the
`power` table. Creates the config directory (`path.parent.mkdir(parents=True, exist_ok=True)`)
if absent. Used by [workhorse config set-library / set-stablemate](../workhorse.md#config).

- code: `workhorse/workhorse/config.py::write_config_key`

## resolve_power

Resolves a workflow node's abstract [`power:`](../workflow-format.md) tier (`high`/`medium`/`low`)
plus the active backend name to a concrete `PowerMapping`. A `power` of `None`/`""` short-circuits
to an empty mapping (no override). Otherwise looks up `power.<power>.<backend>`, falling back to
`power.<power>.default` when no backend-specific table exists; any missing/non-dict step along the
way (no `power` table, no such tier, no matching backend/default table) yields an empty mapping
rather than an error — an unconfigured tier leaves the node's model/effort unset so the backend's
own default applies.

- **Input:** `power: str | None`, `backend: str`, `cfg: dict | None` (defaults to `load_config()`).
- **Output:** `PowerMapping(model, effort)` — each field `None` unless the config supplies a
  non-empty string.
- code: `workhorse/workhorse/config.py::resolve_power`

## resolve_backend_default

Resolves the active backend name to the top-level `[default.<backend>]` table — the configurable
counterpart of a backend's hardcoded `default_model`. Consumed by `_resolve_power_settings` as the
last config-side fallback: it fills whatever the node's power tier (or the absence of one) left
unset, so power-less nodes stop silently falling through to the harness's own auto-picked model.
Any missing/non-dict step (no `default` table, no such backend section) yields an empty mapping
rather than an error.

- **Input:** `backend: str`, `cfg: dict | None` (defaults to `load_config()`).
- **Output:** `PowerMapping(model, effort)` — each field `None` unless the config supplies a
  non-empty string.
- code: `workhorse/workhorse/config.py::resolve_backend_default`

## PowerMapping

The frozen dataclass `resolve_power` and `resolve_backend_default` return: `model: str | None =
None`, `effort: str | None = None`. Both fields default to unset so an unconfigured tier/backend
combination is a no-op override, not an error.

- code: `workhorse/workhorse/config.py::PowerMapping`
