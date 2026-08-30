"""seat-booking, audit-on — the round that gives D9's question a configuration that asks it.

`seat-booking-qa` runs every trial to its first verdict, and D9 — the seat map pushed to
24% width at 62% from the left, outside the declared `placement: width 40-100%, x 0-30%` —
is filed `caught_by: audit` precisely because that configuration cannot see it: every seat
is still present, visible and operable, so no assertion over the running screen goes red
and the row scores `inconclusive — no audit turn in this configuration`. This task is the
other configuration. `first_verdict=False` lets the lane run past the verdict into the
auditor's turn, and the auditor reading the layout digest against the placement clause is
the only route by which D9 becomes a catch or a miss.

The round is scoped to D9 (`defects=("D9",)`): re-buying D1–D8 here would spend eight
QA-route trials re-measuring what `seat-booking-qa` already scores, on a budget this task
raised to pay for audit turns. `--param defects=…` still widens or narrows it. Everything
else — seed, config, materialization, ruler — is `seat-booking-qa`'s, and the two labels
are comparable row-for-row on the one defect they share.
"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="seat-booking-audit",
    seed="seat-booking",
    config="configs/opencode.toml",
)

#: The same one-service fixture `seat_booking_qa` declares, run audit-on and scoped to the
#: one row only an audit turn can score. The budget is higher than the QA task's because
#: the lane no longer stops at the first verdict — the auditor's turn is paid for.
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
