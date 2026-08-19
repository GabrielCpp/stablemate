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

    def fake_require_engine(self: Any) -> Any:
        # `_ends` resolves the backbone chain's id through the engine; no turn in these
        # tests reaches a real one, so the resolved id is the chain name itself.
        return SimpleNamespace(session_id=lambda key: key)

    for flow in (Docs, Qa, Dev):
        monkeypatch.setattr(flow, "agent", fake_agent)
        monkeypatch.setattr(flow, "reset_session", fake_reset)
        monkeypatch.setattr(flow, "logger", property(lambda _: logging.getLogger("test")))
        monkeypatch.setattr(flow, "_dirs", lambda _: [])
        monkeypatch.setattr(flow, "_require_engine", fake_require_engine)
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
    # The backbone chain is stamped on the way out, not dropped like the repair chains.
    assert done.result.session_id == f"story:{STORY}"


def test_the_docs_backbone_resumes_an_incoming_session_rather_than_naming_a_fresh_one(
    spy: _Spy,
) -> None:
    """A `session_id` threaded in from `dev` is the conversation to continue — not a
    reason to open a second one keyed on the story slug."""
    flow = _docs()
    flow.session_id = "story:from-dev"

    assert flow._story_chain() == "story:from-dev"


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
    """Not just the plan-repair one: the feedback turn and the regression fixer each hold
    a conversation of their own. The fix loop is not here — it runs on the backbone chain,
    which is stamped for the next stage rather than dropped."""
    done = _qa()._ends(QaFlowResult(status="passed"))

    assert isinstance(done.result, QaFlowResult) and done.result.status == "passed"
    assert spy.resets == [
        f"qa-plan-repair:{STORY}",
        f"qa-feedback:{STORY}",
        f"qa-regression-fix:{STORY}",
    ]
    assert done.result.session_id == f"story:{STORY}"


def test_the_qa_backbone_resumes_an_incoming_session_rather_than_naming_a_fresh_one(
    spy: _Spy,
) -> None:
    flow = _qa()
    flow.session_id = "story:from-docs"

    assert flow._story_chain() == "story:from-docs"


# ── the QA fix lane ──────────────────────────────────────────────────────────────────


def _apply(flow: Qa, **kwargs: Any) -> None:
    with pytest.raises(_Reached):
        flow._apply_fixes(qa_notes="", operator_feedback=None, power="high", **kwargs)


def test_the_fix_loop_and_the_operator_guided_lap_are_one_conversation(spy: _Spy) -> None:
    """`apply_resolved` is the fix loop being told its attempt did not land. Handing it a
    fresh context throws away the one thing it has that the first turn did not: what it
    already tried. Both run on the story's backbone chain, which also means a fix lap
    resumes an implement session threaded in from a prior stage rather than a cold one."""
    flow = _qa()
    _apply(flow, session=flow._story_chain())
    _apply(flow, session=flow._story_chain())

    assert [turn["session"] for turn in spy.turns] == [f"story:{STORY}"] * 2


def test_applying_a_product_note_is_not_the_fix_worklist(spy: _Spy) -> None:
    """An operator's note is new work on a passing story, not another lap at a failure —
    and resuming the fixer would put it in a conversation about failures it already fixed."""
    _apply(_qa(), session=f"qa-feedback:{STORY}")

    assert spy.turns[0]["session"] == f"qa-feedback:{STORY}"


# ── the dev lane ─────────────────────────────────────────────────────────────────────


def _refine(flow: Dev, worklist: str) -> None:
    with pytest.raises(_Reached):
        flow._refine(review_notes="", operator_context="", worklist=worklist)


def test_the_re_planning_loops_never_share_a_conversation(spy: _Spy) -> None:
    """One prompt, several call sites, unrelated worklists. Sharing a key would hand the
    path-repair pass the operator's answer to a block it was never told about — the stale
    context each loop deliberately withholds through its arguments."""
    flow = _dev()
    for worklist in ("block-repair", "path-repair"):
        _refine(flow, worklist)

    assert [turn["session"] for turn in spy.turns] == [
        f"plan-{worklist}:{STORY}" for worklist in ("block-repair", "path-repair")
    ]


def test_a_repair_lap_runs_on_the_story_conversation(spy: _Spy, monkeypatch) -> None:
    """The turn that wrote the code is the cheapest turn to fix it: a fixer in a fresh
    context spends its first minutes re-reading a diff it has only just met."""
    flow = _dev()
    layer = SimpleNamespace(cwd="/tmp/api", service="api-service")
    monkeypatch.setattr(Dev, "_layer", property(lambda _: layer))
    monkeypatch.setattr(
        Dev,
        "output",
        lambda *a, **k: SimpleNamespace(
                gate="lint", status="dirty", command="sh lint.sh", output=""
            ),
    )
    monkeypatch.setattr(Dev, "call", lambda *a, **k: SimpleNamespace(paths=[]))

    with pytest.raises(_Reached):
        flow.fix(index=0, fix_lap=0)

    assert spy.turns[0]["prompt"] == "prompts/dev-fix.md"
    assert spy.turns[0]["session"] == f"story:{STORY}"


def test_ending_the_dev_flow_ends_every_plan_chain(spy: _Spy) -> None:
    """The story chain is not reset here: its id is stamped onto the result instead, so
    the next stage resumes the conversation rather than reopening one."""
    done = _dev()._ends(DevResult())

    assert isinstance(done.result, DevResult)
    assert spy.resets == [
        f"plan-block-repair:{STORY}",
        f"plan-path-repair:{STORY}",
    ]
    assert done.result.session_id == f"story:{STORY}"


def test_the_dev_backbone_resumes_an_incoming_session_rather_than_naming_a_fresh_one(
    spy: _Spy,
) -> None:
    flow = _dev()
    flow.session_id = "story:from-a-resumed-run"

    assert flow._story_chain() == "story:from-a-resumed-run"
