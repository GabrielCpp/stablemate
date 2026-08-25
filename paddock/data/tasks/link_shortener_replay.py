"""link-shortener-replay — what does the docs lane cost on the smallest real story?

The expense-split replay asks whether a review loop converges over five stories of a real
app. This one asks a narrower and more impatient question: on a two-story Go service that a
person would call trivial, how long does documenting one story take, and does a change to
the docs prompts move that number? Small is the point — a lane whose cost is dominated by
its own ceremony shows it most clearly on the story with the least to say, and this is the
fixture where a 20-minute lane cannot be excused by the size of the work.

Only `docs` is pinned. The two stories' QA ran under a since-changed contract, so their
commits are not an honest QA entry state; the book, by contrast, is exactly what the docs
lane was handed. A fixture that pins a flow it cannot faithfully rewind measures the rewind.

The mechanism is `_replay.py`'s in full: clone at the pin, restore the book to the state
the lane was entered with, run `workhorse-coder run docs` cold, with no session to resume.
"""

from __future__ import annotations

import _replay as replay
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="link-shortener-replay",
    seed="link-shortener-built",
    config="configs/opencode.toml",
)

#: The commit that tracks the repo's own harness. The bench repo grew `agents.yml`, its
#: Makefile, its ignore rules and its git hooks as untracked files, so every commit before
#: this one clones into a tree farrier cannot install into and no prompt path resolves in.
#: Restoring them is not input to the lane — `agents.yml` names the packs and the
#: workspace, never the work — which is why it is a harness restore and not a new pin.
HARNESS_REF = "7019808"

#: Two stories, and the state each one's docs lane was entered in.
#:
#: `create-short-links` had its book entry landed by a real run at `2728faf`, so the
#: default rewind — that commit's parent — is right: the book holds everything up to but
#: not including this story.
#:
#: `redirect-short-links` is the more useful row, and the reason `book_from` exists. Its
#: docs lane **never ran**: there is no commit to be the parent of, and its entry state is
#: the tip exactly as it stands — story 1 documented and repaired, story 2 absent. Naming
#: that tree is what makes an undocumented story replayable at all.
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
