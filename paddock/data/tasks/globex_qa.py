"""globex — the tree's only two-service fixture: a web app and an API, together."""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="globex-qa",
    seed="globex",
    config="configs/opencode.toml",
)

FIXTURE = pd.Fixture(app="apps/globex", repo_dir="globex")


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    pd.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return pd.score_round(run, FIXTURE)
