---
type: concept
slug: base-library-discovery
title: stablemate base-library discovery
---
# stablemate base-library discovery

Discovery resolves the base library without making ordinary lookups perform network I/O. An
explicit `STABLEMATE_BASE_DIR` wins, then configured `base_dir`, then the configured stablemate
checkout's `base-library/`, and finally the frozen cache. Invalid configured paths are skipped;
the base remains additive to an overlay-only installation.

- code: `workhorse/workhorse/_vendor/stablemate_core/discovery.py`

## Methods

### base_library_dir
- sig: `base_library_dir() -> Path | None`
- does: evaluate explicit path, shared-config path, configured checkout, and cached base in that order
- verify: json_path(path="$.base_library_dir", equals="/explicit-base")
- does: validate every candidate with `is_library_dir` and resolve the selected path
- verify: json_path(path="$.base_library_dir", matches="^/.+")
- does: never fetch
- verify: absent(subject="network fetch during base library lookup")
- returns: the first usable base path
- verify: json_path(path="$.base_library_dir", equals="/base-library")
- returns: `None` when no candidate is usable
- verify: json_path(path="$.base_library_dir", absent=true)
- code: `workhorse/workhorse/_vendor/stablemate_core/discovery.py::base_library_dir`

### ensure_base_library_dir
- sig: `ensure_base_library_dir(*, refresh: bool = False, quiet: bool = False) -> Path | None`
- does: preserve the explicit/configured resolution order before considering the cache
- verify: json_path(path="$.base_library_dir", equals="/explicit-base")
- does: call cache ensure or refresh only when no human-selected base is usable
- verify: absent(subject="cache ensure or refresh with a usable human-selected base")
- returns: the selected or populated base path when one is available
- verify: json_path(path="$.base_library_dir", matches="^/.+")
- returns: `None` when no base is available
- verify: json_path(path="$.base_library_dir", absent=true)
- code: `workhorse/workhorse/_vendor/stablemate_core/discovery.py::ensure_base_library_dir`
