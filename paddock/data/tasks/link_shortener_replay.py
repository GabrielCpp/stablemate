"""link-shortener-replay — what does the docs lane cost on the smallest real story?"""

from __future__ import annotations

import _replay as replay
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="link-shortener-replay",
    seed="link-shortener-built",
    config="configs/opencode.toml",
)

HARNESS_REF = "7019808"

FIXTURE = replay.Fixture(
    app="link-shortener",
    pins=(
        replay.Pin(story="create-short-links", commits={"docs": "2728faf"}),
        replay.Pin(
            story="redirect-short-links",
            commits={"docs": HARNESS_REF},
            book_from=HARNESS_REF,
        ),
    ),
    flows=("docs",),
    harness=("agents.yml", "Makefile", ".gitignore", ".githooks", ".agents"),
    harness_ref=HARNESS_REF,
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    replay.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return replay.score_round(run)
