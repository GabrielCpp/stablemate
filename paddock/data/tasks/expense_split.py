"""expense-split — does a review loop converge, on a fixture that has no answer key.

The other frozen-app tasks ask a detection question: seed a defect, see whether QA notices.
This one asks the question underneath it — **how much does the machinery talk to itself
before it will let a story go** — and it asks it of a real five-story application built by
the coder workflow rather than of a hand-frozen fixture.

That question needs no answer key, which is why this task has one and the round is scored
on convergence alone: laps per node, operator-gate escalations, cost and wall clock. There
is nothing here to be right or wrong about, so nothing here can be gamed in the direction
detection can: a lane that refutes everything catches every defect and never terminates,
and this is the number that says so.

The seed is the finished app with its whole history, so a trial does not materialize a
tree — it checks one out. Each story was landed by a real run, and the commit that landed
it is the exact state the flow was entered in; `FIXTURE`'s pins are that correspondence,
and they are tracked data rather than a fixture file because they are five rows that change
only when the bundle is recaptured.

The mechanism — clone at the pin, undo what the flow wrote, run the flow cold with no
session to resume — is `_replay.py`'s and is shared with every other replay fixture. What
lives here is only what is true of *this* app: which stories, at which commits, and the two
capture-time gaps (`backfill_dependencies`, `packs`) the bundle predates.
"""

from __future__ import annotations

import _replay as replay
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="expense-split",
    seed="expense-split",
    config="configs/opencode.toml",
)

#: The five stories, in the order they were built, and the commit that landed each flow.
#: Reachable in the seed's own `.git` — `paddock seed capture` zipped the repository,
#: history included, which is what makes a per-story pin a checkout rather than a second
#: fixture.
#:
#: Both flows by default: the fixture's whole point is that it carries a QA loop *and* a
#: documentation loop, and a change that quiets one by pushing the work into the other has
#: not quieted anything.
FIXTURE = replay.Fixture(
    app="expense-split",
    pins=(
        replay.Pin(story="create-group", commits={"qa": "b3b0e0c", "docs": "e1b9785"}),
        replay.Pin(story="group-membership", commits={"qa": "a4b70c2", "docs": "a4b70c2"}),
        replay.Pin(story="expense-record", commits={"qa": "b0464ec", "docs": "b8b3ffc"}),
        replay.Pin(story="expense-list", commits={"qa": "c0478a9", "docs": "c0478a9"}),
        replay.Pin(story="balance-settlement", commits={"qa": "99fff2b", "docs": "321d39a"}),
    ),
    # The bundle was captured before `registry.STORY_SECTIONS` gained a leading
    # `## Dependencies`, and before the docs prompts came to depend on the `stablemate`
    # pack — this app subscribes to `product-planning` and `go` only. Patching both at
    # checkout is what keeps a schema addition from being a reason to recapture: a
    # recapture moves all ten pins and throws away the one thing this fixture *is*.
    backfill_dependencies=True,
    packs=("stablemate",),
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    replay.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return replay.score_round(run)
