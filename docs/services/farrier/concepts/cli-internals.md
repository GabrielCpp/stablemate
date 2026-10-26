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
- does: describe `--home` as the directory the user library installs into, and `--user` as installing the harness home from the `[user_library.<harness>]` tables; combined with `--repo` it installs the repo first, then refreshes the home afterward
- does: describe `--repo` as the repository root to install into, resolved to cwd when omitted, that writes only under that root unless `--user` is also given
- verify: count(subject="install parser options", equals=1)
- code: `farrier/farrier/cli.py::_add_install_args` @2eeeeaa1740e

### method: _flatten
- sig: `_flatten(table: dict[str, Any], prefix: str = '') -> list[tuple[str, Any]]`
- does: flatten nested configuration mappings into dotted leaf paths in source order
- verify: count(subject="flattened configuration leaves", equals=1)
- code: `farrier/farrier/cli.py::_flatten` @2eeeeaa1740e

### method: _dispatch_config
- sig: `_dispatch_config(args: argparse.Namespace) -> int`
- does: execute config setters or show top-level/profile values and print their result
- raises: `SystemExit` when a requested value is unset or a setter path is invalid
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_dispatch_config` @2eeeeaa1740e

### method: find_agents_config
- sig: `find_agents_config(start: Path) -> Path | None`
- does: locate the nearest `agents.yml` at or above a generated file's directory
- verify: count(subject="nearest agents.yml lookup", equals=1)
- code: `farrier/farrier/cli.py::find_agents_config` @2eeeeaa1740e

### method: mapped_instruction_sources
- sig: `mapped_instruction_sources(generated: Path) -> list[str] | None`
- does: resolve a local-instruction output through the live localInstructions mapping and current library selection
- does: resolve hand-written skill directories declared in `agents.yml` into the sources it returns, alongside the live library selection
- does: list `agents.yml` as the source of an entry whose content is its own `text`
- raises: `SystemExit` when an existing agents.yml no longer maps the generated file
- verify: count(subject="live localInstructions source mappings", equals=1)
- code: `farrier/farrier/cli.py::mapped_instruction_sources` @2eeeeaa1740e

### method: _list_scaffolds
- sig: `_list_scaffolds(defs: dict[str, dict[str, Any]], available: set[str], repo: Path) -> int`
- does: print available scaffold ids, descriptions, and parameter defaults or required markers
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_list_scaffolds` @2eeeeaa1740e

### method: _build_parser
- sig: `_build_parser() -> argparse.ArgumentParser`
- does: construct the complete farrier command and subcommand parser
- verify: count(subject="registered farrier subcommands", equals=11)
- code: `farrier/farrier/cli.py::_build_parser` @2eeeeaa1740e

### method: _run_hooks_install
- sig: `_run_hooks_install(args: argparse.Namespace) -> int`
- does: wire the repository hook manager without requiring a resolved library
- verify: exit_status(code=0)
- does: regenerate the per-repository hook runner when a library resolves and the manager is not `none`
- does: leave outputs other than the hook manager and its runner unchanged while wiring repository hooks
- verify: unchanged(subject="repository outputs other than the hook manager and runner")
- does: print every action prefixed with `[dry-run] ` and write nothing when `--dry-run` is set
- code: `farrier/farrier/cli.py::_run_hooks_install` @2eeeeaa1740e

### method: _run_hooks_list
- sig: `_run_hooks_list(args: argparse.Namespace) -> int`
- does: print each hook stage with the skill and command of every hook the selected skills declare
- does: print `(none)` under a stage no selected skill declares a hook for
- does: warn that declared hooks are not wired when the configured manager is `none`
- raises: exits 1 with an error on stderr when `agents.yml` is missing, unreadable or not a mapping
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_hooks_list` @2eeeeaa1740e

### method: _load_library
- sig: `_load_library(library: Path | None, check: bool) -> None`
- does: fetch or refresh the base library at the release that published this farrier, then layer the overlay over it
- does: print one info line for each skill or prompt a higher layer overrides by name, unless `check` is set
- verify: count(subject="library override notices printed", equals=1)
- code: `farrier/farrier/cli.py::_load_library` @2eeeeaa1740e

### method: _base_library_ref
- sig: `_base_library_ref() -> str`
- does: return `main` for a farrier installed from a checkout or a URL
- does: return the release tag `farrier-v<version>` for a farrier installed from a published release
- returns: the git ref the base library is fetched at
- verify: count(subject="base library ref", equals=1)
- code: `farrier/farrier/cli.py::_base_library_ref` @2eeeeaa1740e

### method: _confirm
- sig: `_confirm(question: str) -> bool`
- does: ask the question on the terminal and accept `y` or `yes` in any case
- returns: `false` for any other answer and when input ends
- verify: count(subject="terminal confirmation answers", equals=1)
- code: `farrier/farrier/cli.py::_confirm` @2eeeeaa1740e

### method: _run_user_install
- sig: `_run_user_install(home: Path | None, check: bool) -> int`
- does: render the `[user_library.<harness>]` tables into the harness home folders under `home`, or the real home when it is `None`
- does: compare instead of writing when `check` is set
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_user_install` @2eeeeaa1740e

### method: _selected_layer
- sig: `_selected_layer(args: argparse.Namespace) -> str | None`
- does: convert an optional base/overlay CLI choice to the active layer label
- verify: count(subject="selected library layer labels", equals=1)
- code: `farrier/farrier/cli.py::_selected_layer` @2eeeeaa1740e

### method: _run_library_list
- sig: `_run_library_list(args: argparse.Namespace) -> int`
- does: print layer headers and the selected library catalog kinds
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_library_list` @2eeeeaa1740e

### method: _run_library_show
- sig: `_run_library_show(args: argparse.Namespace) -> int`
- does: print exactly one resolved library source, optionally from a selected layer
- raises: `SystemExit` unless exactly one item kind is requested or the item is unavailable
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_library_show` @2eeeeaa1740e

### method: _run_library_check
- sig: `_run_library_check(args: argparse.Namespace) -> int`
- does: check each distinct active library layer and return nonzero for errors or strict warnings
- verify: exit_status(code=0)
- code: `farrier/farrier/cli.py::_run_library_check` @2eeeeaa1740e
