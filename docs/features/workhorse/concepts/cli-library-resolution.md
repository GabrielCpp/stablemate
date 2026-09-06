---
type: concept
slug: cli-library-resolution
title: CLI library-directory resolution
---
# CLI library-directory resolution

The run invocation carries library roots resolved at the CLI boundary. The overlay is selected
from `FARRIER_LIBRARY_DIR`, then configured `library_dir`; the usable base root follows from
`base_library_dir()`. Missing candidates are omitted, duplicate paths are emitted once, and this
lookup never downloads or populates a library.

- code: `workhorse/workhorse/cli/run.py::library_dirs`
- code: `workhorse/workhorse/cli/run.py::invocation`
- tests: `workhorse/tests/test_console_script.py::test_the_overlay_precedes_the_base_and_absent_layers_are_dropped`

## Methods

### library-dirs
- sig: `library_dirs(cfg: dict[str, Any]) -> list[str]`
- does: choose the environment overlay before the configured overlay
- does: append the discovered base-library directory after the overlay
- does: omit empty or non-directory candidates
- does: preserve precedence while removing duplicate directory strings
- returns: existing library roots in overlay-then-base order
- verify: count(subject="resolved library roots when overlay and base directories exist", equals=2)
- code: `workhorse/workhorse/cli/run.py::library_dirs`

### invocation
- sig: `invocation(args: argparse.Namespace) -> RunInvocation`
- does: validate the bound registry directory before starting a state
- does: resolve runs, resume, profile, backend, workflow parameters, context, runtime config, and telemetry into one `RunInvocation`
- does: default `repo_dir` from `AGENT_REPO_DIR` or the launch directory
- does: default `library_dirs` from the library resolution ladder
- returns: a driver-ready `RunInvocation` carrying the bound registry and resolved run settings
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/run.py::invocation`
