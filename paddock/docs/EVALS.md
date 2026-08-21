# Iterating on a workflow (evals) — designed, not built

Where a greenfield round measures the whole chain once, this is the design for measuring **one node,
many samples, frozen input** — the instrument a prompt edit actually needs. Nothing here is
implemented; the constraints are the settled part, which is why they are written down. See
[README.md](../README.md) for the harness that does exist.

> **Status: not implemented.** No eval harness, no `evals/<workflow>.yml` and no fixture
> store exist in this tree; only `.gitignore` entries for their output do. What follows is
> the design the harness is meant to satisfy, kept here because the constraints are the hard
> part and they are settled.

A greenfield round answers *is the workflow good?* — once, over hours, as a single sample. That
makes it a regression gate and a poor instrument: a prompt edit worth 15 points of node
success rate is invisible in one end-to-end run, and one lucky run "proves" a change that
did nothing.

An eval would measure the other way round: **one node, many samples, frozen input.**

```bash
evals harvest --run ~/runs/author-default   # freeze real node entries as fixtures
evals list                                  # what's in the store
evals run --node write_story                # baseline pass rate
evals compare --node write_story --b candidate-prompt.md
```

Three pieces, all data:

- **fixture** — the exact context a node was entered with in a real run, plus the repo
  commit it read. Harvested from run artifacts, never hand-written, so the distribution
  is the real one.
- **variant** — the change under test, as an *overlay on the workflow package*: a bare
  file replaces the node's prompt, a directory is mirrored over the whole workflow. So an
  edit to the state machine itself, or a stricter validator, is as testable as a reworded
  prompt — which matters, because those are the **stronger** fixes and the tooling should
  not make the weakest one the easiest to try.
- **grader** — the workflow's *own* deterministic gate, named by node id in
  `evals/<workflow>.yml`. `write_story` is graded by `validate_story` and
  `check_story_grounding`, the same two scripts production runs. Not a rubric, not a
  judge: tightening `validate_story` tightens the eval in the same commit, and the two
  can never drift into different opinions of "done".

## What makes the number trustworthy

- **An unanswered node is a failure.** The ladder never fabricates a node's outputs — it
  stops the run instead — so the resilience that keeps unattended runs alive cannot
  quietly score as a pass.
- **The verdict needs two bars.** A change is accepted only when a paired randomization
  test clears `--alpha` *and* the mean per-fixture gain clears `--min-effect` (10 points
  by default). Significance alone is buyable with sample count.
- **Fixtures are split tune/holdout** (deterministically, by id hash). The tune split has
  to show the gain; the holdout only has to not contradict it. Requiring significance
  twice on a small store would reject every real improvement.
- **Too many harness errors means no verdict.** Above 20% crashed samples the run isn't a
  measurement, and it says so instead of printing a number.
- **Replay never touches the harvested repo.** Each sample gets a `git worktree` at the
  fixture's commit and every path in the context is rebased into it.

## Limits worth knowing before you trust a result

- **Graders check well-formedness, not quality.** A prompt can be tuned to satisfy
  `section_gaps` while writing worse stories. That is what the greenfield round's judged
  backlog satisfaction is for — iterate here, gate there.
- **Only a node's last visit is harvestable.** `context_after.json` is overwritten per
  visit, so a node that looped eleven times yields one fixture. Breadth comes from more
  runs, not deeper mining of one.
- **Fixtures carry real run content**, so the store (`.fixtures/`) is gitignored and
  `$STABLEMATE_EVAL_FIXTURES` moves it off the tree entirely when harvesting from a
  private repo. This directory ships publicly — see the root `CLAUDE.md`.

## Adding a node

Declare it in `evals/<workflow>.yml` with the downstream script node that grades it. A
node qualifies when its input is recoverable from artifacts, its output is graded by a
deterministic node *in the same graph*, and failing that gate is a real defect. If a node
has no deterministic gate, add one to the workflow first — that fix is stronger than
anything the eval would have measured.
