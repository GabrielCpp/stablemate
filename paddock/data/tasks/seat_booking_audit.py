"""seat-booking, audit-on — the round that gives D9's question a configuration that asks it."""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="seat-booking-audit",
    seed="seat-booking",
    config="configs/opencode.toml",
)

FIXTURE = pd.Fixture(
    app="apps/seat-booking",
    repo_dir="seat-booking",
    first_verdict=False,
    defects=("D9",),
    budget_s=3600.0,
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    pd.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return pd.score_round(run, FIXTURE)
