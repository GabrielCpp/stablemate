---
type: concept
slug: docker-subprocess-runner-selection
title: 'Docker subprocess runner: which entry to read'
---
# Docker subprocess runner: which entry to read

`_run` has exactly one implementation in `groom/groom/docker_io.py`. Two `concept` nodes ground
themselves in that one symbol, and neither supersedes the other — they answer different
questions about the same code, and both stay current:

- [Docker subprocess runner](docker-subprocess-runner.md#run) is the complete behavioural
  contract for `_run` — its inputs, its process-launch and capture behaviour, what it returns,
  and what it deliberately leaves to the caller. Read it to learn what `_run` does.
- [Docker subprocess runner documentation](docker-subprocess-runner-documentation.md) states
  that `_run` has no alternative runner, wrapper, or caller-specific implementation to rank, and
  points at the [folded module member](groom-docker-io-module.md#method-run) entry for `_run`'s
  place among the Docker I/O module's other helpers. Read it to locate `_run` in the module
  inventory, not to learn its contract.

- rule: read the standalone runner entry for what `_run` does; read the documentation entry only to locate `_run` among the Docker I/O module's helpers. Neither entry is deprecated or preferred over the other — they cover different questions about the one implementation.
