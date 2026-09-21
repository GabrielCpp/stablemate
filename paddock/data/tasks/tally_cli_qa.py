"""tally-cli — does QA separate obligations that share a file?"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="tally-cli-qa",
    seed="tally-cli",
    config="configs/opencode.toml",
)

FIXTURE = pd.Fixture(
    app="apps/tally-cli",
    repo_dir="tally-cli",
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
