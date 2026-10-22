---
type: concept
slug: layered-source-resolution
title: Layered source resolution
---
# Layered source resolution

The source stack is ordered from highest precedence to lowest. An overlay source with the same
library name replaces the base source, even when a different folder holds it. Distinct names are
retained and returned deterministically. Each retained record keeps the layer that supplied it so
provenance and shadowing remain observable. Two sources that share a name inside one layer stop the
load, because a name must be unique across its library.

- code: `farrier/farrier/sources.py::load_layered_sources` @38fd583de0b8
- detail: [library source record](source-record.md)

## Methods

### method: library_path
- sig: `library_path(path: Path, fallback: str) -> str`
- does: anchors a path at its last `library/` segment when one exists
- returns: a machine-independent POSIX library path, or the supplied fallback
- verify: count(subject="anchored library path", equals=1)
- code: `farrier/farrier/sources.py::library_path` @38fd583de0b8

### method: load_layered_sources
- sig: `load_layered_sources(kind: str, *parts: str) -> list[Source]`
- does: visits every matching directory in layer precedence order and loads its sources for `kind`
- does: keeps the first source for each library name, so a higher layer shadows lower-layer duplicates
- raises: exits when two sources in the same layer share a library name
- returns: all winning sources sorted by source id
- verify: count(subject="winning sources after layer shadowing", equals=1)
- code: `farrier/farrier/sources.py::load_layered_sources` @38fd583de0b8

### method: library_source_path
- sig: `library_source_path(source: Source) -> str`
- does: reports the source path beginning at its last `library/` segment
- returns: a POSIX library-relative path, falling back to `source.rel` outside a library tree
- verify: count(subject="library provenance path", equals=1)
- code: `farrier/farrier/sources.py::library_source_path` @38fd583de0b8
- tests: `farrier/tests/test_provenance_banner.py::test_library_source_path_anchors_at_library`

### method: override_notices
- sig: `override_notices(kind: str, *parts: str) -> list[str]`
- does: names each library source of `kind` that a higher layer replaces by library name
- returns: one `info:` line per override, naming the winning layer and file and the layer and file it overrides
- verify: count(subject="override notice lines", equals=1)
- code: `farrier/farrier/sources.py::override_notices` @38fd583de0b8
