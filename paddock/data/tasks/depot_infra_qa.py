"""depot-infra — what does the QA lane have left to hold on to when nothing runs?"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="depot-infra-qa",
    seed="depot-infra",
    config="configs/opencode.toml",
)

FIXTURE = pd.Fixture(
    app="apps/depot-infra",
    repo_dir="depot-infra",
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
