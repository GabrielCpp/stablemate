"""depot-infra — what does the QA lane have left to hold on to when nothing runs?

`claims-api` removed the screen; this fixture removes the process. A Pulumi program in Go
declares an artifact depot and serves nothing at all: there is no port to reach, no
request to make, and no state to restart. Its whole observable behaviour is the plan
`pulumi preview` writes, so the QA lane's only evidence is a JSON document — read with
`jq`, taken by the `make -C pulumi plan` target the app's own ops page publishes.

That is the measurement. Every obligation here is a policy claim about a declaration, and
a plan is a document that is *correct in all the wrong ways* when a defect lands in it: a
widened IAM binding, a project-level grant, a second scheduler job and a token in the
clear all produce a plan that previews cleanly and reports no error. Only an assertion
that reads the whole plan — the member list compared as a list, every IAM step enumerated,
the jobs counted — separates them from the right one, and whether the lane writes that
kind of assertion is what the seven defects ask.

D7 is deliberately not one of them. A missing provider pin is invisible in the plan JSON
on a machine that already holds the plugin, so it is filed `caught_by: audit` — the row
that says what this evidence surface cannot see.

The round, the materialization and the ruler are all in `_frozenapp.py`, which names no
app; this module is the declaration and the two paths that make it depot-infra.
"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="depot-infra-qa",
    seed="depot-infra",
    config="configs/opencode.toml",
)

#: A Pulumi/Go infrastructure program planned against the pinned GCP provider plugin. No
#: port, no stack state and no credential: a preview resolves against the plugin rather
#: than the cloud, so the round stays runnable on a clean, offline machine.
FIXTURE = pd.Fixture(
    app="apps/depot-infra",
    repo_dir="depot-infra",
    # No screen and no process: the plan document is the only thing a scenario reads.
    leverage=("obligations", "journeys", "sensitivity"),
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    pd.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return pd.score_round(run, FIXTURE)
