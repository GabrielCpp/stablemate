"""claims-api — what does the QA lane have left to hold on to when there is no screen?"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="claims-api-qa",
    seed="claims-api",
    config="configs/opencode.toml",
)

FIXTURE = pd.Fixture(
    app="apps/claims-api",
    repo_dir="claims-api",
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
