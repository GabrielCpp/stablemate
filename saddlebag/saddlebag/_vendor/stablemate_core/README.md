# stablemate_core

The runtime state every stablemate tool must agree on: the home config, where the base library is found, and its shared cache. `make vendor` copies this directory into each tool, so edit it here and never in a `_vendor/` copy.
