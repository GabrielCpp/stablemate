# stablemate

This package installs the stablemate agent tools in one step, at versions tested together.
It has no code and no command of its own. It depends on three distributions:

| Distribution          | What you get                                                          |
| --------------------- | --------------------------------------------------------------------- |
| `workhorse-workflows` | The agent workflows, one command each: `workhorse-loop-runner`, `workhorse-coder` and the rest. |
| `farrier`             | The `farrier` command, which renders the prompt library into a repository. |
| `stablemate-groom`    | The `groom` dashboard and telemetry collector, plus `groom-sidecar`.  |

## Install

```bash
uv tool install workhorse-workflows --with stablemate --with-executables-from farrier,stablemate-groom
```

You need [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer.

The line names `workhorse-workflows` first because uv refuses to install a package with no
commands as a tool, and this package has none. `--with stablemate` holds all three tools at
the versions this package pins. `--with-executables-from` puts the `farrier` and `groom`
commands on your PATH next to the workflow commands.

Check the install:

```bash
workhorse-loop-runner run --dry-run
farrier --help
groom --help
```

## Versions

Each release of this package pins one exact version of each tool. To move all three to the
newest release, run:

```bash
uv tool upgrade workhorse-workflows
```

The tools, their docs and their changelogs live in the
[stablemate repository](https://github.com/GabrielCpp/stablemate).
