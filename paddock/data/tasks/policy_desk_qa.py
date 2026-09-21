"""policy-desk — does the QA lane notice a seeded defect, and did it work the product?"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="policy-desk-qa",
    seed="policy-desk",
    config="configs/opencode.toml",
)

FIXTURE = pd.Fixture(app="apps/policy-desk", repo_dir="policy-desk")


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    pd.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return pd.score_round(run, FIXTURE)
