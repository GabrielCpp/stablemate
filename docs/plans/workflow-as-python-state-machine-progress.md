---
type: ledger
slug: workflow-as-python-state-machine-progress
title: Workflows as Python — execution ledger
status: active
---
# Workflows as Python — execution ledger

Companion to [workflow-as-python-state-machine.md](workflow-as-python-state-machine.md). The plan
is the spec and does not change as work lands; **this file is the state**, and it exists so an
iteration can learn where it is by reading one page instead of re-deriving it from a 1,350-line
design doc, 2,350 lines of driver, and a full test run. That rediscovery is what drove loop 1's
first run into repeated autocompaction.

## How to keep it

Update this file **in the same commit** as the work it describes — not afterwards, not at the end
of the loop. An iteration that ends with the ledger stale has left the next one nothing to read.

Three things earn a line, and nothing else does:

- **What landed**, with its commit, in one sentence.
- **What is next**, specifically enough to start on without re-reading the plan.
- **Decisions re-confirmed** — every time an iteration has to go back to the plan to settle
  something it thought was open. These are the entries that pay for the file: loop 1 lost
  "typed payload models were removed" across a compaction and rebuilt 224 lines of them.

Do not restate the design here, do not paste diffs, and do not keep a narrative of the run. If an
entry is longer than a few lines it belongs in the plan or in the commit message.

## Current position

**Loop 1 is done.** All seven steps are committed. `research` runs end-to-end on the driver
and the YAML engine is still green (`make test && make check-public`).

Loop 2 starts from: **the second port**. The driver has one workflow proving it; the shapes it
has *not* met yet are `Await` (nothing in `research` waits on a human), `handoff` (no sub-flow),
and a workflow whose states outnumber `research`'s twelve. `author` and `coder` are both, which
is why they are next — and `coder` is the one that will say whether `self.output(node)` and the
three-tier state rule hold at size.

## What landed

| Step | Commit | What |
|---|---|---|
| 1 | `740a6ef` | Workflow discovery via `workhorse.workflows` entry points, not just library paths |
| 3 | `7cae8d1` | farrier stops reading workflow prompts |
| 4 | `5bb7e29` | Unresolvable skill/prompt references are named rather than rendered into a live prompt |
| 5 | `ea47ff7` | The Python state-machine driver — `workhorse/workhorse/pyflow/`, 2,350 lines |
| 6 | `53dc4ba` | State graph read off the source, for `--dry-run` and `dot` |
| — | `5d3f89d` | `research/models.py` → `schemas.py`; `self.agent(power=, timeout=)` reaches the turn |
| 2 | `772b5d0` | The scriptutil split — `workhorse_workflows.kit.{git,github,workspace}`; scriptutil 1000 → 154 lines |
| 7 | `2ea582a` | The `research` port — 30 YAML nodes → 12 states, both pyproject tables, 8 end-to-end tests |
| — | _this commit_ | `--dry-run` reports a fail terminal instead of failing on it (the open question below, answered) |

## What is next

1. **Port `author` (then `coder`).** Same shape as `research`: `nodes.py` + `schemas.py` +
   `workflow.py`, one entry-point line and one console script per workflow in
   `workflows/pyproject.toml`, and end-to-end tests in `workflows/tests/`. Take the test file
   `workflows/tests/test_research_workflow.py` as the pattern — real nodes against a temp git
   repo, only the agent turn scripted — because it is what made the port's claims checkable.

## Open questions

None.

## Decisions re-confirmed

Entries here mean an iteration went back to the plan for something it had lost. The plan section
that settled it is named so the next reader can go straight there.

- **Typed payload models were removed** *("Rejected along the way")*. Lost across a compaction in
  loop 1's first run and rebuilt as `research/models.py`. This is the entry that motivated the
  ledger. **Settled:** what was rebuilt is *not* the rejected shape — nothing in the file crosses a
  transition, and a transition carries keyword arguments bound against the next state's signature.
  What is there is what the seams require: agent-reply schemas (`self.agent(returns=T)`, whose
  fields are also the output keys the resilience ladder nulls out), node return types, and
  `Program`, the `setup()` residue. Kept, renamed `schemas.py`, docstring rewritten so it no longer
  claims to be payloads between states. Do not re-litigate; the name now carries the decision.
- **A fail terminal under `--dry-run` is an artifact of the stand-ins** *(raised by the port,
  answered by the user)*. Stubbed nodes return blank models, so the machine takes whichever
  branch a blank selects — `research` walked `start → goal_review → halt` and exited 1 on a
  clean preflight, and no workflow with a reachable fail terminal could have dry-run green.
  `run.py` now prints the halted state and exits 0 for `WorkflowFailed` **under `--dry-run`
  only**; the run dir is still marked `fail`, and every other `PyflowError` still exits 1. Note
  the shape: it is a branch *inside* `except PyflowError`, not a handler before it — a
  `raise` from a sibling `except` arm escapes the whole `try` rather than falling through to
  the next one, which is what the first attempt got wrong.
- **The `kit` package forwards through `__getattr__`; it does not re-export** *(step 2, found while
  building)*. workhorse re-executes a script module on **every** node run, so a script's
  `from workhorse_workflows.kit import github_client` re-reads that attribute each time — which is
  exactly what made `monkeypatch.setattr(scriptutil, …)` reach into scripts. A plain
  `from .github import github_client` in `kit/__init__.py` would bind once at *package* import,
  one process-lifetime earlier, and every existing patch would silently stop reaching the script.
  PEP 562 module `__getattr__` keeps the old seam: patch the **defining submodule**
  (`kit.git`, `kit.github`, `kit.workspace`) and both the flat importers and `kit`'s own internal
  callers follow. Corollary, and the reason `kit/github.py` says `git_kit.origin_url(...)` rather
  than importing the name: a helper calls across modules **through the module object**.
