"""globex — the tree's only two-service fixture: a web app and an API, together.

`policy-desk` is the closer precedent, not `claims-api`: both pair a GUI surface with a
service behind it, so the round has a screen to enter through and a deep link to survive a
page load, which is exactly what `claims-api`'s fixture is built to remove. globex adds a
third surface on top of that pair — `mobile-app` — that a compose-driven round does not
reach; `web-app` and `api-service` are the two services `compose.yml` actually brings up,
and `mobile-app` calls the same API origin from a device rather than a container.

This module only registers the app: it declares the task the same way every other frozen-
app fixture does, so `paddock list` and the corpus gate in `test_app_books.py` can see it.
Its `seed=` resolves — `configs/seeds/globex.toml` was captured for it, and
`test_seed_freshness.py` gates that both ways — but it does not yet carry an answer key:
no `stories/`, no `defects.yml`, no `docs/specs/`. So `trials` unpacks the seed and then
has nothing to grade, and `score` has no key to read; authoring that corpus is separate,
larger work. Capture also warns that this tree has no `agents.yml`, which the five scored
fixtures do — that belongs with the corpus, not here. Until then this declaration is what
stops the book from being reachable by nothing outside its own directory, which is the
defect this module exists to close.

The round, the materialization and the ruler are all in `_frozenapp.py`, which names no
app; this module is the declaration and the two paths that make it globex.
"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="globex-qa",
    seed="globex",
    config="configs/opencode.toml",
)

#: A Go web app and a Go API together, with a screen to enter through and a deep link that
#: has to survive a page load — the leverage questions `claims-api`'s headless fixture has
#: nothing to ask.
FIXTURE = pd.Fixture(app="apps/globex", repo_dir="globex")


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    pd.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return pd.score_round(run, FIXTURE)
