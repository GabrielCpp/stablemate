---
type: concept
slug: library-layout
title: stablemate base-library layout
---
# stablemate base-library layout

A usable base-library root is a directory containing a `library/` directory. The former
`workflows/` alternative is not accepted, and `packs/` is optional.

- code: `workhorse/workhorse/_vendor/stablemate_core/layout.py::is_library_dir`

## Methods

### is_library_dir
- sig: `is_library_dir(path: Path) -> bool`
- does: test whether `path/library` is a directory
- returns: `true` only for a root with the required `library/` directory
- code: `workhorse/workhorse/_vendor/stablemate_core/layout.py::is_library_dir`
