"""link-shortener, book rebuild — the OKF-building question, asked of MiniMax.

`link_shortener_book` runs this exact round on the subscription models. This module
changes the config and nothing else: the seed, the strip, the build and the deterministic
rulers in `_okfbuild` — doctor, fmt, the builder's own `coverage.json` claim, and the
loaded graph's node and obligation counts — are shared verbatim.

It is the other half of the non-frontier question. `seat_booking_qa_minimax_direct` asks
whether a cheaper model can *detect*; this asks whether it can *author* — and the two
lanes fail differently, so a model that scores on one says nothing about the other. The
ruler here is deterministic rather than a judgement, which is what makes a cross-model
comparison mean something: `doctor 0e/5w` is the same claim whoever wrote the book.

**Read the frontier baseline before reading this arm's number.** All three
`link-shortener-book` labels exited rc 1 at the wall clock with a partial book (best:
doctor 0e/5w, 329 obligations, 71m at `budget=9000`), so the subscription arm has never
run this task to completion either. Both arms are therefore "book quality at a budget",
and the budget has to be stated with the score or the two are not comparable. Give this
arm the `timeout_scale` its config carries — a model three times slower needs three times
the wall clock to reach the same node, and a smaller budget measures the clock rather
than the model.
"""

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
