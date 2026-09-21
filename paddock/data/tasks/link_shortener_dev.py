"""link-shortener-dev — what does the dev lane cost, against one agent given one goal?"""

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

HARNESS_REF = "7019808"

FIXTURE = replay.Fixture(
    app="link-shortener",
    pins=(replay.Pin(story="create-short-links", commits={"dev": "7e12d48"}),),
    flows=("dev",),
    harness=("agents.yml", "Makefile", ".gitignore", ".githooks", ".agents"),
    harness_ref=HARNESS_REF,
    extra_witness=("api",),
)


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    replay.run_round(run, FIXTURE)


def score(run: Run) -> Score:
    """The replay's cost, and beside it the same gate the solo baseline was graded on."""
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
