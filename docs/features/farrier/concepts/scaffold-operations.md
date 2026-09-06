---
type: concept
slug: scaffold-operations
title: Scaffold operations
---
# Scaffold operations

Scaffold definitions are layered YAML recipes. The command resolves the winning definition and
parameters, safely flattens its tree, downloads URL files when requested, and seeds only absent
paths.

## Methods

### method: resolve_scaffold_params
- sig: `resolve_scaffold_params(scaffold_id: str, definition: dict[str, Any], overrides: dict[str, str], repo: Path) -> dict[str, str]`
- does: merge declared defaults and overrides
- verify: count(subject="resolved scaffold parameter mappings", equals=1)
- does: reject unknown parameters
- verify: count(subject="unknown scaffold parameters rejected", equals=1)
- does: require values for null-default parameters
- verify: count(subject="required scaffold parameters", equals=1)
- does: add repository name and title defaults
- verify: count(subject="repository scaffold name and title defaults", equals=1)
- code: `farrier/farrier/scaffolds.py::resolve_scaffold_params`

### method: flatten_scaffold_tree
- sig: `flatten_scaffold_tree(scaffold_id: str, tree: dict[str, Any], base: str = '') -> tuple[dict[str, Any], list[str]]`
- does: flatten inline files into the file collection
- verify: count(subject="flattened inline scaffold files", equals=1)
- does: flatten URL file nodes into the file collection
- verify: count(subject="flattened URL scaffold files", equals=1)
- does: flatten nested directories into the directory collection
- verify: count(subject="flattened nested scaffold directories", equals=1)
- does: flatten empty directories into the directory collection
- verify: count(subject="flattened empty scaffold directories", equals=1)
- raises: `SystemExit` for unsupported tree node values or keys
- code: `farrier/farrier/scaffolds.py::flatten_scaffold_tree`

### method: substitute_scaffold_path
- sig: `substitute_scaffold_path(scaffold_id: str, rel: str, params: dict[str, str]) -> str`
- does: strictly substitute path parameters and reject empty, absolute, or parent-traversing results
- verify: absent(subject="scaffold paths escaping the repository")
- code: `farrier/farrier/scaffolds.py::substitute_scaffold_path`

### method: fetch_scaffold_url
- sig: `fetch_scaffold_url(scaffold_id: str, rel: str, url: str) -> str`
- does: fetch a scaffold file with a bounded timeout and decode it as UTF-8
- raises: `SystemExit` with scaffold id and path when download or decoding fails
- verify: count(subject="downloaded scaffold file contents", equals=1)
- code: `farrier/farrier/scaffolds.py::fetch_scaffold_url`

### method: available_scaffold_ids
- sig: `available_scaffold_ids(repo: Path, defs: dict[str, dict[str, Any]]) -> set[str]`
- does: return all definitions without agents.yml, otherwise union direct and selected-pack scaffold ids
- verify: count(subject="scaffold ids available to a repository", equals=1)
- code: `farrier/farrier/scaffolds.py::available_scaffold_ids`

### method: parse_param_overrides
- sig: `parse_param_overrides(entries: list[str]) -> dict[str, str]`
- does: parse repeated `key=value` arguments, retaining the last value for a repeated key
- raises: `SystemExit` for an entry without a non-empty key and equals separator
- verify: count(subject="parsed scaffold parameter overrides", equals=1)
- code: `farrier/farrier/scaffolds.py::parse_param_overrides`
