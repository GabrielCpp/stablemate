---
type: concept
slug: layered-source-resolution
title: Layered source resolution
---
# Layered source resolution

The source stack is ordered from highest precedence to lowest. An overlay source with the same
derived id replaces the base source, while distinct ids are retained and returned deterministically.
Each retained record keeps the layer that supplied it so provenance and shadowing remain observable.

- code: `farrier/farrier/sources.py::load_layered_sources`
- detail: [library source record](source-record.md)

## Methods

### method: library_path
- sig: `library_path(path: Path, fallback: str) -> str`
- does: anchors a path at its last `library/` segment when one exists
- returns: a machine-independent POSIX library path, or the supplied fallback
- verify: count(subject="anchored library path", equals=1)
- code: `farrier/farrier/sources.py::library_path`

### method: load_layered_sources
- sig: `load_layered_sources(kind: str, *parts: str) -> list[Source]`
- does: visits every matching directory in layer precedence order and loads its sources for `kind`
- does: keeps the first source for each source id, so a higher layer shadows lower-layer duplicates
- returns: all winning sources sorted by source id
- verify: count(subject="winning sources after layer shadowing", equals=1)
- code: `farrier/farrier/sources.py::load_layered_sources`

### method: library_source_path
- sig: `library_source_path(source: Source) -> str`
- does: reports the source path beginning at its last `library/` segment
- returns: a POSIX library-relative path, falling back to `source.rel` outside a library tree
- verify: count(subject="library provenance path", equals=1)
- code: `farrier/farrier/sources.py::library_source_path`
- tests: `farrier/tests/test_provenance_banner.py::test_library_source_path_anchors_at_library`
