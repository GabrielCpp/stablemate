# workhorse

You are working inside `workhorse/` — the engine that drives an agent CLI through
workflows written as **Python state machines**, designed to run **unattended for up to a
week**. The PyPI distribution is `workhorse-agent` and the import package is `workhorse`.
It is a **library**: it ships no command of its own, only the wiring
(`workhorse.console_script`) a workflow distribution uses to bind *its* command. The
workflows it runs are not here — they live in `workflows/` (`workhorse-workflows`), each
declaring its own console script (`workhorse-coder run …`).

What an editor of the engine needs, before the rules below: paths here are relative to
this directory, so the package is `workhorse/` — inside it, `pyflow/` holds the
state-machine driver (`workflow.py`
declares states, `driver.py` is the state loop and checkpoint, `engine.py` provides
`self.call` / `self.agent` / `self.output`) and `runner/` holding the agent-CLI side
(`ladder.py` holds the `AgentRunner` service — the recovery ladder over `failure.py` /
`process.py` / `caps.py` / `reframe.py` / `extract.py`, driven with an injected `Clock`
from `clock.py` — and `backends/` the agent-CLI port and one adapter module per CLI). `make help` lists
the tasks; `make test` runs the suite. [README.md](README.md) is what workhorse is and how
to run it; the guide for changing the engine — project layout, the loop, sessions, where
docs go, conventions — is [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Read that one first.

## Working rules (most load-bearing)

- **Fail soft for unattended runs.** New failure paths in agent-node handling must slot
  into the existing retry → compact → reframe → default ladder in
  `workhorse/runner/ladder.py`, not raise. One bad node must never end the run. Reserve
  hard raises for unrecoverable, deterministic errors.
- **Tests go in `tests/test_<area>.py`** and must be dependency-free and standalone: each
  file runs under plain `uv run python tests/test_x.py` (and is also pytest-compatible),
  injecting the CLI boundary (a fake `AgentBackend` from `tests/_fakes.py`) and the
  clock (a `FakeClock` from the same module) so nothing hits the network or waits in
  real time. `make test` runs them all. Add or extend a test for any behavior change.
- **Keep README.md and the matching `docs/` file current** when behavior changes — they
  are the operator contract, and GUARDRAILS is imported here. Which file is which is in
  [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#where-docs-go).
- **The engine's `.py` is COPY'd into the image, not bind-mounted** — changes take effect
  only after an image rebuild (add `--build` to the `docker compose up`). The build
  context is the repo root, not this directory.
- **Stay repository-agnostic.** Never add repo-specific bind mounts to `compose.yaml`; the
  container's checkout step clones the repos each run needs.
- **Stay workflow-agnostic (separation of concerns).** Workhorse is a generic driver
  shared by every workflow, so it must never learn the shape of one workflow's data. Not
  in `workhorse/**`: a particular workflow's field names (the coder workflow's
  `plan-context.json` and its `services[].type` / `touched_layers` / layer→platform maps
  are the standing example — they live in `workflows/`, and that is where they stay), a
  Jinja global in `templates.py` that derives a workflow-specific value, or branching on a
  particular env-var, repo or story name. A value derived from a workflow's own data
  belongs in that workflow — a `@blueprint.node` function, or the prompt's Jinja over its
  args.

  If workhorse genuinely needs a new capability, add a **parameterised primitive** that
  knows no workflow's schema. `ostler/qa/stack.py` is the model, and it lived here until
  it grew a durable home in ostler: `ensure_stack` / `teardown_stack` own a long-lived
  stack across nodes, and the workflow hands them a manifest dict rather than the
  primitive knowing what a stack of *theirs* looks like. Litmus
  test: *would a different workflow want this unchanged?* If not, it belongs in the
  workflow.

@docs/GUARDRAILS.md
