"""depot-infra, audit-on — the round that gives D7's question a configuration that asks it.

`depot-infra-qa` runs every trial to its first verdict, and D7 — the deleted provider pin —
is filed `caught_by: audit` precisely because that configuration cannot see it: the plan
JSON reports the version the preview *resolved*, not the version the program asked for, so
no assertion over the plan goes red and the row scores `inconclusive — no audit turn in
this configuration`. This task is the other configuration. `first_verdict=False` lets the
lane run past the verdict into the auditor's turn, and the auditor reading the evidence
against the clause — the pin the ops page says the program holds, absent from `main.go` —
is the only route by which D7 becomes a catch or a miss.

The round is scoped to D7 (`defects=("D7",)`): re-buying D1–D6 here would spend six
QA-route trials re-measuring what `depot-infra-qa` already scores, on a budget this task
raised to pay for audit turns. `--param defects=…` still widens or narrows it. Everything
else — seed, config, materialization, ruler — is `depot-infra-qa`'s, and the two labels
are comparable row-for-row on the one defect they share.
"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="depot-infra-audit",
    seed="depot-infra",
    config="configs/opencode.toml",
)

#: The same offline Pulumi/Go fixture `depot_infra_qa` declares, run audit-on and scoped
#: to the one row only an audit turn can score. The budget is higher than the QA task's
#: because the lane no longer stops at the first verdict — the auditor's turn is paid for.
FIXTURE = pd.Fixture(
    app="apps/depot-infra",
    repo_dir="depot-infra",
    # No screen and no process: the plan document is the only thing a scenario reads.
    leverage=("obligations", "journeys", "sensitivity"),
    first_verdict=False,
    defects=("D7",),
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
