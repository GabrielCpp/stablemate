"""Direct-state tests for repair-loop conversations and routing policy."""
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from workhorse.pyflow import Continue, NodeNotRunError

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
        self.open_chains: set[str] | None = None
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

    def call(
        self,
        node: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        span_kind: str = "",
    ) -> Any:
        """Run a deterministic node directly when a state needs its rendered value."""
        return node(logging.getLogger("test"), *args, **kwargs)


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> _Spy:
    """Replace the two engine seams on both flows, plus the helpers that need a run."""
    seen = _Spy()

    def fake_agent(self: Any, prompt: str, **kwargs: Any) -> Any:
        seen.turns.append({"prompt": prompt, **kwargs})
        raise _Reached(prompt)

    def fake_reset(self: Any, key: str) -> None:
        seen.resets.append(key)

    def fake_require_engine(self: Any) -> Any:
        return SimpleNamespace(
            session_id=seen.session_id,
            output=seen.output,
            call=seen.call,
            run_dir=Path("/tmp/stablemate-test-run"),
        )

    for flow in (Docs, Qa, Dev, Review):
        monkeypatch.setattr(flow, "agent", fake_agent)
        monkeypatch.setattr(flow, "reset_session", fake_reset)
        monkeypatch.setattr(flow, "logger", property(lambda _: logging.getLogger("test")))
        monkeypatch.setattr(flow, "_require_engine", fake_require_engine)
    monkeypatch.setattr(Qa, "_dirs", lambda _: [])
    for module in (docs_flow, review_flow, dev_flow, nodes):
        monkeypatch.setattr(module, "workspace_dirs", lambda _: [])
    monkeypatch.setattr(Docs, "_author_args", lambda *a, **k: {})
    monkeypatch.setattr(Qa, "_plan_args", lambda *a, **k: {})
    return seen


def _docs() -> Docs:
    flow = Docs(story=STORY)
    flow._ctx = SimpleNamespace(story_slug=STORY, story_id="", story_path="", spec_dir="", qa_dir="")
    return flow


def _qa() -> Qa:
    flow = Qa(story=STORY)
    flow._ctx = SimpleNamespace(story_slug=STORY, story_id="", story_path="", spec_dir="", qa_dir="")
    return flow


def _dev() -> Dev:
    flow = Dev(story=STORY)
    flow._ctx = SimpleNamespace(story_slug=STORY, story_id="", story_path="", spec_dir="", qa_dir="")
    return flow


def _review(**kwargs: Any) -> Review:
    flow = Review(story=STORY, **kwargs)
    flow._ctx = SimpleNamespace(story_slug=STORY, story_id="", story_path="", spec_dir="", qa_dir="")
    return flow


def _repair(flow: Docs, progress: DocsProgress) -> None:
    with pytest.raises(_Reached):
        flow.repair(DocsLoop(progress=progress))


def _repair_plan(flow: Qa, loop: QaLoop) -> None:
    with pytest.raises(_Reached):
        flow.repair_plan(loop)




def test_a_docs_repair_lap_continues_the_story_s_own_conversation(spy: _Spy) -> None:
    """Keyed per story: the point of the chain is that lap N+1 already knows what lap N was editing, and two stories in one run are editing different parts of the book."""
    _repair(_docs(), DocsProgress(chain_laps=1))

    assert spy.turns[0]["session"] == f"docs-repair:{STORY}"
    assert spy.resets == []


def test_a_fifth_consecutive_docs_lap_starts_over(spy: _Spy) -> None:
    """A conversation that has been wrong four times running is a transcript of four rejected repairs, and compaction summarises those as readily as the useful turns."""
    flow = _docs()
    _repair(flow, DocsProgress(chain_laps=flow.MAX_CHAIN_LAPS))

    assert spy.resets == [f"docs-repair:{STORY}"]
    assert spy.turns[0]["session"] == f"docs-repair:{STORY}"


def test_a_stalled_docs_gate_drops_the_conversation_that_stalled(spy: _Spy) -> None:
    """`stalled` is the gate saying the last pass closed nothing."""
    _repair(_docs(), DocsProgress(chain_laps=1, gate_progress_verdict="stalled"))

    assert spy.resets == [f"docs-repair:{STORY}"]


def test_entering_the_docs_flow_drops_the_story_conversation_too(spy: _Spy) -> None:
    """Docs is the one lane that does not inherit the backbone it names."""
    _docs()._reset_chains()

    assert spy.resets == [f"story:{STORY}", f"docs-repair:{STORY}"]


def test_ending_the_docs_flow_ends_its_chain(spy: _Spy) -> None:
    """A chain outliving its flow waits for the next entry to resume it, on a book that has moved."""
    done = _docs()._ends(DocsResult(status="passed"))

    assert isinstance(done.result, DocsResult) and done.result.status == "passed"
    assert spy.resets == [f"docs-repair:{STORY}"]
    assert f"story:{STORY}" not in spy.resets


def test_every_lane_names_the_same_conversation_without_being_handed_anything(
    spy: _Spy, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The key is derived from the story slug, and that is the whole transport."""
    seeded: list[tuple[str, str]] = []
    story_md = tmp_path / "story.md"
    story_md.write_text("# Story\n", encoding="utf-8")
    spec_dir = tmp_path / "specs" / STORY
    ctx = SimpleNamespace(
        story_slug=STORY, story_id="", story_path=str(story_md), spec_dir=str(spec_dir), qa_dir=""
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
        (_dev(), backbone),
        (_review(), lambda f: f._impl_chain()),
    ):
        flow.setup()
        assert chain(flow) == f"story:{STORY}"

    assert seeded == []


def test_no_lane_takes_a_session_id_as_a_parameter(spy: _Spy) -> None:
    """A `Workflow` field is settable from outside with `--params`, and a lane pointed at a conversation from outside answers out of that conversation's memory rather than from the tree in front of it."""
    for flow_cls in (Docs, Qa, Dev, Review):
        assert "session_id" not in flow_cls.model_fields




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
    """The same signal `_repeating` escalates on: the repair was paid for and the suite fails identically, so the conversation that produced it has nothing left to give."""
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
    """One story is repaired in both lanes, and the two repairs edit different files against different worklists."""
    assert _docs()._chain != _qa()._chain


def test_ending_the_qa_flow_ends_every_chain_it_opened(spy: _Spy) -> None:
    """Not just the plan-repair one: the feedback turn and the regression fixer each hold a conversation of their own."""
    done = _qa()._ends(QaFlowResult(status="passed"))

    assert isinstance(done.result, QaFlowResult) and done.result.status == "passed"
    assert spy.resets == [
        f"qa-plan-repair:{STORY}",
        f"qa-feedback:{STORY}",
        f"qa-regression-fix:{STORY}",
    ]
    assert f"story:{STORY}" not in spy.resets




@pytest.mark.parametrize(
    ("guard", "loop", "counter", "spent"),
    [
        (
            "context",
            QaLoop(context_rework=qa_flow.MAX_CONTEXT_REWORKS),
            "context_rework",
            f"{qa_flow.MAX_CONTEXT_REWORKS} context repair",
        ),
        (
            "schema",
            QaLoop(plan_validation_rework=qa_flow.MAX_PLAN_VALIDATION_REWORKS),
            "plan_validation_rework",
            "0 plan repair",
        ),
        (
            "plan",
            QaLoop(plan_rework=qa_flow.MAX_PLAN_REWORKS),
            "plan_rework",
            f"{qa_flow.MAX_PLAN_REWORKS} plan repair",
        ),
        (
            "code",
            QaLoop(qa_rework=qa_flow.MAX_QA_REWORKS, failure_class="code"),
            "qa_rework",
            f"{qa_flow.MAX_QA_REWORKS} code rework",
        ),
        (
            "setup",
            QaLoop(setup_rework=qa_flow.MAX_SETUP_REWORKS),
            "setup_rework",
            f"{qa_flow.MAX_SETUP_REWORKS} setup repair",
        ),
    ],
    ids=("context", "schema", "plan", "code", "setup"),
)
def test_each_spent_qa_budget_routes_to_the_operator_with_its_own_counter(
    spy: _Spy,
    guard: str,
    loop: QaLoop,
    counter: str,
    spent: str,
) -> None:
    """Budget guards preserve the exhausted counter when they enter the operator gate."""
    flow = _qa()

    if guard == "context":
        transition = flow._exhausted(loop, "context repair")
    elif guard == "schema":
        transition = flow._guard_plan_validation(object(), loop)
    elif guard == "plan":
        transition = flow._guard_plan(object(), loop)
    elif guard == "code":
        transition = flow._guard_qa(object(), loop)
    else:
        transition = flow._guard_setup(object(), loop)

    assert isinstance(transition, Continue) and transition.state == "resolve_operator"
    routed = transition.params["loop"]
    assert isinstance(routed, QaLoop)
    assert getattr(routed, counter) == getattr(loop, counter)
    assert spent in qa_flow._escalation(flow, routed).body


def test_the_total_plan_lap_ceiling_bounds_individually_legal_budgets(spy: _Spy) -> None:
    """Schema and judgement laps cannot alternate past their shared total ceiling."""
    loop = QaLoop(
        plan_rework=qa_flow.MAX_PLAN_REWORKS - 1,
        plan_validation_rework=qa_flow.MAX_PLAN_VALIDATION_REWORKS,
    )

    transition = _qa()._guard_plan(object(), loop)

    assert isinstance(transition, Continue) and transition.state == "resolve_operator"
    routed = transition.params["loop"]
    assert isinstance(routed, QaLoop)
    assert routed.plan_rework_total == qa_flow.MAX_TOTAL_PLAN_LAPS + 1


@pytest.mark.parametrize(
    ("qa_rework", "failure_class", "bonus_used", "state", "routed_bonus"),
    [
        (qa_flow.MAX_QA_REWORKS - 1, "code", False, "apply_fixes", False),
        (qa_flow.MAX_QA_REWORKS, "evidence", False, "apply_fixes", True),
        (qa_flow.MAX_QA_REWORKS, "evidence", True, "resolve_operator", True),
        (qa_flow.MAX_QA_REWORKS, "code", False, "resolve_operator", False),
    ],
    ids=("ordinary-lap", "evidence-bonus", "spent-bonus", "code-no-bonus"),
)
def test_only_an_unspent_evidence_bonus_can_cross_the_code_rework_ceiling(
    spy: _Spy,
    qa_rework: int,
    failure_class: Any,
    bonus_used: bool,
    state: str,
    routed_bonus: bool,
) -> None:
    """The extra fix lap belongs only to a first evidence failure at the ceiling."""
    transition = _qa()._guard_qa(
        object(),
        QaLoop(
            qa_rework=qa_rework,
            failure_class=failure_class,
            bonus_used=bonus_used,
        ),
    )

    assert isinstance(transition, Continue) and transition.state == state
    routed = transition.params["loop"]
    assert isinstance(routed, QaLoop)
    assert routed.bonus_used is routed_bonus




def _apply(flow: Qa, **kwargs: Any) -> None:
    with pytest.raises(_Reached):
        flow._apply_fixes(qa_notes="", operator_feedback=None, power="high", **kwargs)


def test_the_fix_loop_and_the_operator_guided_lap_are_one_conversation(spy: _Spy) -> None:
    """`apply_resolved` is the fix loop being told its attempt did not land."""
    flow = _qa()
    _apply(flow, session=backbone(flow))
    _apply(flow, session=backbone(flow))

    assert [turn["session"] for turn in spy.turns] == [f"story:{STORY}"] * 2


def test_applying_a_product_note_is_not_the_fix_worklist(spy: _Spy) -> None:
    """An operator's note is new work on a passing story, not another lap at a failure — and resuming the fixer would put it in a conversation about failures it already fixed."""
    _apply(_qa(), session=f"qa-feedback:{STORY}")

    assert spy.turns[0]["session"] == f"qa-feedback:{STORY}"




def _refine(flow: Dev, role: str, worklist: str) -> None:
    with pytest.raises(_Reached):
        nodes.refine(flow, role, review_notes="", operator_context="", worklist=worklist)


def test_the_re_planning_loops_never_share_a_conversation(spy: _Spy) -> None:
    """Two prompts, unrelated worklists."""
    flow = _dev()
    for role, worklist in (("replan-with-answer", "block-repair"), ("repair-plan-paths", "path-repair")):
        _refine(flow, role, worklist)

    assert [turn["session"] for turn in spy.turns] == [
        f"plan-{worklist}:{STORY}" for worklist in ("block-repair", "path-repair")
    ]


def test_a_repair_lap_runs_on_the_story_conversation(spy: _Spy, monkeypatch) -> None:
    """The turn that wrote the code is the cheapest turn to fix it: a fixer in a fresh context spends its first minutes re-reading a diff it has only just met."""
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
    """The story chain is not reset here: it is left open under a key the next lane derives for itself, so that lane resumes the conversation rather than reopening one."""
    done = nodes.ends(_dev(), DevResult())

    assert isinstance(done.result, DevResult)
    assert spy.resets == [
        f"plan-block-repair:{STORY}",
        f"plan-path-repair:{STORY}",
    ]




def _apply_review(flow: Review, **kwargs: Any) -> None:
    with pytest.raises(_Reached):
        flow.apply(
            notes="the handler ignores the timeout",
            code_review=CodeReviewResult(status="clean"),
            loop=ReviewLoop(),
            **kwargs,
        )


def test_an_apply_turn_rejoins_the_implementer_rather_than_judging_cold(spy: _Spy) -> None:
    """The half of this lane that changes code is not the half that judges it."""
    _apply_review(_review())

    assert spy.turns[0]["prompt"] == "review/prompts/apply-review.md"
    assert spy.turns[0]["session"] == f"story:{STORY}"
    assert spy.turns[0]["power"] == "low"


def test_the_judging_turns_stay_cold_even_when_the_implementer_is_threaded_in(
    spy: _Spy,
) -> None:
    """The reason the two halves are named apart: a reviewer that inherited the author's context is reviewing its own reasoning, so the feeder chain must never be the story's."""
    flow = _review()

    assert flow._feeder_chain == f"review-feeders:{STORY}"
    assert flow._feeder_chain != flow._impl_chain()


def test_a_standalone_pr_review_has_no_implementer_to_resume_and_pays_for_it(
    spy: _Spy,
) -> None:
    """No dev lane in front of it means no context to inherit, so the apply turn is cold — and a cold turn needs the reasoning the resumed one did not have to repeat."""
    spy.open_chains = set()
    _apply_review(_review())

    assert spy.turns[0]["session"] == f"story:{STORY}"
    assert spy.turns[0]["power"] == "high"


def test_the_apply_turns_keep_counting_from_what_the_dev_lane_spent(spy: _Spy) -> None:
    """The cap bounds the *conversation*, not each lane's share of it."""
    flow = _review()

    assert flow._spend_turn(ReviewLoop(session_turns=7)).session_turns == 8
    assert spy.resets == []


def test_a_conversation_that_fills_up_inside_the_review_lane_is_recycled(spy: _Spy) -> None:
    """Where the cap is reached is not where it is owned: the dev lane can hand over a conversation already at the threshold, and the next apply turn opens a fresh one."""
    flow = _review()

    assert flow._spend_turn(ReviewLoop(session_turns=8)).session_turns == 1
    assert spy.resets == [f"story:{STORY}"]
