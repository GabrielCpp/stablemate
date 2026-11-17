story: none
date: 2026-11-16
elements: Install

farrier/farrier/_vendor/stablemate_core is a symlink to core/stablemate_core, the shared package that holds the
config, schema and manifest readers every command calls. Its files are core's, not farrier's, and the vendored
checksum beside it only records which copy farrier took. The book names the farrier files that call it and leaves the
link, its checksum and the package marker under `App(ignore=...)`. The README of the package and its `__init__.py`
hold no behaviour.
