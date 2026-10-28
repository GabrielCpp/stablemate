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
and any write to it is refused.

The CLI is chosen in this order:

- `--profile NAME` names a profile, and the profile's `cli` field names the CLI. A profile with
  no `cli` field is refused. A profile whose CLI this engine has no backend for is refused.
- `--cli NAME` names the CLI. Without it, `AGENT_CLI` does, then the config's `default_cli`, then
  claude.
- With only a CLI, the run uses the profile named after that CLI when that profile declares the
  same CLI. Otherwise it runs on no profile.

An operator can switch the CLI or the profile of a live run with
[`control switch-cli`](../workhorse.md#control) or `switch-profile`. The switch is recorded, so a
resumed run comes back on the profile it switched to. The agent CLIs themselves are described in
[agent backends](agent-backends.md).

- code: `workhorse/workhorse/profile.py::select_backend` @ff29018aab02
- code: `workhorse/workhorse/profile.py::implied_profile` @ff29018aab02
- code: `workhorse/workhorse/profile.py::ProfileError` @ff29018aab02
- code: `workhorse/workhorse/profile.py::switch_profile` @ff29018aab02
- code: `workhorse/workhorse/profile.py::recorded_profile` @ff29018aab02
- code: `workhorse/workhorse/profile.py::record_switch` @ff29018aab02
- code: `workhorse/workhorse/_vendor/stablemate_core/profiles.py::select_profile` @0f757c16382b
- code: `workhorse/workhorse/_vendor/stablemate_core/profiles.py::resolve_default_cli` @0f757c16382b
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::load_config` @ff8a02ce3c68
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::check_config_version` @ff8a02ce3c68
