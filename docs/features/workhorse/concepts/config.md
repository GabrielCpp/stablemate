---
type: concept
slug: config
title: stablemate config file
---
# stablemate config file

The toolchain's small persistent settings file — **one** TOML file at
`~/.config/stablemate/config.toml`, shared by workhorse and farrier, holding `library_dir`,
`stablemate_dir`, `base_dir`, `worktree_dir`, `default_cli`, a `[power.<tier>.<backend>]` model/effort table, a per-backend
`[default.<backend>]` fallback table, a per-harness `[harness.<backend>].env` table, and any number of
named [`[profiles.<name>]`](#profiles) tables carrying a whole alternative set of the model
ones. Read and
written by [farrier config](../../farrier/farrier.md#config) — workhorse is a library and ships no
command of its own; the `power` table is consumed at run time by
`resolve_power` to satisfy a node's [`power`](../workflow-format.md#power) tier, and the `default`
table by `resolve_backend_default` to fill whatever that left unset.

It lives in `stablemate-core`, not in workhorse. It used to be one file *per tool*, which meant
each tool's own `config set-base` wrote to a different file and they then
disagreed about `library_dir`/`stablemate_dir`/`base_dir` — the installer and the runner
disagreeing about where the library is, silently. The legacy per-tool files are still **read** when
the unified one is absent; the first write migrates them.

- code: `workhorse/workhorse/_vendor/stablemate_core/config.py`

## Location

`config_path()` resolves the file's path:

- **`$STABLEMATE_CONFIG`** env var (`CONFIG_PATH_ENV`), if set (expanded via
  `Path.expanduser()`) — an explicit override.
  [`workhorse-<name> run --config PATH`](../workhorse.md#run) and
  [`farrier --config PATH config`](../../farrier/farrier.md#config) set it rather than
  threading a path: every reader and every writer resolves the file through `config_path()`
  itself, so one assignment moves all of them together, and a subprocess (a re-exec after a
  `control reload`, a tool the command shells out to) inherits the same answer instead of
  quietly reading the machine's own file.
- otherwise **`$WORKHORSE_CONFIG`**, still honoured so an existing override does not have to be
  renamed in lockstep with the unification.
- otherwise the platform-appropriate default via `platformdirs.user_config_dir("stablemate")`:
  `~/Library/Application Support/stablemate/config.toml` (macOS),
  `%APPDATA%\stablemate\config.toml` (Windows), `~/.config/stablemate/config.toml` (Linux).

`legacy_config_paths()` returns the pre-unification per-tool paths (`workhorse` and `farrier`'s own
`user_config_dir` files) that `load_config` falls back to.

- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::config_path`

## Additional API

The vendored module also exposes the following persistence and path helpers used by the shared
tooling.

### legacy_config_paths
- sig: `legacy_config_paths() -> list[Path]`
- returns: the historical workhorse and farrier config paths in that order
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::legacy_config_paths`

### config_version_of
- sig: `config_version_of(cfg: dict[str, Any]) -> int`
- returns: the declared positive integer schema version, or `1` for an absent, invalid, boolean, or non-positive value
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::config_version_of`

### write_library_dir
- sig: `write_library_dir(path: Path) -> None`
- does: persist the string form of `path` under `library_dir`
- returns: `None`
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::write_library_dir`

### write_stablemate_dir
- sig: `write_stablemate_dir(path: Path) -> None`
- does: persist the string form of `path` under `stablemate_dir`
- returns: `None`
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::write_stablemate_dir`

### write_base_dir
- sig: `write_base_dir(path: Path) -> None`
- does: persist the string form of `path` under `base_dir`
- returns: `None`
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::write_base_dir`

### write_worktree_dir
- sig: `write_worktree_dir(path: Path) -> None`
- does: persist the string form of `path` under `worktree_dir`
- returns: `None`
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::write_worktree_dir`

### resolve_stablemate_dir
- sig: `resolve_stablemate_dir() -> Path | None`
- returns: the expanded, resolved configured `stablemate_dir`, or `None` when it is unset or not a string
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::resolve_stablemate_dir`

### resolve_worktree_dir
- sig: `resolve_worktree_dir() -> Path | None`
- returns: the expanded, resolved configured `worktree_dir`, or `None` when it is unset or not a string
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::resolve_worktree_dir`

### read_config
- sig: `read_config() -> dict[str, Any]`
- does: provide the `load_config` behavior under farrier's alias
- returns: the effective config mapping
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::read_config`

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

- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::check_config_version`

## load_config

Reads the whole file into a plain dict. Returns `{}` if the file doesn't exist (no error) — an
unconfigured toolchain behaves as an empty config rather than failing. A corrupt or unreadable file
(`OSError`, `TOMLDecodeError`) also reads as `{}`: it must not take down an unattended run.

When the unified file is absent, it merges the legacy per-tool files instead, in `workhorse`,
`farrier` order. That fallback applies **only** to the default path — an explicit
`$STABLEMATE_CONFIG` means what it says.

`read_config` is an alias of this function, farrier's spelling of the same call, aliased rather than
renamed so neither caller had to change.

- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::load_config`

## get_config_value

Reads one value out of the loaded config (or a `cfg` dict passed in, else `load_config()`) by a
dot-path `name` (e.g. `power.high.claude` reaches `[power.high.claude]`). Walks `name.split(".")`
as successive dict lookups; returns `None` as soon as a segment is missing or a non-dict is
indexed — an unresolved path is silent, never an error. Used by
`stablemate_core.discovery` to read `base_dir`/`stablemate_dir` without caring whether either is
set.

- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::get_config_value`

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
[farrier config set-library / set-stablemate / set-base / set-worktree](../../farrier/farrier.md#config),
and by the typed helpers `write_library_dir`, `write_stablemate_dir`, `write_base_dir` and
`write_worktree_dir` that wrap it.

- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::write_config_key`
- detail: [config write documentation contexts](../../farrier/concepts/config-write-context.md)

## profiles

A `[profiles.<name>]` table holds a whole alternative set of the model tables — its own
`power`, `default` and `default_cli` — under one name, so "which set of models this run
buys" is a persistent object selected per run
([`run --profile <name>`](../workhorse.md#run)) rather than an edit to the one file every
run on the machine shares. Editing that file to make one run cheaper moved *every* run,
including the six-day one already going, and left no record of what the finished run
actually bought.

A profile **replaces** the top-level tables; it does not layer over them. Inheriting was
rejected because power tiers are opaque strings: no schema says which tiers exist, so "the
profile did not mention `smart`, therefore it means the machine's `smart`" is a guess the
config cannot state and the operator cannot see. What stays outside a profile stays outside
for free — `[harness.<backend>].env`, `library_dir`, `stablemate_dir`, `base_dir` and
`worktree_dir` are resolved from the *unnarrowed* config, because they are properties of the
machine, not of a model set.

```toml
[profiles.cheap.power.high.claude]
model = "sonnet"

[profiles.cheap.default.claude]
model = "haiku"
```

- `PROFILES_KEY` — `"profiles"`, the top-level key.
- `profile_names(cfg=None) -> list[str]` — the names defined, sorted; empty when there are
  none.
`select_profile(cfg, name) -> dict` is the seam between profile selection and model resolution.
It hands the resulting config to [`resolve_power`](#resolve_power) and
[`resolve_backend_default`](#resolve_backend_default), so those functions need no notion of
profiles. Unknown names fail during startup, where reporting the mistake is safe; silently falling
back to the top-level tables could otherwise run unattended on the wrong models.

- consistency: config-profile — selecting a named profile returns that profile's own table without overlaying the
  top-level model tables
- consistency: config-profile — selecting an empty profile name returns the config unchanged
- consistency: config-profile — selecting an undefined profile raises `UnknownProfileError` naming the requested
  profile and the known alternatives
- `profile_backends(profile) -> list[str]` — every backend name the narrowed config keys its
  model tables by, sorted (the per-tier `default` fallback is not one). **Nothing is
  validated here**: core knows no backend registry, so a misspelling is reported at the
  boundary that resolves the adapter, where every other bad backend name already is.
- `profile_has_backend(profile, backend) -> bool` — whether the narrowed config resolves any
  model at all for that backend: some tier names it, some tier carries the `default`
  fallback, or `[default.<backend>]` does. False is the two-independent-axes misuse — an
  opencode-only profile selected with `--cli claude` — which
  [`run`](../workhorse.md#run) refuses at the boundary rather than letting the run spend a
  week on the harness's own default model.

There is **no writer**. A profile is a nested table and
[`write_config_key`](#write_config_key) sets one top-level key, so profiles are authored by
editing the file; [`farrier config show --profile <name>`](../../farrier/farrier.md#config)
reads one back.

- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::select_profile`
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::profile_names`
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::profile_backends`
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::profile_has_backend`
- tests: `workhorse/tests/test_model_resolution.py::test_a_profile_replaces_the_top_level_tables`
- tests: `workhorse/tests/test_model_resolution.py::test_without_a_profile_nothing_is_narrowed`
- tests: `workhorse/tests/test_run_options.py::test_an_unknown_profile_is_refused_before_the_first_state`
- tests: `workhorse/tests/test_run_options.py::test_a_profile_with_nothing_for_the_chosen_backend_is_refused`

## resolve_power

Resolves a node's abstract [`power`](../workflow-format.md#power) tier (`high`/`medium`/`low`) plus
the active backend name to a concrete `PowerMapping`. A `power` of `None`/`""` short-circuits to an
empty mapping (no override). Otherwise looks up `power.<power>.<backend>`, falling back to
`power.<power>.default` when no backend-specific table exists; any missing/non-dict step along the
way (no `power` table, no such tier, no matching backend/default table) yields an empty mapping
rather than an error — an unconfigured tier leaves the node's model/effort unset so the backend's
own default applies.

- **Input:** `power: str | None`, `backend: str`, `cfg: dict | None` (defaults to
  `load_config()`; under a [profile](#profiles) the caller passes the narrowed table
  instead, which is why this function knows nothing about profiles).
- **Output:** `PowerMapping(model, effort)` — each field `None` unless the config supplies a
  non-empty string.
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::resolve_power`

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
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::resolve_backend_default`

## resolve_default_cli

Resolves the `default_cli` key — the agent CLI a run drives when neither `--cli` nor
`AGENT_CLI` names one, read from the selected [profile](#profiles) first and from the top
level after it — to a normalised (`strip().lower()`) backend name, or `BUILTIN_DEFAULT_CLI`
(`"claude"`) when the key is absent, empty, or not a string. It is the third rung of
[get_backend](get-backend.md)'s resolution order, and the reason the built-in default is a
*fallback* rather than the only answer: a flag's default is reachable only by editing workhorse, so
an operator whose machine is set up for one CLI would otherwise name it on every run of every
workflow.

**No name is validated here.** core knows no backend registry, so the check lands in
[get_backend](get-backend.md), which owns the list of real names and reports a misspelling with the
same `ValueError` a typo'd `--cli` gets. What this function does guarantee is that a malformed
value (a TOML integer, an empty string, a list) reads as *unset* rather than raising — it is read on
the way into unattended week-long runs, and a config that has gone wrong must degrade to the
built-in.

The key is additive, so it does not bump `CONFIG_VERSION`: an older tool that ignores it falls back
to the same built-in it always used.

- **Input:** `cfg: dict | None` (defaults to `load_config()`).
- consistency: default-cli — `resolve_default_cli` always returns a non-empty backend name
  normalized with `strip().lower()`.
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::resolve_default_cli`
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::write_default_cli`
- tests: `workhorse/tests/test_backends.py::test_config_default_cli_selects_backend`
- tests: `workhorse/tests/test_backends.py::test_env_var_beats_config_default_cli`
- tests: `workhorse/tests/test_backends.py::test_unknown_config_default_cli_fails_like_any_typo`

## resolve_harness_env

Resolves `[harness.<backend>].env` to a plain `dict[str, str]` of environment variables to add to
that harness's subprocess — e.g. `env = { OPENCODE_DISABLE_AUTOCOMPACT = "1" }`. Scoped per
**harness**, not per power tier: what a CLI needs in its environment is a property of that CLI.
A missing or mistyped table yields `{}`, and a non-string value is dropped rather than coerced —
an environment is strings, and quietly stringifying a bare TOML `1` would hide the config error.

- **Input:** `backend: str`, `cfg: dict | None` (defaults to `load_config()`).
- **Output:** `dict[str, str]`.
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::resolve_harness_env`

## PowerMapping

The frozen dataclass `resolve_power` and `resolve_backend_default` return: `model: str | None =
None`, `effort: str | None = None`. Both fields default to unset so an unconfigured tier/backend
combination is a no-op override, not an error.

- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::PowerMapping`

## Consumers

- [`farrier config`](../../farrier/farrier.md#config) — `show`/`set-*`, the one command that reads and
  writes this file. The `power` and `profiles` tables have no writer subcommand; they are
  edited by hand, and `show --profile <name>` reads one back.
- [`AgentRunner.run`](run-agent.md) — `resolve_power` and `resolve_backend_default` per agent turn,
  against the config re-loaded and re-narrowed to the run's [profile](#profiles) each turn, so
  a `control switch-profile` reaches the next turn without a reload.
- [`workhorse-<name> run --profile`](../workhorse.md#run) — `select_profile` once at the
  boundary, plus `profile_backends`/`profile_has_backend` to refuse a profile that maps no
  model for the chosen `--cli`.
- [`get_backend`](get-backend.md) — `resolve_default_cli`, the rung under `AGENT_CLI`; and
  [`workhorse-<name> run`](../workhorse.md#run), which resolves the name once and writes it back to
  `AGENT_CLI` so the manifest and template layers read the same answer.
- the [agent backend](agent-backend.md) — `resolve_harness_env` for the harness subprocess's
  environment.
- `stablemate_core.discovery` and farrier's installer — `library_dir`/`stablemate_dir`/`base_dir`,
  which is the pair of readers the unification exists for.
