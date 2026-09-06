---
type: concept
slug: profile-selection
title: Profile selection
---
# Profile selection

Selecting a named profile replaces the top-level model tables with that profile. It does not merge
unspecified tiers from the top level, while harness environment settings remain resolved from the
unselected config.

- code: `farrier/farrier/_vendor/stablemate_core/config.py::select_profile`
- detail: [home config](../home-config.md)

## Methods

### UnknownProfileError
This exception represents a request for a profile absent from the config.

- sig: `UnknownProfileError(message: str)`
- code: `farrier/farrier/_vendor/stablemate_core/config.py::UnknownProfileError`
