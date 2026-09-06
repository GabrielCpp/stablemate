---
type: concept
slug: cli-internals
title: CLI internals
---
# CLI internals

These helpers form the command parser and dispatch seams behind the public `farrier` commands.

## Methods

### method: _add_install_args
- sig: `_add_install_args(parser: argparse.ArgumentParser) -> None`
- does: add repository, config, check, library, user, home, and unresolved-library options to an install parser
- verify: count(subject="install parser options", equals=1)
- code: `farrier/farrier/cli.py::_add_install_args`

### method: _flatten
- sig: `_flatten(table: dict[str, Any], prefix: str = '') -> list[tuple[str, Any]]`
- does: flatten nested configuration mappings into dotted leaf paths in source order
- verify: count(subject="flattened configuration leaves", equals=1)
- code: `farrier/farrier/cli.py::_flatten`

### method: _dispatch_config
- sig: `_dispatch_config(args: argparse.Namespace) -> int`
- does: execute config setters or show top-level/profile values and print their result
- raises: `SystemExit` when a requested value is unset or a setter path is invalid
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_dispatch_config`

### method: find_agents_config
- sig: `find_agents_config(start: Path) -> Path | None`
- does: locate the nearest `agents.yml` at or above a generated file's directory
- verify: count(subject="nearest agents.yml lookup", equals=1)
- code: `farrier/farrier/cli.py::find_agents_config`

### method: mapped_instruction_sources
- sig: `mapped_instruction_sources(generated: Path) -> list[str] | None`
- does: resolve a local-instruction output through the live localInstructions mapping and current library selection
- raises: `SystemExit` when an existing agents.yml no longer maps the generated file
- verify: count(subject="live localInstructions source mappings", equals=1)
- code: `farrier/farrier/cli.py::mapped_instruction_sources`

### method: _list_scaffolds
- sig: `_list_scaffolds(defs: dict[str, dict[str, Any]], available: set[str], repo: Path) -> int`
- does: print available scaffold ids, descriptions, and parameter defaults or required markers
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_list_scaffolds`

### method: _build_parser
- sig: `_build_parser() -> argparse.ArgumentParser`
- does: construct the complete farrier command and subcommand parser
- verify: count(subject="registered farrier subcommands", equals=10)
- code: `farrier/farrier/cli.py::_build_parser`

### method: _run_hooks
- sig: `_run_hooks(args: argparse.Namespace) -> int`
- does: wire the repository hook manager without resolving or rendering a library
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_hooks`

### method: _selected_layer
- sig: `_selected_layer(args: argparse.Namespace) -> str | None`
- does: convert an optional base/overlay CLI choice to the active layer label
- verify: count(subject="selected library layer labels", equals=1)
- code: `farrier/farrier/cli.py::_selected_layer`

### method: _run_library_list
- sig: `_run_library_list(args: argparse.Namespace) -> int`
- does: print layer headers and the selected library catalog kinds
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_library_list`

### method: _run_library_show
- sig: `_run_library_show(args: argparse.Namespace) -> int`
- does: print exactly one resolved library source, optionally from a selected layer
- raises: `SystemExit` unless exactly one item kind is requested or the item is unavailable
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_library_show`

### method: _run_library_check
- sig: `_run_library_check(args: argparse.Namespace) -> int`
- does: check each distinct active library layer and return nonzero for errors or strict warnings
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_library_check`
