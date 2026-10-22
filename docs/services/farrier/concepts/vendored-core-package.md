---
type: concept
slug: vendored-core-package
title: Vendored core package
---
# Vendored core package

Farrier carries a private copy of the shared stablemate core under `_vendor`. The package is not
published independently; its modules use relative imports so this tool cannot accidentally resolve
another installation's copy. It contains shared configuration, clock, cache, discovery, and
library-layout contracts, while Farrier-specific behavior remains outside it.

The package initializer is a one-line docstring and exports no application behavior. The core has
no dependency on Farrier, workhorse, or ostler, and each tool owns its byte-identical vendored
copy. The cache, clock, configuration, discovery, and layout modules below are the public contracts used by Farrier's command and library-resolution paths.

The configuration contract persists one versioned, platform-appropriate shared config file. It
reads legacy per-tool files only when that unified file is absent, carries older schemas forward
in memory, and backs up then stamps an older file on its first write. A writer refuses a file
whose schema is newer than the vendored core understands, preserving settings it could otherwise
drop. Named profiles select the model and effort mapping for one CLI, while CLI environment
settings remain global to that CLI across profiles.

- code: `farrier/farrier/_vendor/__init__.py` @d63f5d827a00
- code: `farrier/farrier/_vendor/stablemate_core/__init__.py` @3b3d6fe59b0c
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py` @79e1cc13c672
- code: `farrier/farrier/_vendor/stablemate_core/clock.py` @99322cfda640
- code: `farrier/farrier/_vendor/stablemate_core/config.py` @45b4d92edb39
- code: `farrier/farrier/_vendor/stablemate_core/discovery.py` @42eebfdfea77
- code: `farrier/farrier/_vendor/stablemate_core/layout.py` @d69e52175abc
- detail: [library directory](library-directory.md)
- detail: [home config](../formats/home-config.md)
