---
type: format
slug: home-config
title: Home config file (config.toml)
---
# Home config file (config.toml)

The shared, machine-local settings file every stablemate tool reads and writes — holding the
overlay [library directory](../concepts/library-directory.md) candidate, the base-library path, the
local `stablemate` checkout path, and the `[profiles.*]` / `[cli.*]` tables workhorse resolves
against. It lives in `stablemate_core`, not in farrier: the keys are shared, so workhorse
inheriting a farrier-set `library_dir` is the point rather than a leak. Read as a typed document by `load_home_config`, which validates the file against the
[machine config schema](../concepts/config-schema.md) (no tool reads the raw mapping, so
`load_home_config` is the one reader),
written key-by-key by `write_config_key` and `write_config_section`, and surfaced to the user by
[`farrier config show`](../farrier-commands-init.md#config). The schema is versioned: a config older than this
build's `CONFIG_VERSION` is carried forward in-memory on read, so resolvers always see the current
shape; the file on disk is lifted to the current version only when a write touches it.

- file: `config.toml` under `platformdirs.user_config_dir("stablemate")` — e.g.
  `~/.config/stablemate/config.toml` on Linux, `~/Library/Application Support/stablemate/config.toml`
  on macOS, `%APPDATA%\stablemate\config.toml` on Windows. `$STABLEMATE_CONFIG` (or the
  pre-unification `$WORKHORSE_CONFIG`) overrides the path outright.
- code: `farrier/farrier/_vendor/stablemate_core/config.py::load_home_config` @635fe33c5b9e
- code: `farrier/farrier/_vendor/stablemate_core/schema/home.py::HomeConfig` @074a3b29bddd
- detail: [machine config schema](../concepts/config-schema.md)
- detail: [configuration version guard](../concepts/config-version-guard.md)
- detail: [power mapping](../concepts/power-mapping.md)
- detail: [profile selection](../concepts/profile-selection.md)

## Fields

A TOML table. The complete list of keys, each with its type, default, meaning, example, environment
variable and legacy spelling, is printed by [`farrier config reference --file home`](../farrier-commands-init.md#config),
generated from the schema, so it cannot drift from what the loader accepts. This page does not repeat it.
A key the schema does not declare loads, is kept, and is reported once per process as a stray key. The
v1 `[power.*]` / `[harness.*]` shape is carried forward into the v2 `[profiles.*]` / `[cli.*]` shape by
the in-memory lift, so an older config keeps working until a write lifts it.

What farrier does with the keys it owns:

- `library_dir` is written by [`farrier config set-library <path>`](../farrier-commands-init.md#config) via
  `write_library_dir`, after the path is validated with `is_library_dir` (it must contain `library/`). It is
  the third-precedence overlay candidate of [library directory](../concepts/library-directory.md) resolution,
  after `--library` and `$FARRIER_LIBRARY_DIR`.
- `base_dir` is the persisted form of `$STABLEMATE_BASE_DIR`, written by `write_base_dir`. A
  configured-but-invalid value is skipped rather than raised on, because the base is additive and failing
  soft keeps an overlay-only setup working.
- `stablemate_dir` and `worktree_dir` are written by `write_stablemate_dir` and `write_worktree_dir`.
- `user_library.<harness>` selects what a user-scope install renders; the same selection keys as the
  manifest apply.
- `config_version` is stamped on every write. An absent key reads as version 1 because v1 IS the unified
  file. It is not the `stablemate-core` package version: coupling the two would bump the schema on every
  patch release and lock out every tool that had not upgraded yet. A file newer than the running build's
  `CONFIG_VERSION` makes `write_config_key` refuse with `ConfigVersionError` rather than clobber it. An
  older file is backed up to `<name>.v<N>.bak`, then carried forward before the write lands, so a write
  never mixes schemas.

- code: `farrier/farrier/user_library.py::user_library_tables` @c71b69ee84ae

## Reading and writing

- `load_home_config(path=None)` — returns the file as a validated `HomeConfig`, shared and read-only.
  Without `path` it finds the effective file: the unified file if it exists. If it does not, and
  the path was **not** named explicitly, the pre-unification per-tool files
  (`user_config_dir("workhorse")` then `user_config_dir("farrier")`, merged in that order) are read
  as a fallback; an explicitly named `$STABLEMATE_CONFIG` that happens not to exist means "this
  file", not "and also whatever is in `~/.config/workhorse`". An older file is lifted in memory,
  then validated. A wrong type raises `ConfigError` naming the key path
  (`groom.dispatch.runner.concurrency: Input should be a valid integer`). Unparsable TOML raises
  `ConfigError` too. A version-1 file that cannot be lifted raises `ConfigVersionError`. An
  undeclared key loads and logs a stray-key warning once per process. A missing file yields the
  defaults.
- Last good value: the document is held per path and revalidated when the file's modification time
  or size changes. A re-read of a path that loaded before and now fails validation or parsing logs
  a warning naming the key path and returns the last good document, so an edit made mid-run never
  ends a run. A first load that fails still raises. A file modified within the last two seconds is
  re-read on every call, so a rewrite that lands inside the filesystem's timestamp granularity is
  never served stale.
- `write_config_key(key, value)` — creates the config directory if needed, parses the existing file
  with a comment-preserving TOML editor, applies the version guard and migration above, sets
  `key = value`, stamps `config_version`, and writes the file back. Comments, key order and keys
  no tool declares survive the write. When only legacy files exist, this is what merges them into
  the unified path. `write_config_section(name, values)` does the same for one dotted table such as
  `groom.attend`, adding no empty parent header. A write forgets the held document, so the next
  load reads the file just written. Using a real TOML editor is load-bearing: the hand-rolled
  `f'{k} = "{v}"'` it replaced stringified nested tables, so a single `config set-base` turned
  `[power.*]` into a Python-repr string and every node silently fell back to the default model with
  no error anywhere.

- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_config_key` @d88fea8c531e
- detail: [config write documentation contexts](../concepts/config-write-context.md)

## Methods

### legacy_config_paths
- sig: `legacy_config_paths() -> list[Path]`
- does: returns the legacy workhorse and farrier config paths in migration order
- returns: one path for each legacy application config location
- verify: count(subject="legacy config paths", equals=2)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::legacy_config_paths` @4c7c2fee50db

### config_path
- sig: `config_path() -> Path`
- does: uses `$STABLEMATE_CONFIG`, then `$WORKHORSE_CONFIG`, then the platform shared config path
- returns: the expanded path selected for reads and writes
- verify: json_path(path="$.config_path", matches="config\\.toml$")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::config_path` @333a1e67799e

### config_version_of
- sig: `config_version_of(cfg: dict[str, Any]) -> int`
- does: treats an absent, boolean, non-integer, or below-one version as schema version 1
- returns: the integer schema version declared by the mapping
- verify: json_path(path="$.config_version", equals=1)
- code: `farrier/farrier/_vendor/stablemate_core/config.py::config_version_of` @8da6e2da31af

### check_config_version
- sig: `check_config_version() -> int`
- does: checks the effective config against the supported schema
- raises: `ConfigVersionError` when the config declares a newer schema
- returns: the supported schema version when the config is acceptable
- verify: json_path(path="$.exception.type", equals="ConfigVersionError")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::check_config_version` @560ca002be10

### profile_names
- sig: `profile_names(home: HomeConfig | None = None) -> list[str]`
- does: reads names from the config's `profiles` table
- returns: names sorted lexicographically, or an empty list when none are defined
- verify: count(subject="sorted profile names", equals=1)
- code: `farrier/farrier/_vendor/stablemate_core/profiles.py::profile_names` @fbc58c5e2cc2

### select_profile
- sig: `select_profile(home: HomeConfig | None, name: str) -> Profile | None`
- does: returns `None` when `name` is empty
- does: hands back the named profile so resolvers see one CLI's view
- does: validates the named profile declares a `cli` field
- raises: `UnknownProfileError` when the named profile is not defined
- raises: `ConfigError` when the named profile has no `cli` field
- returns: the selected `Profile`, or `None` for an empty `name`
- verify: json_path(path="$.cli", equals="opencode")
- code: `farrier/farrier/_vendor/stablemate_core/profiles.py::select_profile` @4dbfd0a9d396

### profile_backends
- sig: `profile_backends(profile: Profile) -> list[str]`
- does: returns the profile's declared CLI as a single-element list
- does: returns an empty list when the profile has no usable `cli` field
- returns: the lowercased CLI name as a one-element list, or `[]` when missing
- verify: count(subject="profile backends", equals=1)
- code: `farrier/farrier/_vendor/stablemate_core/profiles.py::profile_backends` @571afa4c80e6

### profile_has_backend
- sig: `profile_has_backend(profile: Profile | None, backend: str) -> bool`
- does: reports true when the profile's `cli` field equals `backend`
- returns: false when there is no profile, it has no `cli` field, or the names differ
- verify: json_path(path="$", equals=true)
- code: `farrier/farrier/_vendor/stablemate_core/profiles.py::profile_has_backend` @11cf779f6e80

### resolve_power
- sig: `resolve_power(power: str | None, backend: str, profile: Profile | None = None) -> PowerMapping`
- does: returns an empty mapping when no power tier, no profile, no tier table, or the profile's `cli` field disagrees with `backend`
- does: reads the tier entry directly from `profile.powers.<power>` (no per-backend nesting in v2)
- returns: a `PowerMapping` carrying `model`, `effort`, and `timeout_scale`
- verify: json_path(path="$.model", equals="haiku")
- code: `farrier/farrier/_vendor/stablemate_core/profiles.py::resolve_power` @654eae2c4d72

### resolve_backend_default
- sig: `resolve_backend_default(backend: str, profile: Profile | None = None) -> PowerMapping`
- does: reads the mapping from the profile's `default` table
- does: returns an empty mapping when the profile's `cli` field disagrees with `backend`
- returns: a `PowerMapping` carrying `model`, `effort`, and `timeout_scale`, or an empty mapping when the table is absent
- verify: json_path(path="$.model", equals="opus")
- code: `farrier/farrier/_vendor/stablemate_core/profiles.py::resolve_backend_default` @25cec29f5a29

### resolve_harness_env
- sig: `resolve_harness_env(backend: str, home: HomeConfig | None = None) -> dict[str, str]`
- does: reads `cli.<backend>.env` from the unnarrowed config so every profile that runs this CLI inherits the table
- does: drops empty variable names
- does: fails the load, rather than coercing, when a value is not a string
- returns: the string environment mapping, or `{}` when absent
- verify: json_path(path="$.OPENCODE_DISABLE_AUTOCOMPACT", equals="1")
- code: `farrier/farrier/_vendor/stablemate_core/profiles.py::resolve_harness_env` @95f123a20729

### resolve_default_cli
- sig: `resolve_default_cli(home: HomeConfig | None = None) -> str`
- does: reads and trims the configured `default_cli` value
- returns: the lower-case configured CLI, or `claude` when absent or blank
- verify: json_path(path="$.default_cli", equals="claude")
- code: `farrier/farrier/_vendor/stablemate_core/profiles.py::resolve_default_cli` @498c07bf417f

### write_library_dir
- sig: `write_library_dir(path: Path) -> None`
- does: persists the overlay library path under `library_dir`
- returns: `None`
- verify: persists(subject="library_dir")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_library_dir` @0aaa18f50fca
- detail: [config write documentation contexts](../concepts/config-write-context.md)

### write_stablemate_dir
- sig: `write_stablemate_dir(path: Path) -> None`
- does: persists the stablemate checkout path under `stablemate_dir`
- returns: `None`
- verify: persists(subject="stablemate_dir")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_stablemate_dir` @0938d2bdd27a

### write_base_dir
- sig: `write_base_dir(path: Path) -> None`
- does: persists the base library path under `base_dir`
- returns: `None`
- verify: persists(subject="base_dir")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_base_dir` @c969cedaf7ec

### write_worktree_dir
- sig: `write_worktree_dir(path: Path) -> None`
- does: persists the parent directory for new worktrees without requiring it to exist
- returns: `None`
- verify: persists(subject="worktree_dir")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_worktree_dir` @de1f039be7d0

### resolve_stablemate_dir
- sig: `resolve_stablemate_dir() -> Path | None`
- does: reads the configured `stablemate_dir` value
- returns: its expanded absolute path, or `None` when unset or not a non-empty string
- verify: json_path(path="$.stablemate_dir", equals="/checkout")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::resolve_stablemate_dir` @80b69ad6678e

### resolve_worktree_dir
- sig: `resolve_worktree_dir() -> Path | None`
- does: reads the configured `worktree_dir` value without requiring the directory to exist
- returns: its expanded absolute path, or `None` when unset or not a non-empty string
- verify: json_path(path="$.worktree_dir", equals="/worktrees")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::resolve_worktree_dir` @f68b6d0c5853

### resolve_paddock_dir
- sig: `resolve_paddock_dir() -> Path`
- does: uses the configured `paddock_dir`, then a `paddock` folder under the platform data directory
- returns: the expanded absolute path of the benchmark root
- verify: json_path(path="$.paddock_dir", equals="/bench")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::resolve_paddock_dir` @5ce6787bd02c

### resolve_artifacts_dir
- sig: `resolve_artifacts_dir() -> Path`
- does: uses `$STABLEMATE_ARTIFACTS_DIR`, then the configured `artifacts_dir`, then an `artifacts` folder under the platform data directory
- returns: the expanded absolute path of the artifacts folder
- verify: json_path(path="$.artifacts_dir", equals="/artifacts")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::resolve_artifacts_dir` @9214f57f99b1

### resolve_delegates
- sig: `resolve_delegates(backend: str, profile: Profile | None = None) -> dict[str, PowerMapping]`
- does: reads the selected profile's `delegates` table, one mapping per role
- does: returns an empty mapping when the profile's `cli` field disagrees with `backend`
- does: keeps only the roles whose entry names a model
- returns: a mapping from role name to `PowerMapping`
- verify: json_path(path="$.reviewer.model", equals="haiku")
- code: `farrier/farrier/_vendor/stablemate_core/profiles.py::resolve_delegates` @723e18203ef7
