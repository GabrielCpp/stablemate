---
type: concept
slug: skill-assets
title: Skill bundled assets
---
# Skill bundled assets

`references/` and `scripts/` directly beneath a directory containing `SKILL.md` are assets of that
skill, not independent library sources. Markdown references remain addressable beside the generated
skill, while script byproducts under `__pycache__/` are ignored because they were not authored.
Directories with those names elsewhere in the library remain ordinary source trees.

- code: `farrier/farrier/sources.py::skill_assets`
- tests: `farrier/tests/test_skill_assets.py::test_nested_skill_dirs_do_not_swallow_each_others_assets`

## Fields

### field: path
- type: `Path`
- required: true
- semantics: filesystem path of the bundled asset
- code: `farrier/farrier/sources.py::Asset`

### field: rel
- type: `str`
- required: true
- semantics: POSIX path relative to the owning skill directory and generated skill document
- code: `farrier/farrier/sources.py::Asset`

## Methods

### method: is_script
- sig: `Asset.is_script -> bool`
- does: identifies an asset as a script when its relative path begins with `scripts/`
- returns: `true` for script assets and `false` for reference assets
- verify: count(subject="script assets classified by relative path", equals=1)
- code: `farrier/farrier/sources.py::Asset.is_script`

### method: asset_owner
- sig: `asset_owner(root: Path, path: Path) -> Path | None`
- does: interprets `path` relative to `root` using POSIX-independent path components
- does: identifies a `references/` or `scripts/` directory in an ancestor of `path` as an asset boundary
- does: accepts that boundary only when the directory immediately above it contains a regular `SKILL.md`
- raises: `ValueError` when `path` is not located below `root`
- verify: count(subject="paths assigned to a directly-owned skill asset directory", equals=1)
- verify: absent(subject="owner for a references directory outside a skill")
- returns: the directory containing that `SKILL.md` when `path` is below an accepted asset boundary
- returns: `None` when `path` has no accepted `references/` or `scripts/` ancestor
- code: `farrier/farrier/sources.py::asset_owner`
- tests: `farrier/tests/test_skill_assets.py::test_nested_skill_dirs_do_not_swallow_each_others_assets`
- tests: `farrier/tests/test_skill_assets.py::test_a_references_dir_outside_a_skill_still_holds_skills`

### method: skill_assets
- sig: `skill_assets(source: Source) -> list[Asset]`
- does: returns every regular file below the source skill's `references/` and `scripts/` directories in relative-path order
- does: omits files below any `__pycache__/` directory
- returns: an empty list for a flat source or a skill with no asset directories
- verify: count(subject="authored assets returned for a skill", equals=1)
- code: `farrier/farrier/sources.py::skill_assets`
- tests: `farrier/tests/test_skill_assets.py::test_running_a_bundled_script_does_not_bundle_its_bytecode`
