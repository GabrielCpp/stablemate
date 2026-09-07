"""seat-booking — the detection question, asked of MiniMax over a metered OpenRouter key.

`seat_booking_qa` runs this exact round on the subscription models. This module changes
one thing and declares it: the config, and so the models. Everything else — the fixture,
the nine seeded defects, the answer key, the materialization and the ruler — is
`_frozenapp.py`'s and is shared verbatim, because a comparison whose two arms differ in
more than the model measures the difference nobody asked about.

It is a second module rather than a `--param` on the first because `config` is a property
of the task, not of a round: `paddock run` has no config override, and a scorecard has to
name the file it was produced under. It is a second module rather than a second profile in
one config — the `okf-builder-luna-terra` shape — because the two arms here do not share a
credential. One arm spends plan quota and the other spends credit on an OpenRouter
account, so they cannot be driven in the same round without the cheap arm's failure mode
(a 402) looking like the expensive arm's (a quota wall).

**This round costs real money.** Run it narrowed — `--param defects=…`, `--param
no_control=1` — until the per-trial cost is known, because the budget that stops it is an
account balance rather than a clock.
"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="seat-booking-qa-minimax",
    seed="seat-booking",
    config="configs/openrouter-minimax.toml",
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
