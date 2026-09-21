"""expense-split — does a review loop converge, on a fixture that has no answer key."""

from __future__ import annotations

import _replay as replay
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="expense-split",
    seed="expense-split",
    config="configs/opencode.toml",
)

FIXTURE = replay.Fixture(
    app="expense-split",
    pins=(
        replay.Pin(story="create-group", commits={"qa": "b3b0e0c", "docs": "e1b9785"}),
        replay.Pin(story="group-membership", commits={"qa": "a4b70c2", "docs": "a4b70c2"}),
        replay.Pin(story="expense-record", commits={"qa": "b0464ec", "docs": "b8b3ffc"}),
        replay.Pin(story="expense-list", commits={"qa": "c0478a9", "docs": "c0478a9"}),
        replay.Pin(story="balance-settlement", commits={"qa": "99fff2b", "docs": "321d39a"}),
    ),
    backfill_dependencies=True,
    packs=("stablemate",),
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    replay.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return replay.score_round(run)
