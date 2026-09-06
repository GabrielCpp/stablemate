---
type: concept
slug: config-version-guard
title: Configuration version guard
---
# Configuration version guard

The shared TOML file is guarded by its schema version because separately installed tools can write
the same file. Reads of a newer schema warn and continue, but writes refuse rather than dropping
keys the current tool does not understand.

- code: `farrier/farrier/_vendor/stablemate_core/config.py::ConfigVersionError`
- detail: [home config](../home-config.md)

## Methods

### ConfigVersionError
- sig: `ConfigVersionError(message: str)`
- does: represents refusal to write a config newer than the supported schema
- verify: conflict_on_stale(subject="config file", token="config schema version")
- code: `farrier/farrier/_vendor/stablemate_core/config.py::ConfigVersionError`
