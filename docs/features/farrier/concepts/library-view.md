---
type: concept
slug: library-view
title: Library view
---
# Library view

The read-only library catalog preserves every provider layer, including shadowed entries, while
resolving names using the same stack that installation uses.

### method: Item
- sig: `Item(name: str, alias: str, provided: tuple[tuple[str, Path], ...])`
- does: carry one catalog name, optional installed alias, and all layer providers
- code: `farrier/farrier/library_view.py::Item`
- verify: count(subject="library catalog item records", equals=1)

### method: layer
- sig: `Item.layer -> str`
- returns: the highest-precedence provider layer
- code: `farrier/farrier/library_view.py::Item.layer`
- verify: count(subject="winning library provider labels", equals=1)

### method: path
- sig: `Item.path -> Path`
- returns: the highest-precedence provider path
- code: `farrier/farrier/library_view.py::Item.path`
- verify: count(subject="winning library provider paths", equals=1)

### method: shadowed
- sig: `Item.shadowed -> tuple[str, ...]`
- returns: provider layer names hidden by the winner
- code: `farrier/farrier/library_view.py::Item.shadowed`
- verify: count(subject="shadowed provider layer lists", equals=1)

### method: path_in
- sig: `Item.path_in(layer: str) -> Path | None`
- returns: the item's path in the named provider layer, or none when that layer does not provide it
- code: `farrier/farrier/library_view.py::Item.path_in`
- verify: absent(subject="provider path for a layer that does not provide an item")

## Methods

### method: _dirs
- sig: `_dirs(*parts: str) -> list[tuple[str, Path]]`
- does: return one distinct real directory per resolved layer for the requested path
- verify: count(subject="distinct library layer directories", equals=1)
- code: `farrier/farrier/library_view.py::_dirs`

### method: stack
- sig: `stack() -> list[str]`
- does: return deduplicated active layer names in precedence order
- verify: count(subject="active library layer names", equals=1)
- code: `farrier/farrier/library_view.py::stack`

### method: _source_items
- sig: `_source_items(kind: str, *parts: str, installed: bool = True) -> list[Item]`
- does: collect source-backed items across all providers without collapsing shadowed ids
- verify: count(subject="source-backed catalog items", equals=1)
- code: `farrier/farrier/library_view.py::_source_items`

### method: _file_items
- sig: `_file_items(suffix: str, *parts: str) -> list[Item]`
- does: collect flat file-backed items such as packs, scaffolds, and roots with provider records
- verify: count(subject="file-backed catalog items", equals=1)
- code: `farrier/farrier/library_view.py::_file_items`

### method: items
- sig: `items(kind: str) -> list[Item]`
- does: return every catalog item for a supported plural kind
- raises: `SystemExit` for an unknown library kind
- verify: count(subject="catalog items returned for a supported kind", equals=1)
- code: `farrier/farrier/library_view.py::items`

### method: layer_label
- sig: `layer_label(choice: str) -> str`
- does: map `base` or `overlay` to the active layer name
- raises: `SystemExit` when overlay was requested without an overlay layer
- verify: count(subject="base and overlay layer labels", equals=2)
- code: `farrier/farrier/library_view.py::layer_label`

### method: format_list
- sig: `format_list(kinds: list[str], layer: str | None = None) -> str`
- does: render one catalog block per selected kind, optionally filtered to providers of one layer
- verify: count(subject="formatted library catalog blocks", equals=1)
- code: `farrier/farrier/library_view.py::format_list`

### method: _format_kind
- sig: `_format_kind(kind: str, found: list[Item], layer: str | None) -> str`
- does: render a kind header, count, and aligned item rows with shadow annotations
- verify: count(subject="formatted library kind rows", equals=1)
- code: `farrier/farrier/library_view.py::_format_kind`

### method: find
- sig: `find(kind: str, name: str) -> Item`
- does: resolve a library id, installed alias, or basename in that precedence order
- raises: `SystemExit` for ambiguous or unknown names with actionable catalogs
- verify: count(subject="library item name resolutions", equals=1)
- code: `farrier/farrier/library_view.py::find`
