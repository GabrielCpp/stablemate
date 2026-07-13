---
type: concept
slug: groom-package-initializer
title: groom package initializer
---
# groom package initializer

The groom package initializer is the import-time contract for the top-level [`groom`](../groom.md) Python package. It exposes the package version as the only star-import export and deliberately does not start the [groom server](../http/groom.md), inspect Docker, open sidecar connections, import dashboard modules, or mutate process state when the package is imported.

- code: groom/groom/__init__.py

## Contract

- purpose: define the package-level metadata visible from `import groom` and from `from groom import *`.
- import behavior: importing the package performs only constant assignment for the export list and version string.
- public export rule: star imports expose `__version__` and no command, server, sidecar, state, discovery, rendering, or Docker helper symbols.
- submodule rule: package submodules remain importable through ordinary Python package semantics, but the initializer does not eagerly import or re-export them.
- side effects: no server startup, CLI parsing, Docker subprocess execution, filesystem access, network access, websocket registration, in-memory workflow mutation, logging, or background task creation.
- version source: the package version is a literal string in the initializer, not computed from package metadata, git state, or runtime environment.

## Fields

### field-__all__

- type: `list[str]`
- default: `["__version__"]`
- required: true
- code: groom/groom/__init__.py::__all__
- meaning: declares the complete star-import export list for the package initializer.
- constraints: contains only `__version__`; adding a symbol here makes it part of the package's wildcard import surface.

### field-__version__

- type: `str`
- default: `"0.1.0"`
- required: true
- code: groom/groom/__init__.py::__version__
- meaning: package-level version string exposed to callers that import `groom.__version__` or use the initializer's star-import surface.
- constraints: static literal value; importing the package does not derive or validate it against installed distribution metadata.
