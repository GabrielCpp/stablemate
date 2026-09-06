---
type: concept
slug: cli-composition
title: CLI composition and workflow binding
---
# CLI composition and workflow binding

The CLI is composed at the workflow distribution boundary. A workflow supplies its own
`Registry` to `console_script`; the returned callable receives argv, builds the shared parser,
binds the same registry to the parsed namespace, and dispatches the selected command. The
command table is fixed to `run`, `dot`, `control`, `inbox`, and `version`; a workflow name alone
never triggers discovery.

- code: `workhorse/workhorse/cli/__init__.py::console_script`
- code: `workhorse/workhorse/cli/__init__.py::main`
- code: `workhorse/workhorse/cli/parser.py::Command`
- code: `workhorse/workhorse/cli/parser.py::COMMANDS`
- code: `workhorse/workhorse/cli/parser.py::build_parser`
- tests: `workhorse/tests/test_console_script.py::test_console_script_returns_the_callable_without_running_it`
- tests: `workhorse/tests/test_console_script.py::test_a_bare_name_is_not_enough_to_build_a_script`

## Methods

### console_script
- sig: `console_script(workflow: Registry) -> ConsoleEntry`
- does: reject a non-Registry value with `TypeError`
- does: return a callable that invokes `main` with the bound registry and its workflow name
- does: set the returned callable name to `workhorse_<workflow-name-with-hyphens-replaced-by-underscores>`
- returns: the callable entry point without executing the workflow during construction
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/__init__.py::console_script`

### main
- sig: `main(argv: list[str] | None, *, workflow: str, registry: Registry) -> None`
- does: use process arguments after `argv` is omitted, otherwise use the supplied argument list
- does: inject `run` before an empty argv or an argv whose first token is not a known subcommand
- does: leave bare `--help` and `-h` for the top-level parser instead of treating them as `run` input
- does: attach the supplied registry and workflow name to the parsed namespace
- does: dispatch through the selected `Command` row
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/__init__.py::main`

### build-parser
- sig: `build_parser(prog: str, workflow: str) -> argparse.ArgumentParser`
- does: create a parser named by `prog` whose description identifies `workflow`
- does: register one subparser for each command row in `COMMANDS`
- returns: a parser with `command` as the selected-subcommand destination
- verify: count(subject="registered workflow CLI subcommands", equals=5)
- code: `workhorse/workhorse/cli/parser.py::build_parser`
