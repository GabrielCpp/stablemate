---
type: concept
slug: asset-path-representations
title: Asset path representations
---
# Asset path representations

Each bundled asset has both representations because they serve different boundaries. `path` is
the filesystem location used while collecting and installing the asset. `rel` is the POSIX path
relative to the owning skill directory and generated `SKILL.md`; it is the stable representation
for links in generated skills and for determining whether an asset is a script.

Neither field replaces the other. Use `path` when code must read or copy the file, and use `rel`
when the asset must be named independently of the machine-specific skill location.

- code: `farrier/farrier/sources.py::Asset`
- rule: use `path` for filesystem operations and `rel` for portable asset identity; both fields are required for each bundled asset
