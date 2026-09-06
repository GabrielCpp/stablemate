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

The package initializer documents the boundary rather than exporting application behavior: the
core has no dependency on Farrier, workhorse, or ostler, and each tool owns its byte-identical
vendored copy. The cache, clock, configuration, discovery, and layout modules below are the
public contracts used by Farrier's command and library-resolution paths.

- code: `farrier/farrier/_vendor/__init__.py`
- code: `farrier/farrier/_vendor/stablemate_core/__init__.py`
- code: `farrier/farrier/_vendor/stablemate_core/base_cache.py`
- code: `farrier/farrier/_vendor/stablemate_core/clock.py`
- code: `farrier/farrier/_vendor/stablemate_core/config.py`
- code: `farrier/farrier/_vendor/stablemate_core/discovery.py`
- code: `farrier/farrier/_vendor/stablemate_core/layout.py`
- detail: [library directory](library-directory.md)
- detail: [home config](../home-config.md)
