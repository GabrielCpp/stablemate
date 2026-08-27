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
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from workhorse.pyflow import NodeNotRunError

from workhorse_workflows.coder.dev import flow as dev_flow, nodes
from workhorse_workflows.coder.shared.conversation import backbone
from workhorse_workflows.coder.dev.flow import Dev
from workhorse_workflows.coder.docs import flow as docs_flow
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.qa import flow as qa_flow
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.qa.nodes import run_qa_plan
from workhorse_workflows.coder.review import flow as review_flow
from workhorse_workflows.coder.review.flow import Review
from workhorse_workflows.coder.shared.schemas.dev import DevResult, Lap
from workhorse_workflows.coder.shared.schemas.docs import (
    DocsLoop,
    DocsProgress,
    DocsResult,
)
from workhorse_workflows.coder.shared.schemas.qa import (
    LaneClock,
    QaFlowResult,
    QaLoop,
    QaPlanRun,
)
from workhorse_workflows.coder.shared.schemas.review import (
    CodeReviewResult,
    ReviewLoop,
)

STORY = "STORY-1"


class _Reached(Exception):
    """Raised by the scripted turn: the call under test has been observed."""


class _Spy:
    """What a state asked for, without the run that would normally supply it."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self.resets: list[str] = []
        #: Which chains already have a conversation behind them. `None` — the default —
        #: is every chain, which is what a lane entered from the lane before it sees.
        self.open_chains: set[str] | None = None
        #: What the last `run_qa_plan` recorded, for the states that read it back off the
        #: engine rather than off the loop. `None` is a run that has not happened yet.
        self.run: QaPlanRun | None = None

    def output(self, node: Any) -> Any:
        """What `Workflow.output` resolves to here — only `run_qa_plan` is ever asked for."""
        assert node is run_qa_plan
        if self.run is None:
            raise NodeNotRunError("run_qa_plan has not run")
        return self.run

    def session_id(self, key: str) -> str:
        """What `chain_session(key)` reports: the chain name itself stands in for an id."""
        if self.open_chains is None:
            return key
        return key if key in self.open_chains else ""


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> _Spy:
    """Replace the two engine seams on both flows, plus the helpers that need a run.

    `dirs` and the argument builders read node outputs, which only exist inside a
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
        # Asking whether a chain is open goes through the engine; no turn in these tests
        # reaches a real one, so the resolved id is the chain name itself.
        return SimpleNamespace(session_id=seen.session_id, output=seen.output)

    for flow in (Docs, Qa, Dev, Review):
        monkeypatch.setattr(flow, "agent", fake_agent)
        monkeypatch.setattr(flow, "reset_session", fake_reset)
        monkeypatch.setattr(flow, "logger", property(lambda _: logging.getLogger("test")))
        monkeypatch.setattr(flow, "_require_engine", fake_require_engine)
    monkeypatch.setattr(Qa, "_dirs", lambda _: [])
    # Everywhere else the helper is a shared module function, so the seam is the name each
    # module imported it under rather than an attribute on the class.
    for module in (docs_flow, review_flow, dev_flow, nodes):
        monkeypatch.setattr(module, "workspace_dirs", lambda _: [])
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


def _review(**kwargs: Any) -> Review:
    flow = Review(story=STORY, **kwargs)
    flow._ctx = SimpleNamespace(story_slug=STORY, story_path="", spec_dir="", qa_dir="")
    return flow


def _repair(flow: Docs, progress: DocsProgress) -> None:
    with pytest.raises(_Reached):
        flow.repair(DocsLoop(progress=progress))


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


def test_entering_the_docs_flow_drops_the_story_conversation_too(spy: _Spy) -> None:
    """Docs is the one lane that does not inherit the backbone it names.

    Every other lane joins it to reach the implementer that already read the code. A docs
    pass runs *again* — after a fix, after an operator answer, after a resume — and the
    conversation it would resume describes a book and a set of commits that have both been
    rewritten since, so the author no-ops on edits it remembers making to a tree that no
    longer holds them. Both chains go, and the author turn opens cold.
    """
    _docs()._reset_chains()

    assert spy.resets == [f"story:{STORY}", f"docs-repair:{STORY}"]


def test_ending_the_docs_flow_ends_its_chain(spy: _Spy) -> None:
    """A chain outliving its flow waits for the next entry to resume it, on a book that
    has moved. Every terminal goes through `_ends` so none can forget."""
    done = _docs()._ends(DocsResult(status="passed"))

    assert isinstance(done.result, DocsResult) and done.result.status == "passed"
    assert spy.resets == [f"docs-repair:{STORY}"]
    # The backbone chain is left open for whichever lane runs next, not dropped like
    # the repair chains.
    assert f"story:{STORY}" not in spy.resets


def test_every_lane_names_the_same_conversation_without_being_handed_anything(
    spy: _Spy, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The key is derived from the story slug, and that is the whole transport.

    Handed-off lanes share their parent run's chain directory, so a lane that names the
    key lands in the conversation the lane before it left — with nothing threaded in and
    nothing seeded. A lane run on its own finds no chain there and starts cold, which is
    what makes replaying one lane honest instead of answering out of memory.

    Naming it is all this asserts. Docs names the same key and then drops what is under it
    on entry — see `test_entering_the_docs_flow_drops_the_story_conversation_too`.
    """
    seeded: list[tuple[str, str]] = []
    # A real file: the review lane's `setup` refuses a slug that resolved to no story.
    story_md = tmp_path / "story.md"
    story_md.write_text("# Story\n", encoding="utf-8")
    ctx = SimpleNamespace(
        story_slug=STORY, story_path=str(story_md), spec_dir="", qa_dir=""
    )
    for flow_cls in (Docs, Qa, Dev, Review):
        monkeypatch.setattr(
            flow_cls,
            "seed_session",
            lambda _self, key, sid: seeded.append((key, sid)),
        )
        monkeypatch.setattr(flow_cls, "call", lambda _self, _node, *a, **k: ctx)

    for flow, chain in (
        (_docs(), backbone),
        (_qa(), backbone),
        # The dev lane derives it in `nodes` rather than on the class; the key is the same.
        (_dev(), backbone),
        # The review lane names the same key from the other side: the conversation it
        # rejoins is the implementer's.
        (_review(), lambda f: f._impl_chain()),
    ):
        flow.setup()
        assert chain(flow) == f"story:{STORY}"

    assert seeded == []


def test_no_lane_takes_a_session_id_as_a_parameter(spy: _Spy) -> None:
    """A `Workflow` field is settable from outside with `--params`, and a lane pointed at
    a conversation from outside answers out of that conversation's memory rather than
    from the tree in front of it. There is no such field to point."""
    for flow_cls in (Docs, Qa, Dev, Review):
        assert "session_id" not in flow_cls.model_fields


# ── the QA-plan lane ─────────────────────────────────────────────────────────────────


def test_a_qa_plan_repair_lap_mirrors_the_docs_lane(spy: _Spy) -> None:
    _repair_plan(_qa(), QaLoop(clock=LaneClock(chain_laps=1)))

    assert spy.turns[0]["session"] == f"qa-plan-repair:{STORY}"
    assert spy.resets == []


def test_a_fifth_consecutive_qa_plan_lap_starts_over(spy: _Spy) -> None:
    flow = _qa()
    _repair_plan(flow, QaLoop(clock=LaneClock(chain_laps=qa_flow.MAX_CHAIN_LAPS)))

    assert spy.resets == [f"qa-plan-repair:{STORY}"]


def test_a_qa_plan_lap_that_failed_at_exactly_what_it_failed_at_before_starts_over(
    spy: _Spy,
) -> None:
    """The same signal `_repeating` escalates on: the repair was paid for and the suite
    fails identically, so the conversation that produced it has nothing left to give."""
    spy.run = QaPlanRun(
        status="failed",
        ostler={"scenarios": {"SC-1": {"status": "failed", "assertions": 3, "failures": 1}}},
    )
    _repair_plan(
        _qa(),
        QaLoop(
            clock=LaneClock(chain_laps=1),
            repaired_failures=("SC-1:failed:3/1",),
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
    assert f"story:{STORY}" not in spy.resets


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
    _apply(flow, session=backbone(flow))
    _apply(flow, session=backbone(flow))

    assert [turn["session"] for turn in spy.turns] == [f"story:{STORY}"] * 2


def test_applying_a_product_note_is_not_the_fix_worklist(spy: _Spy) -> None:
    """An operator's note is new work on a passing story, not another lap at a failure —
    and resuming the fixer would put it in a conversation about failures it already fixed."""
    _apply(_qa(), session=f"qa-feedback:{STORY}")

    assert spy.turns[0]["session"] == f"qa-feedback:{STORY}"


# ── the dev lane ─────────────────────────────────────────────────────────────────────


def _refine(flow: Dev, role: str, worklist: str) -> None:
    with pytest.raises(_Reached):
        nodes.refine(flow, role, review_notes="", operator_context="", worklist=worklist)


def test_the_re_planning_loops_never_share_a_conversation(spy: _Spy) -> None:
    """Two prompts, unrelated worklists. Sharing a key would hand the path-repair pass the
    operator's answer to a block it was never told about — the stale context each loop
    deliberately withholds through its arguments."""
    flow = _dev()
    for role, worklist in (("replan-with-answer", "block-repair"), ("repair-plan-paths", "path-repair")):
        _refine(flow, role, worklist)

    assert [turn["session"] for turn in spy.turns] == [
        f"plan-{worklist}:{STORY}" for worklist in ("block-repair", "path-repair")
    ]


def test_a_repair_lap_runs_on_the_story_conversation(spy: _Spy, monkeypatch) -> None:
    """The turn that wrote the code is the cheapest turn to fix it: a fixer in a fresh
    context spends its first minutes re-reading a diff it has only just met."""
    flow = _dev()
    layer = SimpleNamespace(cwd="/tmp/api", service="api-service")
    monkeypatch.setattr(nodes, "current_layer", lambda _: layer)
    monkeypatch.setattr(
        Dev,
        "output",
        lambda *a, **k: SimpleNamespace(
                gate="lint", status="dirty", command="sh lint.sh", output=""
            ),
    )
    monkeypatch.setattr(Dev, "call", lambda *a, **k: SimpleNamespace(paths=[]))

    with pytest.raises(_Reached):
        flow.fix(index=0, lap=Lap())

    assert spy.turns[0]["prompt"] == "dev/prompts/dev-fix.md"
    assert spy.turns[0]["session"] == f"story:{STORY}"


def test_ending_the_dev_flow_ends_every_plan_chain(spy: _Spy) -> None:
    """The story chain is not reset here: it is left open under a key the next lane
    derives for itself, so that lane resumes the conversation rather than reopening one."""
    done = nodes.ends(_dev(), DevResult())

    assert isinstance(done.result, DevResult)
    assert spy.resets == [
        f"plan-block-repair:{STORY}",
        f"plan-path-repair:{STORY}",
    ]


# ── the review lane ──────────────────────────────────────────────────────────────────


def _apply_review(flow: Review, **kwargs: Any) -> None:
    with pytest.raises(_Reached):
        flow.apply(
            notes="the handler ignores the timeout",
            code_review=CodeReviewResult(status="clean"),
            loop=ReviewLoop(),
            **kwargs,
        )


def test_an_apply_turn_rejoins_the_implementer_rather_than_judging_cold(spy: _Spy) -> None:
    """The half of this lane that changes code is not the half that judges it. A finding is
    a request to edit a line somebody just wrote, and the turn that wrote it is the cheapest
    one that can act on it — which is also what makes the low power tier sufficient."""
    _apply_review(_review())

    assert spy.turns[0]["prompt"] == "review/prompts/apply-review.md"
    # The key is the story's; the dev lane earlier in the run is what opened it.
    assert spy.turns[0]["session"] == f"story:{STORY}"
    assert spy.turns[0]["power"] == "low"


def test_the_judging_turns_stay_cold_even_when_the_implementer_is_threaded_in(
    spy: _Spy,
) -> None:
    """The reason the two halves are named apart: a reviewer that inherited the author's
    context is reviewing its own reasoning, so the feeder chain must never be the story's."""
    flow = _review()

    assert flow._feeder_chain == f"review-feeders:{STORY}"
    assert flow._feeder_chain != flow._impl_chain()


def test_a_standalone_pr_review_has_no_implementer_to_resume_and_pays_for_it(
    spy: _Spy,
) -> None:
    """No dev lane in front of it means no context to inherit, so the apply turn is cold —
    and a cold turn needs the reasoning the resumed one did not have to repeat. The chain
    itself is what says which of the two this is: an unopened chain is a cold turn."""
    spy.open_chains = set()
    _apply_review(_review())

    assert spy.turns[0]["session"] == f"story:{STORY}"
    assert spy.turns[0]["power"] == "high"


def test_the_apply_turns_keep_counting_from_what_the_dev_lane_spent(spy: _Spy) -> None:
    """The cap bounds the *conversation*, not each lane's share of it. A review that
    restarted the count would hand the recycler a context twice as long as it agreed to."""
    flow = _review()

    assert flow._spend_turn(ReviewLoop(session_turns=7)).session_turns == 8
    assert spy.resets == []


def test_a_conversation_that_fills_up_inside_the_review_lane_is_recycled(spy: _Spy) -> None:
    """Where the cap is reached is not where it is owned: the dev lane can hand over a
    conversation already at the threshold, and the next apply turn opens a fresh one."""
    flow = _review()

    assert flow._spend_turn(ReviewLoop(session_turns=8)).session_turns == 1
    assert spy.resets == [f"story:{STORY}"]
