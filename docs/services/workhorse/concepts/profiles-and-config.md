---
type: concept
title: Profiles and config
---
# Profiles and config

A profile is a named row of model choices in the stablemate config file. It says which agent CLI
the run drives and which model and effort each power level of a node resolves to. A run is on
exactly one CLI and at most one profile at a time.

The config file is the first of these that is set: `--config`, `$STABLEMATE_CONFIG`, then
`$WORKHORSE_CONFIG`, then the home config. The file carries a `config_version`. A file from an
older version is migrated in memory when read. A file from a newer version is read with a warning,
and any write to it is refused. The file is read each turn through a cache that re-reads it only
when it changes. A change that fails validation leaves the last good config in force and logs the
key path, so an edit made mid-run never ends the run. A file that has never loaded fails the run at
start, naming the key path.

The CLI is chosen in this order:

- `--profile NAME` names a profile, and the profile's `cli` field names the CLI. A profile with
  no `cli` field is refused. A profile whose CLI this engine has no backend for is refused.
- `--cli NAME` names the CLI. Without it, `AGENT_CLI` does, then the config's `default_cli`, then
  claude.
- With only a CLI, the run uses the profile named after that CLI when that profile declares the
  same CLI. Otherwise it runs on no profile, and no model, effort or timeout scale comes from the
  file: a table left at the top level of the config is not a profile.

An operator can switch the CLI or the profile of a live run with
[`control switch-cli`](../workhorse.md#control) or `switch-profile`. The switch is recorded, so a
resumed run comes back on the profile it switched to. The agent CLIs themselves are described in
[agent backends](agent-backends.md).

- code: `workhorse/workhorse/profile.py::select_backend` @e476586e5a7f
- code: `workhorse/workhorse/profile.py::implied_profile` @61bb22af1e60
- code: `workhorse/workhorse/profile.py::ProfileError` @6271a2f66932
- code: `workhorse/workhorse/profile.py::switch_profile` @6f0444c3120e
- code: `workhorse/workhorse/profile.py::recorded_profile` @15c64172698f
- code: `workhorse/workhorse/profile.py::record_switch` @d058110a1d97
- code: `workhorse/workhorse/_vendor/stablemate_core/profiles.py::select_profile` @4dbfd0a9d396
- code: `workhorse/workhorse/_vendor/stablemate_core/profiles.py::resolve_default_cli` @498c07bf417f
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::load_home_config` @635fe33c5b9e
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::check_config_version` @560ca002be10
