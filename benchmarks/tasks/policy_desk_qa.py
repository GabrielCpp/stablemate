"""policy-desk — does the QA lane notice a seeded defect, and did it work the product?

One task, one round: a clean control per story plus one trial per row of the answer key,
each a fresh materialization of the frozen app with exactly one thing wrong in it. The
fan-out lives in a step rather than in a task per defect — twelve near-identical task
modules would be twelve places to fix a change to the round, and the score is a statement
about the round rather than about any single trial.

What travels out of a run is deliberately small: the trees themselves are per-trial and
stay in `scratch/`, and each trial copies into the result only the evidence its score is
read from — the book, the spec, the plan, the run ledger and the one file the defect was
seeded into. That is what keeps `score` read-only over the stage and a sealed result
re-scorable on a machine that never ran it.

The round, the materialization and the ruler are all in `_frozenapp.py`, which names no
app; this module is the declaration and the two paths that make it policy-desk.
"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="policy-desk-qa",
    seed="policy-desk",
    config="benchmarks/configs/opencode.toml",
)

#: A Go API behind a React SPA — the shape the interesting leverage questions only arise
#: in: a deep link that has to survive a page load, an obligation that spans two services.
FIXTURE = pd.Fixture(app="apps/policy-desk", repo_dir="policy-desk")


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    pd.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return pd.score_round(run, FIXTURE)
