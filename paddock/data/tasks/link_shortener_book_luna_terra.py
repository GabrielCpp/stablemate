"""Compare Luna and Terra rebuilding the same link-shortener OKF book.

Both arms start from independent clones of one committed stripped baseline. The score
keeps deterministic book quality separate from retries, tokens, elapsed time, and
rate-card cost so a cheaper incomplete build cannot be mistaken for a better one.
"""

from __future__ import annotations

import _okfbuild as ob
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="link-shortener-book-luna-terra",
    seed="link-shortener-built",
    config="configs/okf-builder-luna-terra.toml",
)

FIXTURE = ob.Fixture(
    service="api",
    source_path="api",
    repo_dir="link-shortener",
)
PROFILES = ("luna", "terra")


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def strip_book(run: Run) -> None:
    ob.strip_book(run, FIXTURE)


@step()
def builds(run: Run) -> None:
    ob.run_paired_build(run, FIXTURE, PROFILES)


def score(run: Run) -> Score:
    return ob.score_paired_round(run, FIXTURE, PROFILES)
