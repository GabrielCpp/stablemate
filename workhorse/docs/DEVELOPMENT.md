# Developing workhorse itself

This document is for working on the **controller itself** — the Python that runs
workflows — not on individual workflows. For those, see
[docs/AUTHORING.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md).
It assumes you have cloned the [stablemate](https://github.com/GabrielCpp/stablemate)
repository and are working in its `workhorse/` directory, rather than having installed
`workhorse-agent` from PyPI. Common tasks are wrapped in the
[`Makefile`](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/Makefile)
(`make help`): `make install`, `make test`, `make build`, `make publish`.

## Project layout

```
workhorse/                     # this directory, inside the stablemate workspace
├── workhorse/                 # The workhorse Python package (entrypoint: workhorse:main)
│   ├── cli/                   # The `workhorse` command line — parse argv, dispatch, hand off
│   │   ├── __init__.py        # main(): argv normalization, the per-workflow console script
│   │   ├── parser.py          # The Command table and the one parser built from it
│   │   ├── run.py             # `run`: its arguments, and the RunInvocation it builds
│   │   ├── test.py            # `test`: run a workflow's own pytest suite
│   │   ├── dot.py             # `dot`: render a workflow's state graph as Graphviz DOT
│   │   ├── config.py          # `config`: show / set / list / get the shared config file
│   │   ├── version.py         # `version`: print the installed workhorse-agent version
│   │   ├── resolve.py         # A workflow name → its installed Registry (`run` and `dot`)
│   │   └── params.py          # --params / --params-file → the starting params dict
│   ├── packaged.py            # Entry-point discovery: what `workhorse run <name>` resolves to
│   ├── rundir.py              # Run identity: the (workflow, run-id) dir and the resume contract
│   ├── manifest.py            # The per-repo context manifest (ContextManifest → ManifestContext)
│   ├── context.py             # WorkflowContext: the key→value bag prompts render against
│   ├── templates.py           # Jinja2 rendering (resilient: missing vars render empty, not raise)
│   ├── references.py          # Static skill/prompt reference checking (the --dry-run warning)
│   ├── artifacts.py           # ArtifactWriter: run dir, checkpoints, per-step artifacts
│   ├── records.py             # The models for what a run writes and reads back (checkpoint, event)
│   ├── otel.py                # OpenTelemetry facade (auto-on if a collector answers; else no-op)
│   ├── config_run.py          # The shared config file: power tiers, defaults, harness env
│   ├── logsetup.py            # Logging configuration for the driver and node functions
│   ├── stack.py               # ensure_stack / teardown_stack: a long-lived stack across nodes
│   ├── worklist.py            # A resumable work queue (WorkItem / WorkCounts / WorkSnapshot)
│   ├── scriptutil.py          # Helpers for the shell steps a workflow shells out to
│   ├── testing.py             # make_git_repo + the artifact assertions a workflow test uses
│   ├── pyflow/                # The Python state-machine driver
│   │   ├── workflow.py        # The `Workflow` base class: state discovery, freezing, self.ctx
│   │   ├── transitions.py     # Continue / Done / Await + transition-time signature binding
│   │   ├── blueprint.py       # `Blueprint`: node libraries a workflow composes
│   │   ├── registry.py        # What an entry point / console script points at
│   │   ├── engine.py          # self.call / self.agent / self.handoff / self.output
│   │   ├── driver.py          # drive(): the state loop, the (state, params) checkpoint, Await
│   │   ├── run.py             # RunInvocation + run_pyflow(): run dir, dry run, exit code
│   │   ├── graph.py / dot.py  # Read the states' source; render Graphviz DOT (`workhorse dot`)
│   │   ├── activity.py        # The flagged-log-record activity tracker (a logging.Filter)
│   │   ├── errors.py          # WorkflowFailed, NodeNotRunError and the rest of the exceptions
│   │   └── names.py           # NameIndex: live names + aliases, collisions raise at import
│   └── runner/
│       ├── ladder.py          # AgentRunner: render the prompt, drive the retry → cap-wait →
│       │                      #   compact → reframe → default ladder, return the outputs
│       ├── clock.py           # The Clock port and the system one — what the ladder waits on
│       ├── failure.py         # The turn's error types, its markers and its classifier
│       ├── process.py         # Spawn an agent CLI: process group, watchdog, stream loop
│       ├── caps.py            # How long to wait out a scheduled-reset cap, and how to sleep it
│       ├── reframe.py         # The ladder's substitute prompts and its default outputs
│       ├── extract.py         # Recover the node's declared outputs from a free-form answer
│       ├── backends/          # The agent-CLI port and its adapters
│       │   ├── __init__.py    # AgentBackend: the port, and nothing else
│       │   ├── registry.py    # name → backend class; the only module importing every adapter
│       │   ├── claude.py      # One adapter per CLI: its argv, its event stream, its /compact
│       │   ├── codex.py       # …
│       │   ├── copilot.py
│       │   ├── opencode.py
│       │   ├── aider.py
│       │   ├── turn.py        # TurnState + finalize_turn: what a non-Claude turn accumulates
│       │   └── jsonl.py       # stream_jsonl: the shared JSONL stream loop
│       ├── usage.py           # Normalize each harness's token/cost reporting onto one shape
│       └── spec.py            # OutputSpec / AgentNode: what one agent turn declares
├── tests/                     # Standalone test files (see below)
├── compose.yaml               # Service, env, mounts, named volumes
├── Dockerfile                 # Ubuntu + uv + Claude CLI + the controller package
├── entrypoint.sh              # Non-root auth seeding, checkout, exec `workhorse`
├── Makefile                   # install / test / build / publish tasks (`make help`)
├── pyproject.toml             # Python deps (jinja2, pydantic); the lock is the workspace's
├── README.md                  # What workhorse is, install, and the CLI (the PyPI page)
├── CLAUDE.md                  # Agent entry point; imports docs/GUARDRAILS.md
└── docs/
    ├── GUARDRAILS.md          # The resilience/error-recovery design and env-var reference
    ├── BACKENDS.md            # Agent CLI backends, power→model mapping, the config file
    ├── AUTHORING.md           # Writing a workflow: states, nodes, transitions, checkpoints
    ├── DEVELOPMENT.md         # This file — working on the controller itself
    ├── DOCKER.md              # The Docker harness (image + compose) for unattended runs
    └── WORKFLOW.md            # Migrating a retired `workflow.yaml` to a Python workflow
```

## How the controller works (the loop)

`pyflow/driver.py::drive` is a single loop over states. For each transition it:

1. **Checkpoints** `(state, params)` plus the frozen inputs and `ctx`
   (`ArtifactWriter.write_state_checkpoint`) so a crash here is resumable.
2. **Calls** the state method, which does its work through `self.call` (a node
   function), `self.agent` (an agent turn) or `self.handoff` (a sub-flow) — each of
   which writes its own per-step artifact.
3. **Binds** the returned transition's keyword arguments against the target state's
   signature, so a wrong parameter name fails on the transition that made it.
4. **Advances** to that state.

`Done` ends the flow and `WorkflowFailed` ends the run; `Await` checkpoints first and
then polls for the answer file. The resilience for agent turns lives entirely in
`runner/ladder.py`'s `AgentRunner` — see [docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).

## Sessions (per-turn clean context)

**Each agent turn runs as a fresh prompt with a clean Claude context.** The controller
does *not* chain one turn's conversation into the next — turn N does not inherit
turn N‑1's messages. Concretely, `AgentRunner.run` drops any persisted `.session_id`
before a turn's first attempt, and a reframed attempt also starts fresh.

The persisted session is `--resume`d in exactly one situation: **continuing the
same turn that was interrupted.** When the controller resumes from a checkpoint and
re-enters the state that was killed mid-run, that turn calls
`AgentRunner.run(..., resume_session=True)` so Claude picks up where it left off; every turn
the run then reaches starts clean again.

**Context overflow → compact & continue.** If a turn exhausts the model's
context window mid-run (the headless CLI returns instead of auto-compacting),
`AgentRunner` runs `/compact` on that turn's session and retries the *same* prompt
on it, preserving the turn's progress (bounded by `AGENT_MAX_COMPACT_ATTEMPTS`;
falls back to a fresh-session reframe if `/compact` can't help). Verified against
Claude Code 2.1.x. See the recovery ladder in [docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).

> Not yet implemented: a configurable *per-turn* limit (`--max-turns`) that
> proactively compacts before the window is exhausted. Today compaction is
> reactive — triggered when an overflow is detected.

## Running tests

Tests live in `tests/` and are **dependency-free**: each file runs standalone
(`uv run python tests/test_x.py` prints PASS/FAIL and exits non-zero on failure) and is
also pytest-compatible. There is no pytest in the venv by default; run them with
the project's Python:

```bash
# All of them (via the Makefile)
make test

# One file
uv run python tests/test_agent_recovery.py
```

If a `.venv` isn't present, create one with `uv sync` (or `make install`).

**Where to put tests.** There are two styles. Controller-internal tests add a
`tests/test_<area>.py` that injects the CLI boundary (a fake `AgentBackend` from
`tests/_fakes.py`) and injects the clock (a `FakeClock` from the same module) so nothing
hits the network or waits in real time:
`test_agent_cap.py` (cap/transient handling), `test_agent_recovery.py` (reframe →
default ladder), `test_resume_auto.py`, `test_idempotency.py`,
`test_templates_resilient.py`.

**Whole-workflow tests** drive a real workflow through `drive()` in the current
process — no `workhorse` CLI subprocess and no PATH shims. They substitute rather than
patch: agent turns are answered by an `agent_runner` handed to the `RunEnv`, and node
functions by `Registry.override(...)`, so neither stand-in can outlive the run (see
[The node index is the substitution seam](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md#the-node-index-is-the-substitution-seam)).
Local `git` runs for **real** against a throwaway repo built with
`workhorse.testing.make_git_repo` — git is never mocked. `workhorse.testing` also
carries the artifact assertions (`assert_file`, `assert_file_contains`,
`assert_json_file`) a workflow test makes about what a run left on disk.

## Where docs go

- **`README.md`** (root) is the front door and the PyPI landing page: what workhorse is,
  install, the CLI, and a summary-plus-link for everything below. Because it renders
  off-repo, every link it makes to another file must be an **absolute** forge URL —
  a relative one 404s on PyPI.
- **Everything long-form** → `docs/`, one topic per file, `SCREAMING-KEBAB.md`:
  `GUARDRAILS.md` (resilience design + env-var reference), `BACKENDS.md` (CLI backends,
  the power→model config), `AUTHORING.md` (writing a workflow), `DEVELOPMENT.md` (this
  file), `DOCKER.md` (the harness). Add new reference and design docs here, not at the
  root, and leave a one- or two-sentence summary in the README beside the link.
- **`CLAUDE.md`** (root) is the agent entry point and stays at the root so Claude
  Code auto-loads it. It is a standing instruction file loaded on every turn in this
  subtree, so it carries rules an agent would get wrong by default and nothing else; it
  `@`-imports only `docs/GUARDRAILS.md` and *links* the rest.
- **Per-workflow docs** → inside that workflow's own package directory (under
  `../workflows/src/workhorse_workflows/<name>/`), not here. The controller is workflow-agnostic; keep
  workflow-specific knowledge with the workflow.

Keep these docs current when you change behavior — they are the contract for
operators running week-long jobs, and `CLAUDE.md` imports one of them, so updating
them keeps agent context accurate too.

## Conventions

- **Python 3.12**, `from __future__ import annotations` at the top of each module.
- **Pydantic** models for anything crossing a boundary — an agent's JSON reply, a
  node's return value, the context manifest. A state declares what it expects
  (`returns=`) and the runner validates into it; nothing downstream re-checks shapes.
- **Fail soft for unattended runs.** New failure paths in agent handling should
  slot into the existing retry → reframe → default ladder rather than raising, so
  one bad node can't end a week-long run. Reserve hard raises for genuinely
  unrecoverable, deterministic errors.
- **Comments explain *why*.** Match the existing density — the tricky invariants
  (checkpoint/fast-forward idempotency, cap-vs-transient classification) are
  documented inline; keep them that way.

## Editing the container

The repo ships a Docker harness (`Dockerfile`, `compose.yaml`, `entrypoint.sh`)
for isolated unattended runs. It is not part of the PyPI package; its build/run
workflow — including rebuilding the image after controller or `pyproject.toml`
changes — is documented in [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).
