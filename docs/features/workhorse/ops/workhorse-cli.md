---
type: runbook
title: workhorse-loop-runner from a checkout
---
# workhorse-loop-runner from a checkout

The `workhorse-loop-runner` script runs once per command and exits, so nothing stays up between
commands. Bring-up only confirms the script is installed and answers. Every scenario then runs
the script in its own working directory.

- driver: cli
- surfaces: [workhorse](../workhorse.md)
- reuse: always

## Steps

### installed

- kind: prepare
- run: workhorse-loop-runner version
- timeout: 60
