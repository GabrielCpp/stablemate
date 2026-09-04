# Developing workhorse itself

This document is for working on the **controller itself** — the Python that runs
workflows — not on individual workflows. For those, see
[docs/AUTHORING.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md).
It assumes you have cloned the [stablemate](https://github.com/GabrielCpp/stablemate)
repository and are working in its `workhorse/` directory, rather than having installed
`workhorse-agent` from PyPI. Common tasks are wrapped in the
[`Makefile`](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/Makefile)
(`make help`): `make install`, `make test`, `make build`. Nothing here publishes —
releases are opened by `make release` at the repo root and uploaded from CI; see the
root README's [Releasing](https://github.com/GabrielCpp/stablemate#releasing).

## Project layout

```
workhorse/
├── workhorse/
│   ├── cli/          # run, dot, control, inbox, and version for workflow-owned commands
│   ├── pyflow/       # state discovery, transitions, checkpoints, driving, and diagrams
│   ├── runner/       # agent process, backends, recovery ladder, usage, and transcripts
│   └── *.py          # run artifacts, config, gates, jobs, reload, templates, and testing
├── tests/            # engine tests and reusable fakes
├── docs/             # focused operator, authoring, and development references
├── Dockerfile
├── compose.yaml
└── supervisor.py     # container preflight and child-process supervision
```

The package intentionally has no standalone console entry point. Workflow
distributions call `workhorse.console_script(...)` to expose their own command.

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

**Named chains are the one deliberate exception.** A state that asks for
`self.agent(..., session="docs-repair:STORY-4")` files that turn's session id under
`<run_dir>/.sessions/<key>` (`workhorse/sessions.py` owns the layout) and asks the ladder
to resume it, so the laps of a repair loop are one conversation instead of one
re-derivation per lap. Everything else keeps the clean context above — `.session_id` is
untouched by a chain, and a chain the CLI will not resume is dropped and re-run once on a
fresh session, costing no retry and no reframe. The authoring rules, including when to
`self.reset_session(key)`, are in
[docs/AUTHORING.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md).

**Context overflow → compact & continue.** If a turn exhausts the model's
context window mid-run (the headless CLI returns instead of auto-compacting),
`AgentRunner` runs `/compact` on that turn's session and retries the *same* prompt
on it, preserving the turn's progress (bounded by `AGENT_MAX_COMPACT_ATTEMPTS`;
falls back to a fresh-session reframe if `/compact` can't help). Verified against
Claude Code 2.1.x. See the recovery ladder in [docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).

## Running tests

Tests live in `tests/` and run against the shared workspace environment. Set the
workspace up from the repository root so every member dependency is installed:

```bash
make install
make -C workhorse test

# One file
uv run pytest workhorse/tests/test_agent_recovery.py -q
```

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
  the power→model config, profiles), `RELOAD.md` (the control channel into a live run),
  `TELEMETRY.md` (enabling telemetry, what is emitted, and how to read it),
  `CHECKING.md` (`--dry-run` and `dot`), `RUNS.md` (run identity, resume, artifacts),
  `AUTHORING.md` (writing a workflow), `JOBS.md` (the detached job runner),
  `DEVELOPMENT.md` (this file), `DOCKER.md` (the harness). Add new reference and design
  docs here, not at the root, and leave a one- or two-sentence summary in the README
  beside the link.
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

The repo ships a Docker harness (`Dockerfile`, `compose.yaml`, `supervisor.py`)
for isolated unattended runs. It is not part of the PyPI package; its build/run
workflow — including rebuilding the image after controller or `pyproject.toml`
changes — is documented in [docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).
