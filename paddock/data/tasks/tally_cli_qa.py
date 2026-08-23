"""tally-cli — does QA separate obligations that share a file?

`claims-api` removed the screen and `depot-infra` removed the process; this fixture removes
the *distance* between the stories. A stdlib-only Python package with no server, no port and
no toolchain, whose three stories all touch `tally/cli.py` and two of them `tally/ledger.py` —
so file-level ownership says nothing at all. What separates them is which functions they
changed, and the packet minted from each materialized trial is what has to say so.

That is the measurement. Every defect here is seeded into a file some *other* story also
edits, so a lane that reasons about changed files rather than changed symbols is handed a
QA scope three times too wide and no way to tell which part of it it is answering for.

The second thing the fixture freezes is the shape of a QA lane with no service in it. There
is nothing to start and nothing to reach over a socket — but a plan may not import the
package either, because `ostler.qa.lint` is an AST allowlist that reserves the process for
approved tools. So the product is reached the way every other product is, over a process
boundary: `python3 -m tally`, through the `python3` tool `agents.yml` opts into and the
`[qa_tools.python3]` table in `configs/opencode.toml` resolves. The target's `driver` names
the harness the scenario body runs in, not the transport, and there is no driver for "a
command".

Every one of the seven defects is `caught_by: run`. Two audit-only rows already exist across
this trio — claims-api's C9 and depot-infra's D7 — and a third would buy no coverage of the
scorer that those two do not already buy.

The round, the materialization and the ruler are all in `_frozenapp.py`, which names no app;
this module is the declaration and the two paths that make it tally-cli.
"""

from __future__ import annotations

import _frozenapp as pd
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="tally-cli-qa",
    seed="tally-cli",
    config="configs/opencode.toml",
)

#: A stdlib-only Python CLI. No dependency to install, no port to bind and no state outside
#: the one JSON file the product writes, so a trial runs on a clean, offline machine.
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
    pd.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return pd.score_round(run, FIXTURE)
