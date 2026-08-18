"""The repair loops that run their laps as one conversation.

Everything here is about the part of that decision the engine cannot make for a state:
which key a lap runs under, and *when the conversation has to be thrown away* — because
a chain that outlives what it was repairing is worse than no chain at all, and no test
downstream of these states can see the difference.

The states are called directly rather than driven. Both sit deep inside a loop whose
entry costs a real ostler graph, a real stack and a scripted suite run, and none of that
is what is under test — the scripted turn raises the moment it is reached, so what each
assertion reads is the call the state was about to make.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from workhorse_workflows.coder.dev.flow import Dev
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.shared.schemas.dev import DevResult
from workhorse_workflows.coder.shared.schemas.docs import DocsProgress, DocsResult
from workhorse_workflows.coder.shared.schemas.qa import QaFlowResult, QaLoop

STORY = "STORY-1"


class _Reached(Exception):
    """Raised by the scripted turn: the call under test has been observed."""


class _Spy:
    """What a state asked for, without the run that would normally supply it."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self.resets: list[str] = []


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> _Spy:
    """Replace the two engine seams on both flows, plus the helpers that need a run.

    `_dirs` and the argument builders read node outputs, which only exist inside a
    driven run. They are stubbed because they are inputs to the turn, not the subject of
    it; `agent` and `reset_session` are the surface every assertion below reads.
    """
    seen = _Spy()

    def fake_agent(self: Any, prompt: str, **kwargs: Any) -> Any:
        seen.turns.append({"prompt": prompt, **kwargs})
        raise _Reached(prompt)

    def fake_reset(self: Any, key: str) -> None:
        seen.resets.append(key)

    for flow in (Docs, Qa, Dev):
        monkeypatch.setattr(flow, "agent", fake_agent)
        monkeypatch.setattr(flow, "reset_session", fake_reset)
        monkeypatch.setattr(flow, "logger", property(lambda _: logging.getLogger("test")))
        monkeypatch.setattr(flow, "_dirs", lambda _: [])
    monkeypatch.setattr(Docs, "_author_args", lambda *a, **k: {})
    monkeypatch.setattr(Qa, "_plan_args", lambda *a, **k: {})
    return seen


def _docs() -> Docs:
    flow = Docs(story=STORY)
    flow._ctx = SimpleNamespace(story_slug=STORY, story_path="", spec_dir="", qa_dir="")
    return flow


def _qa() -> Qa:
    flow = Qa(story=STORY)
    flow._ctx = SimpleNamespace(story_slug=STORY, story_path="", spec_dir="", qa_dir="")
    return flow


def _dev() -> Dev:
    flow = Dev(story=STORY)
    flow._ctx = SimpleNamespace(story_slug=STORY, story_path="", spec_dir="", qa_dir="")
    return flow


def _repair(flow: Docs, progress: DocsProgress) -> None:
    with pytest.raises(_Reached):
        flow.repair(progress=progress)


def _repair_plan(flow: Qa, loop: QaLoop) -> None:
    with pytest.raises(_Reached):
        flow.repair_plan(loop)


# ── the docs lane ────────────────────────────────────────────────────────────────────


def test_a_docs_repair_lap_continues_the_story_s_own_conversation(spy: _Spy) -> None:
    """Keyed per story: the point of the chain is that lap N+1 already knows what lap N
    was editing, and two stories in one run are editing different parts of the book."""
    _repair(_docs(), DocsProgress(chain_laps=1))

    assert spy.turns[0]["session"] == f"docs-repair:{STORY}"
    assert spy.resets == []


def test_a_fifth_consecutive_docs_lap_starts_over(spy: _Spy) -> None:
    """A conversation that has been wrong four times running is a transcript of four
    rejected repairs, and compaction summarises those as readily as the useful turns."""
    flow = _docs()
    _repair(flow, DocsProgress(chain_laps=flow.MAX_CHAIN_LAPS))

    assert spy.resets == [f"docs-repair:{STORY}"]
    # Dropped and immediately reopened — the lap still runs, on a fresh session.
    assert spy.turns[0]["session"] == f"docs-repair:{STORY}"


def test_a_stalled_docs_gate_drops_the_conversation_that_stalled(spy: _Spy) -> None:
    """`stalled` is the gate saying the last pass closed nothing. Continuing the same
    conversation is the one thing already known not to work."""
    _repair(_docs(), DocsProgress(chain_laps=1, gate_progress_verdict="stalled"))

    assert spy.resets == [f"docs-repair:{STORY}"]


def test_ending_the_docs_flow_ends_its_chain(spy: _Spy) -> None:
    """A chain outliving its flow waits for the next entry to resume it, on a book that
    has moved. Every terminal goes through `_ends` so none can forget."""
    done = _docs()._ends(DocsResult(status="passed"))

    assert isinstance(done.result, DocsResult) and done.result.status == "passed"
    assert spy.resets == [f"docs-repair:{STORY}"]


# ── the QA-plan lane ─────────────────────────────────────────────────────────────────


def test_a_qa_plan_repair_lap_mirrors_the_docs_lane(spy: _Spy) -> None:
    _repair_plan(_qa(), QaLoop(chain_laps=1))

    assert spy.turns[0]["session"] == f"qa-plan-repair:{STORY}"
    assert spy.resets == []


def test_a_fifth_consecutive_qa_plan_lap_starts_over(spy: _Spy) -> None:
    flow = _qa()
    _repair_plan(flow, QaLoop(chain_laps=flow.MAX_CHAIN_LAPS))

    assert spy.resets == [f"qa-plan-repair:{STORY}"]


def test_a_qa_plan_lap_that_failed_at_exactly_what_it_failed_at_before_starts_over(
    spy: _Spy,
) -> None:
    """The same signal `_repeating` escalates on: the repair was paid for and the suite
    fails identically, so the conversation that produced it has nothing left to give."""
    _repair_plan(
        _qa(),
        QaLoop(
            chain_laps=1,
            run_failures=["SC-1"],
            repaired_failures=["SC-1"],
            repaired_lap="QA-plan repair",
        ),
    )

    assert spy.resets == [f"qa-plan-repair:{STORY}"]


def test_the_two_lanes_never_share_a_conversation(spy: _Spy) -> None:
    """One story is repaired in both lanes, and the two repairs edit different files
    against different worklists."""
    assert _docs()._chain != _qa()._chain


def test_ending_the_qa_flow_ends_every_chain_it_opened(spy: _Spy) -> None:
    """Not just the plan-repair one: the fix loop, the feedback turn and the regression
    fixer each hold a conversation, and a re-QA of this story resumes whichever survived."""
    done = _qa()._ends(QaFlowResult(status="passed"))

    assert isinstance(done.result, QaFlowResult) and done.result.status == "passed"
    assert spy.resets == [
        f"qa-plan-repair:{STORY}",
        f"qa-fix:{STORY}",
        f"qa-feedback:{STORY}",
        f"qa-regression-fix:{STORY}",
    ]


# ── the QA fix lane ──────────────────────────────────────────────────────────────────


def _apply(flow: Qa, **kwargs: Any) -> None:
    with pytest.raises(_Reached):
        flow._apply_fixes(qa_notes="", operator_feedback=None, power="high", **kwargs)


def test_the_fix_loop_and_the_operator_guided_lap_are_one_conversation(spy: _Spy) -> None:
    """`apply_resolved` is the fix loop being told its attempt did not land. Handing it a
    fresh context throws away the one thing it has that the first turn did not: what it
    already tried."""
    flow = _qa()
    _apply(flow, worklist="fix")
    _apply(flow, worklist="fix")

    assert [turn["session"] for turn in spy.turns] == [f"qa-fix:{STORY}"] * 2


def test_applying_a_product_note_is_not_the_fix_worklist(spy: _Spy) -> None:
    """An operator's note is new work on a passing story, not another lap at a failure —
    and resuming the fixer would put it in a conversation about failures it already fixed."""
    _apply(_qa(), worklist="feedback")

    assert spy.turns[0]["session"] == f"qa-feedback:{STORY}"


# ── the dev lane ─────────────────────────────────────────────────────────────────────


def _refine(flow: Dev, worklist: str) -> None:
    with pytest.raises(_Reached):
        flow._refine(review_notes="", operator_context="", worklist=worklist)


def test_the_three_re_planning_loops_never_share_a_conversation(spy: _Spy) -> None:
    """One prompt, three call sites, three unrelated worklists. Sharing a key would hand
    the reuse pass the operator's answer to a block it was never told about — the stale
    context `rework_reuse` deliberately withholds through its arguments."""
    flow = _dev()
    for worklist in ("block-repair", "reuse-repair", "path-repair"):
        _refine(flow, worklist)

    assert [turn["session"] for turn in spy.turns] == [
        f"plan-{worklist}:{STORY}"
        for worklist in ("block-repair", "reuse-repair", "path-repair")
    ]


def test_a_lint_fix_lap_is_keyed_per_service(spy: _Spy, monkeypatch) -> None:
    """The next layer's linter reports on a different cwd, so resuming there would open
    on the previous service's findings."""
    flow = _dev()
    layer = SimpleNamespace(cwd="/tmp/api", service="api-service")
    monkeypatch.setattr(Dev, "_layer", property(lambda _: layer))
    monkeypatch.setattr(
        Dev, "output", lambda *a, **k: SimpleNamespace(command="make lint", output="")
    )

    with pytest.raises(_Reached):
        flow.fix_lint(index=0, lint_rework=0)

    assert spy.turns[0]["session"] == f"lint-repair:{STORY}:api-service"


def test_ending_the_dev_flow_ends_every_plan_chain(spy: _Spy) -> None:
    """The lint chain is not here because it is dropped per layer, by the state that
    leaves it — by the time the flow ends there is none left to drop."""
    done = _dev()._ends(DevResult())

    assert isinstance(done.result, DevResult)
    assert spy.resets == [
        f"plan-block-repair:{STORY}",
        f"plan-reuse-repair:{STORY}",
        f"plan-path-repair:{STORY}",
    ]
