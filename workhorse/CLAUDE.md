# local-worker

You are working inside `agents/local-worker` — the Dockerized agent controller
that runs YAML-defined workflows with the Claude CLI, designed to run agent
workflows **unattended for up to a week**.

## Orientation

- The full usage + development guide is the README, imported below. Read its
  **Development** section before changing the controller: project layout, the
  graph-walk loop, where tests and docs go, and conventions.
- The error-recovery design (the retry → reframe → default ladder that keeps a
  long run from crashing on one bad node) is in docs/GUARDRAILS.md, imported below.

## Working rules (most load-bearing)

- **Fail soft for unattended runs.** New failure paths in agent-node handling
  must slot into the existing retry → reframe → default ladder in
  `workhorse/runner/agent.py`, not raise. One bad node must never end the run.
  Reserve hard raises for unrecoverable, deterministic errors.
- **Tests go in `tests/test_<area>.py`** and must be dependency-free and
  standalone: patch the CLI boundary (`_run_claude_cli` / `_invoke_claude`) and
  sleeping so nothing hits the network or waits in real time. Run with
  `.venv/bin/python tests/test_*.py`. Add/extend a test for any behavior change.
- **Keep README.md and docs/GUARDRAILS.md current** when behavior changes — they are
  the operator contract and are imported here.
- **Controller `.py` is COPY'd into the image, not bind-mounted** — changes take
  effect only after an image rebuild (add `--build` to the `docker compose up`).
- **Stay repository-agnostic.** Never add repo-specific bind mounts to
  `compose.yaml`; workflows clone what they need via their own `setup.sh`.
- **Stay workflow-agnostic (separation of concerns).** Workhorse is a generic
  engine shared by every workflow. Never bake one workflow's vocabulary into it —
  no `plan-context`/`plan_result` field names (`services[].type`, `touched_layers`,
  layer→platform maps), no workflow-specific Jinja globals in `templates.py`, no
  branching on a particular env-var/repo/story name. A value derived from a
  workflow's own data belongs in that workflow (a `script:` node or the prompt's
  Jinja over context), not in `workhorse/**`. If workhorse genuinely needs a new
  capability, add a **parameterised primitive** that knows no workflow's schema —
  `resolve_workspace(env_key)` is the model (the workflow passes the key; workhorse
  just reads it). Litmus test: *would a different workflow want this unchanged?* If
  not, it belongs in the workflow.

@README.md

@docs/GUARDRAILS.md
