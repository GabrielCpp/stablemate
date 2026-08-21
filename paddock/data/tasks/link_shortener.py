"""link-shortener — the smoke task: one Go surface, three bullets, half an hour.

Sized to be re-run after every workflow fix, and that is a design constraint rather than a
convenience: a benchmark you can only afford once a day gets consulted once a day, and a
fix cycle that slow stops being a cycle. Small enough that a failure has one plausible
cause — one stack, a handful of stories, no cross-surface anything.

It is **not** a quality measure. Three bullets cannot rank a workflow; they can only say
whether it still gets from a backlog to committed code without help. Read the rubric score
as pass/fail and the reliability half — repair loops, operator-gate escalations, per-node
active time — as the actual output.

The round itself is `_greenfield.py`'s and is shared with every other backlog-driven task.
This module is the declaration: which backlog, which surface, which gates, which judge.
"""

from __future__ import annotations

import _greenfield as gf
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="link-shortener",
    seed="link-shortener",
    config="configs/opencode.toml",
)

FIXTURE = gf.Fixture(
    backlog="suites/link-shortener/docs/backlog.md",
    # The author lane blocks for a human on product decisions the backlog leaves open,
    # by design and with no resolver. That turn was held once, against these bullets, and
    # frozen — so a round resumes from the far side of it rather than needing an operator.
    decision_records="suites/link-shortener/docs/decisions",
    grill_capture="suites/link-shortener/grill",
    packs="product-planning,stablemate,infra",
    docs_scaffold="shared-docs:docs",
    surfaces=(
        gf.Surface(
            service="api",
            service_root="api",
            packs="go",
            scaffolds="go-service:api",
            init_cmd="go mod init example.com/link-shortener/api",
            marker="go.mod",
            markers="go.mod,main.go",
        ),
    ),
    # Not `make lint` / `make test`: nothing scaffolds a Makefile, so those would report a
    # missing target as a red gate on every single run and train you to skip the row.
    checks=(
        gf.Check(name="build", cmd="cd api && go build ./...", timeout_s=300.0),
        gf.Check(name="test", cmd="cd api && go test ./...", timeout_s=600.0),
    ),
    # The same backend the round runs on, but *named here* rather than inherited from the
    # environment. Sameness is not the property that matters — pinning is: an unpinned
    # judge switches with whatever `$AGENT_CLI` holds, and two rounds graded by two
    # graders differ by an unknown amount of grader.
    judge_cli="opencode",
    judge_model="openai/gpt-5.6-sol",
    judge_effort="medium",
    # One hour per phase, except coder. Checked between states, so an over-budget phase
    # stops on a node boundary with its checkpoint intact — score it, then resume.
    #
    # The figures are deliberately loose. An earlier 600/600/1200 was measured against one
    # backend and was a fact about that backend, not about the task: the first other set to
    # run this spec spent 657s inside a single `decompose-epics` turn and met the 600s
    # author ceiling before the stage finished, so its score read the ceiling rather than
    # the work. `coder` gets far more because it is the only phase whose cost scales with
    # the backlog — it runs plan→implement→document→QA once per story, where genesis and
    # author each run once per task.
    budget_s={"genesis": 3600.0, "author": 3600.0, "coder": 11000.0},
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def build(run: Run) -> None:
    gf.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    return gf.score_round(run, FIXTURE)
