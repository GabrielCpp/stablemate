"""The two repair loops that run their laps as one conversation.

`docs.repair` and `qa.repair_plan` are the only states in the coder that pass
`session=` to a turn. Everything here is about the part of that decision the engine
cannot make for them: which key a lap runs under, and *when the conversation has to be
thrown away* — because a chain that outlives what it was repairing is worse than no
chain at all, and no test downstream of these two states can see the difference.

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

from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.qa.flow import Qa
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

    for flow in (Docs, Qa):
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


def test_ending_the_qa_flow_ends_its_chain(spy: _Spy) -> None:
    done = _qa()._ends(QaFlowResult(status="passed"))

    assert isinstance(done.result, QaFlowResult) and done.result.status == "passed"
    assert spy.resets == [f"qa-plan-repair:{STORY}"]
