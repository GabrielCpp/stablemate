---
type: concept
slug: workflow-kit-tools
title: Workflow kit external tools
---
# Workflow kit external tools

- code: `workflows/src/workhorse_workflows/kit/tools.py::run_tool`
- extends:
- rule:
- prefers:
- deprecates:
- tests:

This is the workflow kit's seam for an external CLI that has no in-process facade. It executes
the supplied argument vector as a real subprocess, captures the child's text output, and returns
the completed process so callers can choose whether a non-zero result is recoverable. Git, GitHub,
and Ostler calls use their dedicated kit or library facades instead of this seam.

The genesis workflow patches this callable at its module boundary with a canned
`subprocess.CompletedProcess`, which keeps its tests independent of an installed `farrier` binary.

## Methods

### run_tool
- sig: `run_tool(argv: list[str], cwd: str | pathlib.Path | None = None, *, check: bool = False, logger: logging.Logger | None = None) -> subprocess.CompletedProcess`
- does: starts the external program named by `argv[0]` with the complete `argv` list
- verify: exit_status(code=0)
- does: runs the child with the supplied `cwd`, or inherits the caller's working directory when `cwd` is `None`
- does: captures standard output as text
- verify: json_path(path="return.stdout", matches=".*")
- does: captures standard error as text
- verify: json_path(path="return.stderr", matches=".*")
- does: returns normally for the child's non-zero status when `check` is `False`
- verify: json_path(path="return.returncode", equals=1)
- does: when `check` is `True` and the child exits non-zero, logs the command, exit code, and trimmed standard error if `logger` is supplied
- does: when `check` is `True` and the child exits non-zero, raises `RuntimeError` naming the executable and trimmed standard error
- verify: exit_status(code=1)
- raises: propagates operating-system or process-launch errors from the subprocess invocation
- returns: the `subprocess.CompletedProcess` for the child, including its arguments, return code, captured text standard output, and captured text standard error
- code: `workflows/src/workhorse_workflows/kit/tools.py::run_tool`
- detail:
- fixture:
- tests: `workflows/tests/coder/genesis/test_flow.py::test_a_bare_directory_becomes_a_repo_the_main_loop_will_accept`
