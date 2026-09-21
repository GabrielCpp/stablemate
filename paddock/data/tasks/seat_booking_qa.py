"""seat-booking — the same question as policy-desk, asked of the small app."""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="seat-booking-qa",
    seed="seat-booking",
    config="configs/opencode.toml",
)

FIXTURE = pd.Fixture(app="apps/seat-booking", repo_dir="seat-booking")


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    pd.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return pd.score_round(run, FIXTURE)
