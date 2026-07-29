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

**Loop 1, closing out.** Steps 1, 3, 4, 5, 6 are committed. **Step 2 was skipped** and step 7 is
in flight. Resume with the prompt under "Resuming loop 1 mid-flight" in the plan — not the full
loop 1 prompt, which specifies mostly-finished work.

## What landed

| Step | Commit | What |
|---|---|---|
| 1 | `740a6ef` | Workflow discovery via `workhorse.workflows` entry points, not just library paths |
| 3 | `7cae8d1` | farrier stops reading workflow prompts |
| 4 | `5bb7e29` | Unresolvable skill/prompt references are named rather than rendered into a live prompt |
| 5 | `ea47ff7` | The Python state-machine driver — `workhorse/workhorse/pyflow/`, 2,350 lines |
| 6 | `53dc4ba` | State graph read off the source, for `--dry-run` and `dot` |
| — | _this commit_ | `research/models.py` → `schemas.py`; `self.agent(power=, timeout=)` reaches the turn |

## What is next

1. **Step 2 — the scriptutil split.** Never started: `workhorse/workhorse/scriptutil.py` still
   holds `github_client`, `open_repo`, `push_branch`, `resolve_workspace` and the rest, and
   `gitpython`/`PyGithub` are still required dependencies in `workhorse/pyproject.toml:32-33`.
   It goes **before** finishing the port: `research/nodes.py:28-36` already imports **seven**
   names from `workhorse.scriptutil` (`allow_all_directories`, `checkout`, `clone`, `commit_all`,
   `fetch_reset`, `push_to_origin`, `set_identity`), so doing the split afterwards means rewriting
   the port. 60 files under `base-library/` import a moving name; 6 of them use the patchable
   `from workhorse import scriptutil` form and must be repointed at the *defining* submodule.
2. **Step 7 — the `research` port**, resumed once step 2 has moved the seam under it.

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
