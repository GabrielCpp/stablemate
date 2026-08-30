"""tally-cli mutants — is the book what kills a defect, or would anything have?

The `-qa` task asks whether QA catches the seven answers somebody already wrote down.
This round asks the sharper question underneath it: of two pools of frozen mutants that
both break the product, does the pool that violates a *written normative bullet* die
measurably more often than the pool curated with the book closed? That difference — the
pin-rate gap — is the number that says the book is load-bearing, rather than QA being
generically good at noticing broken software.

Pool A violates one owed bullet each (recorded as `bullet:` in the manifest, under the
relaxed rule the corpus header states); pool B was written from the classic defect
families without consulting the book. A pool-B survivor is the fixture working as
designed: it names a behavior the book has not pinned yet, and triage has exactly two
exits — promote a normative bullet, or ground an `unspecified:`. The corpus itself is
frozen; `mutants.yml` at the app root is the manifest, `mutants/<id>/` the variants, and
`mutants/battery.py` the differential battery every kept mutant had to fail against its
story image before it was allowed in.

The round, seeding, classification and the pin-rate arithmetic are all in `_mutants.py`,
which names no app; this module is the declaration that makes it tally-cli.
"""

from __future__ import annotations

import _frozenapp as pd
import _mutants as mu
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="tally-cli-mutants",
    seed="tally-cli",
    config="configs/opencode.toml",
)

#: The same fixture shape as `tally_cli_qa.py` — a stdlib-only CLI reached over a process
#: boundary — with `defects` empty so a round runs the whole corpus unless the operator
#: narrows it with `--param mutants=M1`.
FIXTURE = pd.Fixture(
    app="apps/tally-cli",
    repo_dir="tally-cli",
    # A CLI: reached over a process, never a screen, so the GUI metrics do not apply.
    leverage=("obligations", "journeys", "sensitivity"),
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    mu.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return mu.score_round(run, FIXTURE)
