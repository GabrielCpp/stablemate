"""seat-booking — the detection question, asked of MiniMax over minimax.io's own API.

Third arm of one comparison. `seat_booking_qa` runs this exact round on the subscription
models and `seat_booking_qa_minimax` runs it on MiniMax reached over a metered OpenRouter
key; this module changes the config and nothing else, so the fixture, the nine seeded
defects, the answer key, the materialization and the ruler are `_frozenapp.py`'s and are
shared verbatim.

**Why a third module and not a param on the second.** The OpenRouter arm and this one
reach the same weights over different transports, and the transport is a confound a
comparison has to hold still: OpenRouter fans a slug out over competing upstream
endpoints that differ in quantization, context window and tool support, while minimax.io
serves one. They also do not share a credential — one spends metered credit and the
other prepaid plan quota — so driving both in one round makes the cheap arm's failure
mode (a 402) indistinguishable from this one's (a quota wall). `config` is a property of
the task rather than of a round, and a scorecard has to name the file it was produced
under.

**Run this one with controls.** The OpenRouter rounds bought their defect trials with
`no_control=1` because the budget that stopped them was an account balance. A token plan
removes that constraint, and the control trials are the measurement those rounds are
missing: `plan-qa.md` now instructs the planner to arrange state adversarially, which is
exactly the change that could start manufacturing refutations of behaviour the book never
promised. A caught-defect count with no false-positive count beside it does not answer
whether the model is usable.
"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="seat-booking-qa-minimax-direct",
    seed="seat-booking",
    config="configs/minimax-direct.toml",
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
