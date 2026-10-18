---
type: concept
title: Run launch
---
# Run launch

A run is one walk of the workflow's state machine, from its entry flow or from a named flow, to a
terminal state. The [`run`](../workhorse.md#run) command turns its arguments into one run
invocation and refuses early on anything it can check before an agent starts.

The refusals come in a fixed order, so the first problem is the one reported:

1. The `--config` path must name a file. It becomes the only config the run reads.
2. `--cli` and `--profile` exclude each other, because a profile names its own CLI.
3. A resume target must exist. `--resume-latest` picks the newest run directory that has not
   finished, and skips every run that ended done or failed.
4. The profile and the CLI resolve, as [profiles and config](profiles-and-config.md) describes.
5. The params parse. Inline `--params` wins over `--params-file` on a shared key, and both must
   hold one JSON object.
6. The farrier context manifest loads, when one is named or found.

A resumed run named with neither `--cli` nor `--profile` comes back on the profile its `run.json`
recorded. The params always carry `repo_dir` and `library_dirs`. `repo_dir` defaults to
`$AGENT_REPO_DIR`, else the working directory. `library_dirs` lists the overlay library from
`$FARRIER_LIBRARY_DIR` or the config's `library_dir`, then the base library, keeping only those
that exist.

A `--dry-run` swaps every agent turn and every script node for a stand-in. A node whose output
schema declares a reply gets that reply, so the happy path runs end to end without spending a
turn. A dry run that reaches an operator gate fails with `failure_class: dry-run-gate`, because
nothing answers a gate under a dry run and the stand-ins have to walk past it instead. A dry run
is how an author checks the workflow binds.

A `--worktree` run cuts a fresh branch and git worktree first and runs inside it. The run's
records land in its [run directory](run-directory.md). The per-run settings, such as recovery
budgets and timeouts, are fixed when the run starts and do not change under it.

- code: `workhorse/workhorse/cli/run.py::backend_for_profile` @fb229bac321d
- code: `workhorse/workhorse/cli/params.py::load_params` @43dababb9ed6
- code: `workhorse/workhorse/pyflow/run.py::RunInvocation` @328378c45684
- code: `workhorse/workhorse/pyflow/run.py::run_pyflow` @328378c45684
- code: `workhorse/workhorse/pyflow/worktree.py::Worktree` @ced6306a4988
- code: `workhorse/workhorse/pyflow/replies.py::dry_run` @0ccecab8791a
- code: `workhorse/workhorse/manifest.py::ContextManifest` @e896594bc36c
- code: `workhorse/workhorse/config_run.py::RunConfig` @d96de3e447d1
- code: `workhorse/workhorse/config_run.py::AgentResilience` @d96de3e447d1
- code: `workhorse/docs/RUNS.md` @3ef5ce7dac21
