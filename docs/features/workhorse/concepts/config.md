---
type: concept
slug: config
title: stablemate config file
---
# stablemate config file

The toolchain's small persistent settings file — **one** TOML file at
`~/.config/stablemate/config.toml`, shared by workhorse and farrier, holding `library_dir`,
`stablemate_dir`, `base_dir`, a `[power.<tier>.<backend>]` model/effort table, a per-backend
`[default.<backend>]` fallback table, and a per-harness `[harness.<backend>].env` table. Read and
written by [workhorse config](../workhorse.md#config); the `power` table is consumed at run time by
`resolve_power` to satisfy a node's [`power`](../workflow-format.md#power) tier, and the `default`
table by `resolve_backend_default` to fill whatever that left unset.

It lives in `stablemate-core`, not in workhorse. It used to be one file *per tool*, which meant
`workhorse config set-base` and `farrier config set-base` wrote to different files and then
disagreed about `library_dir`/`stablemate_dir`/`base_dir` — the installer and the runner
disagreeing about where the library is, silently. The legacy per-tool files are still **read** when
the unified one is absent; the first write migrates them.

- code: `core/stablemate_core/config.py`

## Location

`config_path()` resolves the file's path:

- **`$STABLEMATE_CONFIG`** env var, if set (expanded via `Path.expanduser()`) — an explicit
  override.
- otherwise **`$WORKHORSE_CONFIG`**, still honoured so an existing override does not have to be
  renamed in lockstep with the unification.
- otherwise the platform-appropriate default via `platformdirs.user_config_dir("stablemate")`:
  `~/Library/Application Support/stablemate/config.toml` (macOS),
  `%APPDATA%\stablemate\config.toml` (Windows), `~/.config/stablemate/config.toml` (Linux).

`legacy_config_paths()` returns the pre-unification per-tool paths (`workhorse` and `farrier`'s own
`user_config_dir` files) that `load_config` falls back to.

- code: `core/stablemate_core/config.py::config_path`

## The file carries a schema version

`CONFIG_VERSION` (currently `1`) is stamped into the file under `config_version` on every write, and
is deliberately **not** core's package version — it is bumped only when a key is renamed, moved, or
changes meaning.

The guard belongs on the file rather than the code because two pipx venvs each carry their own copy
of this module and no packaging arrangement can make them agree: an older tool must not silently
misread a file a newer one wrote.

- `check_config_version(cfg=None) -> int` raises `ConfigVersionError` when the file is newer than
  the running code understands. It is for a CLI to call at **startup**, and is deliberately not
  called from `load_config` — a read of a too-new file warns (once per version, not once per call,
  since `resolve_power` re-reads per node) and proceeds.
- A **write** to a too-new file refuses with `ConfigVersionError` rather than clobbering keys it
  cannot interpret.
- An unversioned file is treated as version 1.
- Migrating forward backs the file up to `<name>.v<n>.bak` first — a migration is a one-way door.

- code: `core/stablemate_core/config.py::check_config_version`

## load_config

Reads the whole file into a plain dict. Returns `{}` if the file doesn't exist (no error) — an
unconfigured toolchain behaves as an empty config rather than failing. A corrupt or unreadable file
(`OSError`, `TOMLDecodeError`) also reads as `{}`: it must not take down an unattended run.

When the unified file is absent, it merges the legacy per-tool files instead, in `workhorse`,
`farrier` order. That fallback applies **only** to the default path — an explicit
`$STABLEMATE_CONFIG` means what it says.

`read_config` is an alias of this function, farrier's spelling of the same call, aliased rather than
renamed so neither caller had to change.

- code: `core/stablemate_core/config.py::load_config`

## get_config_value

Reads one value out of the loaded config (or a `cfg` dict passed in, else `load_config()`) by a
dot-path `name` (e.g. `power.high.claude` reaches `[power.high.claude]`). Walks `name.split(".")`
as successive dict lookups; returns `None` as soon as a segment is missing or a non-dict is
indexed — an unresolved path is silent, never an error. Used directly by
[workhorse config get](../workhorse.md#config).

- code: `core/stablemate_core/config.py::get_config_value`

## write_config_key

Persists a single top-level `key`/`value` pair, preserving every other key already in the file:
loads the current config, migrates it forward if needed, sets `cfg[key] = value`, stamps
`config_version`, and serialises the whole dict with `tomli_w` — a real TOML writer, so nested
tables survive a write.

It used to rewrite the file as `key = "value"` lines built by hand, which stringified every nested
table it did not understand: one `config set-base` turned `[power.*]` into a Python-repr string,
after which `resolve_power` saw a `str` where it expected a table and silently returned an empty
mapping — every node quietly falling back to the harness's default model, with no error anywhere.

Creates the config directory if absent. Refuses with `ConfigVersionError` when the file on disk is
newer than `CONFIG_VERSION`. Used by
[workhorse config set-library / set-stablemate / set-base](../workhorse.md#config), and by the
typed helpers `write_library_dir`, `write_stablemate_dir` and `write_base_dir` that wrap it.

- code: `core/stablemate_core/config.py::write_config_key`

## resolve_power

Resolves a node's abstract [`power`](../workflow-format.md#power) tier (`high`/`medium`/`low`) plus
the active backend name to a concrete `PowerMapping`. A `power` of `None`/`""` short-circuits to an
empty mapping (no override). Otherwise looks up `power.<power>.<backend>`, falling back to
`power.<power>.default` when no backend-specific table exists; any missing/non-dict step along the
way (no `power` table, no such tier, no matching backend/default table) yields an empty mapping
rather than an error — an unconfigured tier leaves the node's model/effort unset so the backend's
own default applies.

- **Input:** `power: str | None`, `backend: str`, `cfg: dict | None` (defaults to `load_config()`).
- **Output:** `PowerMapping(model, effort)` — each field `None` unless the config supplies a
  non-empty string.
- code: `core/stablemate_core/config.py::resolve_power`

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
- code: `core/stablemate_core/config.py::resolve_backend_default`

## resolve_harness_env

Resolves `[harness.<backend>].env` to a plain `dict[str, str]` of environment variables to add to
that harness's subprocess — e.g. `env = { OPENCODE_DISABLE_AUTOCOMPACT = "1" }`. Scoped per
**harness**, not per power tier: what a CLI needs in its environment is a property of that CLI.
A missing or mistyped table yields `{}`, and a non-string value is dropped rather than coerced —
an environment is strings, and quietly stringifying a bare TOML `1` would hide the config error.

- **Input:** `backend: str`, `cfg: dict | None` (defaults to `load_config()`).
- **Output:** `dict[str, str]`.
- code: `core/stablemate_core/config.py::resolve_harness_env`

## PowerMapping

The frozen dataclass `resolve_power` and `resolve_backend_default` return: `model: str | None =
None`, `effort: str | None = None`. Both fields default to unset so an unconfigured tier/backend
combination is a no-op override, not an error.

- code: `core/stablemate_core/config.py::PowerMapping`

## Consumers

- [`workhorse config`](../workhorse.md#config) — `show`/`get`/`list`/`set-*`.
- [`run_agent`](run-agent.md) — `resolve_power` and `resolve_backend_default` per agent turn.
- the [agent backend](agent-backend.md) — `resolve_harness_env` for the harness subprocess's
  environment.
- `stablemate_core.discovery` and farrier's installer — `library_dir`/`stablemate_dir`/`base_dir`,
  which is the pair of readers the unification exists for.
