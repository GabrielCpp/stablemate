"""link-shortener, book rebuild — strip the finished app's book and grade what okf-builder writes.

The seed is `link-shortener-built`: the two-story link-shortener at the end of its review
lane, book and all. The round deletes `docs/features/api/` (committed, so the old book is
not one checkout away), points `workhorse-okf-builder` at the stripped tree, and scores
the rebuild with the deterministic rulers in `_okfbuild` — doctor, fmt, the builder's own
`coverage.json` claim, and the loaded graph's node/obligation counts. The built book at
capture time scored doctor `0e/0w`, which is the bar a rebuild is read against.

What this round's product must never become is a fixture book for the frozen-app family.
apps/README.md ("The book is versioned per story") is explicit about why: a book authored
in one pass against the finished app is **wrong for every image but the last** — it
documents commands, fields and invocations the earlier stories have not written yet, and
a plan authored against it reaches for them. And: "**`okf-builder` builds books from
finished code**, so any fixture derived through it inherits the anachronism by
construction. A generated book is a post-image of the *last* story and has to be trimmed
backwards, per story, by hand." This task measures the builder; it does not mint pins.

One trial per round — a build is its own control. `--param budget` narrows the wall
clock for a smoke round (the builder exits rc 1 at the budget with a resume line, and
the partial book still scores, caveated); `--param judge=true` adds the opt-in prose
judge (`_okfbuild.judge_book` + `rubric-book.md`), which grades a sample of the rebuilt
bullets on whether each earns its citation — a detail line, never the headline.
"""

from __future__ import annotations

import _okfbuild as ob
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="link-shortener-book",
    seed="link-shortener-built",
    config="configs/opencode.toml",
)

#: Confirmed against the unpacked seed (Op 0): `agents.yml` declares a mono workspace
#: with `service_roots: [api]`, the book lives at `docs/features/api/`, and the source
#: root is the `api/` Go module. Discovery routes the app as `driver: http` — no UI, so
#: no walkthrough tail to gate on. The rest of `docs/` (epics, specs, journeys index)
#: survives the strip with nothing dangling.
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
