# stablemate

This package installs the stablemate agent tools in one step, at versions that work together.
It has no code of its own. It depends on four distributions and puts each one's commands on
your PATH:

| Distribution          | What you get                                                          |
| --------------------- | --------------------------------------------------------------------- |
| `workhorse-workflows` | The agent workflows, one command each: `workhorse-loop-runner`, `workhorse-coder` and the rest. |
| `farrier`             | The `farrier` command, which renders the prompt library into a repository. |
| `stablemate-groom`    | The `groom` dashboard and telemetry collector, plus `groom-sidecar`.  |
| `ostler`              | The `ostler` command, which checks and edits a repository's `docs/` graph. |

## Install

```bash
uv tool install stablemate
```

You need [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. pipx works too:

```bash
pipx install stablemate
```

Check the install:

```bash
workhorse-loop-runner run --dry-run
farrier --help
groom --help
ostler --help
```

## Versions

Each release of this package allows one major version of each tool. To move all four to
their newest release within it, run:

```bash
uv tool upgrade stablemate
```

The tools, their docs and their changelogs live in the
[stablemate repository](https://github.com/GabrielCpp/stablemate).
