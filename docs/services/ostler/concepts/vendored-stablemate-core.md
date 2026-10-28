---
type: concept
slug: vendored-stablemate-core
title: Vendored stablemate-core
---
# Vendored stablemate-core

Ostler is installed on its own, without the rest of the stablemate monorepo, so it carries a
private copy of the handful of cross-tool helpers every stablemate CLI shares: config
persistence, the shared base-skill library, and wall-clock access as an injectable dependency.
The copy lives at `ostler/_vendor/stablemate_core/`, written there by `make vendor` from
`core/stablemate_core` at the repository root; a caller edits the root copy and re-runs
`make vendor`, never this one, and `make check-vendor` fails the build if the two drift apart.
Ostler's `index`, `model`, `qa/stack`, `qa/tools` and `qa/addresses` modules import a few helpers from it, for config, the base-library cache and the clock. Discovery, profiles and skill references are carried but no ostler module calls them.

- code: ostler/ostler/_vendor/__init__.py@d63f5d827a00
- code: ostler/ostler/_vendor/stablemate_core/__init__.py@3b3d6fe59b0c
- code: ostler/ostler/_vendor/stablemate_core/clock.py::Clock@99322cfda640
- code: ostler/ostler/_vendor/stablemate_core/clock.py::SYSTEM_CLOCK@99322cfda640
- code: ostler/ostler/_vendor/stablemate_core/layout.py::is_library_dir@d69e52175abc
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::ensure_cached_base@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::refresh_cached_base@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cached_commit@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/discovery.py::base_library_dir@42eebfdfea77
- code: ostler/ostler/_vendor/stablemate_core/discovery.py::ensure_base_library_dir@42eebfdfea77
- code: ostler/ostler/_vendor/stablemate_core/config.py::load_config@f30a7f155019
- code: ostler/ostler/_vendor/stablemate_core/config.py::write_config_key@f30a7f155019
- code: ostler/ostler/_vendor/stablemate_core/config.py::write_config_section@f30a7f155019
- code: ostler/ostler/_vendor/stablemate_core/profiles.py::select_profile@0f757c16382b
- code: ostler/ostler/_vendor/stablemate_core/profiles.py::resolve_power@0f757c16382b
- code: ostler/ostler/_vendor/stablemate_core/profiles.py::resolve_backend_default@0f757c16382b
- code: ostler/ostler/_vendor/stablemate_core/profiles.py::resolve_delegates@0f757c16382b
- code: ostler/ostler/_vendor/stablemate_core/skill_refs.py::scan_catalog@ebf1b69c7565
- code: ostler/ostler/_vendor/stablemate_core/skill_refs.py::skill_link@ebf1b69c7565
- code: ostler/ostler/_vendor/stablemate_core/skill_refs.py::skill_path@ebf1b69c7565
- code: ostler/ostler/_vendor/stablemate_core/skill_refs.py::skill_command@ebf1b69c7565

## Contract

- clock (`clock.py`): `Clock` is a protocol of `now`, `monotonic` and `sleep`; `SYSTEM_CLOCK` is
  the one implementation that calls the real `time` and `datetime` functions, so code that needs
  to wait takes a `Clock` instead of calling `time.sleep` directly and a test can substitute a
  fake one.
- library layout (`layout.py`): `is_library_dir` reports whether a path holds a `library/`
  subdirectory, the one structural fact every base-library consumer checks before trusting a
  candidate directory.
- base-library cache (`base_cache.py`): `ensure_cached_base` and `refresh_cached_base` fetch the
  `base-library/` subtree of the `stablemate` repo at a given git ref into one shared cache
  directory (`$STABLEMATE_CACHE_DIR`, else the platform user-cache dir), with a sparse,
  depth-1 clone that keeps only that subtree; the fetch is skipped when `$STABLEMATE_FETCH_BASE`
  is set to a falsy value, and `cached_commit` reports the commit the cache currently holds.
- base-library discovery (`discovery.py`): `base_library_dir` and `ensure_base_library_dir` find
  the library to use in order — an explicit `$STABLEMATE_BASE_DIR`, a configured `base_dir`, a
  configured `stablemate_dir`'s `base-library/` subpath, then the shared cache — and only the
  `ensure_` form is allowed to populate the cache.
- config persistence (`config.py`): `load_config` and `write_config_key`/`write_config_section`
  read and write one TOML file (`$STABLEMATE_CONFIG`, else the platform user-config dir); a config
  written by a newer stablemate-core than the one running raises `ConfigVersionError` rather than
  being silently rewritten and losing keys this build does not understand, and a config older than
  the running build is migrated forward one registered step at a time, with the pre-migration file
  backed up next to it as `<name>.v<N>.bak`.
- profile and power resolution (`profiles.py`): `select_profile` raises `UnknownProfileError` for
  a `--profile` name absent from `[profiles]`, and for a name present but missing the required
  `cli` field raises `ConfigError`; `resolve_power`, `resolve_backend_default` and
  `resolve_delegates` read the model/effort/timeout-scale a profile declares for a tier, a
  fallback, or a subagent role, each scoped to the profile's own `cli`.
- skill references (`skill_refs.py`): `scan_catalog` walks from a working directory up to the
  repository root, then added directories, then the home folder, collecting every `SKILL.md` and
  prompt file per harness's folder layout (`HARNESS_FOLDERS`); a rendered template calls
  `skill_link`, `skill_path` or `skill_command` to reference a catalog entry by name, and a name
  the catalog does not hold raises `MissingSkill` unless the template supplied its own
  `on_missing` fallback. A template calling one of the helpers `RETIRED_HELPERS` lists instead
  raises `RetiredHelper`, naming the replacement.
