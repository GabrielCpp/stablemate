"""link-shortener-dev — what does the dev lane cost, against one agent given one goal?

The other replay on this app asks what the docs lane costs. This one asks the question
that decides whether the workflow is worth running at all: **hand the dev lane the same
work a single agent was handed, on the same model, and compare.**

The baseline it is measured against is not another workflow. It is `claude -p --model
claude-opus-5` invoked once in an empty directory, with the backlog and the seven decision
records concatenated onto its stdin and nothing else — no plan node, no review cycle, no
book. Three trials of that finished in 140s, 161s and 174s, emitting a mean of 12,776
output tokens, and each of the three passed a twelve-point black-box acceptance gate. That
is the number on the other side of this fixture.

Only `create-short-links` is pinned, and the reason is the whole design of the fixture.
`a57f280` — the commit that lands story 1's implementation — already contains the redirect
handler and its 302, so the dev lane for `redirect-short-links` was entered on a tree that
already implemented its story: it added a logger and refactored a repository. Replaying it
would measure a lane confirming its own work, which `_replay.rewind` exists to prevent, and
a second row that measures nothing is worse than one row that measures something.

What survives is the better row anyway. Story 1's dev lane was entered at `3322bb3`, a tree
with `docs/` and no `api/` at all, and it left behind the entire service — both endpoints,
the validation rules, the durable ledger. Its input is the story rather than a goal file
and its deliverable carries a plan and a review record the baseline never writes, but the
*product* is the same product, graded by the same gate. The comparison is honest in the one
direction that matters: both sides start from nothing and are asked for the whole app.

The models are flattened to a single rung on purpose — see `configs/claude-opus.toml`.
"""

from __future__ import annotations

import _linkshort as linkshort
import _replay as replay
import _stablemate as sm
from paddock import Run, Score, step, task

task(
    name="link-shortener-dev",
    seed="link-shortener-built",
    config="configs/claude-opus.toml",
)

#: The commit that tracks the repo's own harness — see the docs replay for why restoring
#: it is not input to the lane. Shared verbatim with `link_shortener_replay`, because it is
#: a fact about the bundle rather than about either fixture.
HARNESS_REF = "7019808"

#: One story, and the commit its dev lane's output begins at.
#:
#: `7e12d48` and not `a57f280`: the lane's first commit for this story is the one that
#: records the implementation review, and the code lands in the commit after it. Pinning
#: the later one would rewind to a tree that already held the lane's review.
#:
#: The default entry ref — that commit's parent, `3322bb3` — is exactly right here: it is
#: the last commit the *author* workflow made, so the tree holds the epic, both stories and
#: the journeys index, and holds no source.
FIXTURE = replay.Fixture(
    app="link-shortener",
    pins=(replay.Pin(story="create-short-links", commits={"dev": "7e12d48"}),),
    flows=("dev",),
    harness=("agents.yml", "Makefile", ".gitignore", ".githooks", ".agents"),
    harness_ref=HARNESS_REF,
    # The whole product, so the acceptance gate can rebuild and interrogate it from the
    # sealed result — a wall-clock number with no quality bar under it is half a comparison.
    extra_witness=("api",),
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    replay.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    """The replay's cost, and beside it the same gate the solo baseline was graded on.

    The gate runs over each trial's sealed witness (which carries `api/`, see the
    fixture), builds in `scratch/` and logs into `run.artifacts` — the two places a score
    is allowed to write — so a sealed result stays re-gradable without re-running a trial.
    """
    base = replay.score_round(run)
    trials = list((base.data or {}).get("trials", []))
    gates = []
    for trial in trials:
        run_id = str(trial["run_id"])
        outcome = linkshort.probe(
            run.stage / str(trial["witness"]),
            run.workdir(f"gate-{run_id}"),
            run.artifacts / run_id,
        )
        gates.append({"run_id": run_id, **outcome})

    if not gates:
        return base
    line = "  ".join(linkshort.gate_line(gate) for gate in gates)
    detail = [*base.detail, ""]
    for gate in gates:
        detail.extend(linkshort.gate_detail(str(gate["run_id"]), gate))
    return Score(
        headline=f"{base.headline} | {line}",
        detail=tuple(detail),
        data={**(base.data or {}), "gates": gates},
    )
