---
type: concept
slug: docker-subprocess-runner-documentation
title: Docker subprocess runner documentation
---
# Docker subprocess runner documentation

`_run` has one implementation: it directly invokes `subprocess.run` with the supplied argument
vector, captured text output, timeout, and optional standard input. The source contains no
alternative runner, wrapper, deprecation marker, or caller-specific implementation to rank.

The [Docker subprocess runner](docker-subprocess-runner.md#run) is the complete contract to read
when choosing how the shared execution layer handles process creation, output, return codes, and
exceptions. The [folded module member](groom-docker-io-module.md#method-run) is the same internal method
in the Docker I/O module inventory; use it to locate `_run` among the module's public helpers and
their delegation path. Neither entry supersedes the other.

- code: groom/groom/docker_io.py::_run
- rule: use the standalone runner entry for `_run` behavior and the folded module entry for its place in the Docker I/O adapter; they document one implementation rather than competing alternatives.
- detail: [Docker subprocess runner: which entry to read](docker-subprocess-runner-selection.md)
