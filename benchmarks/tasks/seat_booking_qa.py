"""seat-booking — the same question as policy-desk, asked of the small app.

One Python service with one screen, nine seeded defects. It is the cheaper half of the
detection measurement and the one that isolates the lane from the stack: where policy-desk
answers "does QA notice a defect that spans two services and a client-owned route",
seat-booking answers "does it notice one at all", on a fixture a trial can bring up in
seconds.

Everything about the round — materialize the story so its diff is uncommitted, seed one
variant, drive `workhorse-coder run qa`, keep a witness, classify against the answer key —
is `_frozenapp.py`'s and is shared verbatim with policy-desk. This module is the
declaration and the two paths that make it seat-booking.
"""

from __future__ import annotations

import _frozenapp as pd
from paddock import Run, Score, step, task

task(
    name="seat-booking-qa",
    seed="seat-booking",
    config="benchmarks/configs/opencode.toml",
)

FIXTURE = pd.Fixture(app="apps/seat-booking", repo_dir="seat-booking")


@step()
def pin_config(run: Run) -> None:
    pd.pin_config(run)


@step()
def trials(run: Run) -> None:
    pd.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return pd.score_round(run, FIXTURE)
