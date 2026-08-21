"""claims-api — what does the QA lane have left to hold on to when there is no screen?

The same round `policy-desk` runs, over a fixture built to remove one thing: the product
has no GUI at all. Its book is `http/` and nothing else, so the leverage keys that count
entry points and deep links have nothing to read, and every obligation has to be reached
through the contract. That pair of numbers — a detection rate beside a scorecard with two
blank columns — is the measurement this app exists to take.

The other half is what a contract-first service can get wrong that a hand-rolled one
cannot pose. Protection is not wired per route here: `oapi-codegen`'s chi wrapper stamps
`gen.BearerAuthScopes` into the request context for exactly the operations `openapi.yml`
secures, and the middleware serves whatever it does not find there. C1 and C2 make that
false while leaving every happy path green.

The round, the materialization and the ruler are all in `_frozenapp.py`, which names no
app; this module is the declaration and the two paths that make it claims-api.
"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="claims-api-qa",
    seed="claims-api",
    config="configs/opencode.toml",
)

#: A Go JSON API generated from an OpenAPI contract, with bearer identity minted by a
#: Firebase Auth emulator beside it — so a trial reaches an authenticated obligation with
#: no credential anywhere in the tree, and the round stays runnable on a clean machine.
FIXTURE = pd.Fixture(app="apps/claims-api", repo_dir="claims-api")


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    pd.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return pd.score_round(run, FIXTURE)
