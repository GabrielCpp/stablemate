"""tally-cli mutants — is the book what kills a defect, or would anything have?"""

from __future__ import annotations

import _frozenapp as pd
import _mutants as mu
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="tally-cli-mutants",
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
    mu.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return mu.score_round(run, FIXTURE)
