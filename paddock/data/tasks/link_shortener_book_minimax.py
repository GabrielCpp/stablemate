"""link-shortener, book rebuild — the OKF-building question, asked of MiniMax."""

from __future__ import annotations

import _okfbuild as ob
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="link-shortener-book-minimax",
    seed="link-shortener-built",
    config="configs/minimax-direct.toml",
)

FIXTURE = ob.Fixture(
    service="api",
    source_path="api",
    repo_dir="link-shortener",
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def strip_book(run: Run) -> None:
    ob.strip_book(run, FIXTURE)


@step()
def build(run: Run) -> None:
    ob.run_build(run, FIXTURE)


def score(run: Run) -> Score:
    return ob.score_round(run, FIXTURE)
