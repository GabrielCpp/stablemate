"""Direct-state tests for repair-loop conversations and routing policy."""
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from workhorse.pyflow import NodeNotRunError, WorkflowFailed

from workhorse_workflows.coder.shared.conversation import backbone
from workhorse_workflows.coder.docs import flow as docs_flow
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.dev.flow import Dev
from workhorse_workflows.coder.qa import flow as qa_flow
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.shared.owner import UNBOUNDED, owner_profile
from workhorse_workflows.coder.shared.schemas.docs import DocsResult
from workhorse_workflows.coder.shared.schemas.qa import QaFlowResult, QaPlanRun
from workhorse_workflows.coder.shared.worktree import snapshot_code_state

STORY = "STORY-1"


class _Reached(Exception):
    """Raised by the scripted turn: the call under test has been observed."""


class _Spy:
    """What a state asked for, without the run that would normally supply it."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self.resets: list[str] = []
        self.open_chains: set[str] | None = None

    def output(self, node: Any) -> Any:
        """What `Workflow.output` resolves to here: only the QA entry snapshot is ever asked for."""
        if node is not snapshot_code_state:
            raise NodeNotRunError(f"{node} has not run")
        return SimpleNamespace(status="")

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

    for flow in (Docs, Qa):
        monkeypatch.setattr(flow, "agent", fake_agent)
        monkeypatch.setattr(flow, "reset_session", fake_reset)
        monkeypatch.setattr(flow, "logger", property(lambda _: logging.getLogger("test")))
        monkeypatch.setattr(flow, "_require_engine", fake_require_engine)
    monkeypatch.setattr(Qa, "_dirs", lambda _: [])
    monkeypatch.setattr(docs_flow, "workspace_dirs", lambda _: [])
    monkeypatch.setattr(Docs, "_brief", lambda *a, **k: {})
    monkeypatch.setattr(Qa, "_owner_args", lambda *a, **k: {})
    monkeypatch.setattr(
        qa_flow, "code_changed", lambda _log, **_k: SimpleNamespace(changed=False)
    )
    return seen


def _docs() -> Docs:
    flow = Docs(story=STORY)
    flow._ctx = SimpleNamespace(story_slug=STORY, story_id="", story_path="", spec_dir="", qa_dir="")
    return flow


def _qa() -> Qa:
    flow = Qa(story=STORY)
    flow._ctx = SimpleNamespace(story_slug=STORY, story_id="", story_path="", spec_dir="", qa_dir="")
    return flow




def test_every_docs_turn_continues_the_story_s_own_owner_conversation(spy: _Spy) -> None:
    """Keyed per story: a repair turn already knows what the last turn wrote, and two stories in one run are editing different parts of the book."""
    with pytest.raises(_Reached):
        _docs().work(report="one symbol is not directly grounded", laps=1)

    turn = spy.turns[0]
    assert turn["session"] == f"docs:{STORY}"
    assert turn["power"] == "high"
    assert turn["profile"] == owner_profile("docs")
    assert spy.resets == []


def test_entering_the_docs_flow_starts_a_fresh_owner_conversation(spy: _Spy) -> None:
    """The owner starts from the book, not from a conversation about a book that has moved."""
    with pytest.raises(WorkflowFailed):
        _docs().start()

    assert spy.resets == [f"docs:{STORY}"]


def test_ending_the_docs_flow_ends_its_chain(spy: _Spy) -> None:
    """A chain outliving its flow waits for the next entry to resume it, on a book that has moved."""
    done = _docs()._ends(DocsResult(status="passed"))

    assert isinstance(done.result, DocsResult) and done.result.status == "passed"
    assert spy.resets == [f"docs:{STORY}"]
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
    for flow_cls in (Docs, Qa):
        monkeypatch.setattr(
            flow_cls,
            "seed_session",
            lambda _self, key, sid: seeded.append((key, sid)),
        )
        monkeypatch.setattr(flow_cls, "call", lambda _self, _node, *a, **k: ctx)

    for flow, chain in (
        (_docs(), backbone),
        (_qa(), backbone),
    ):
        flow.setup()
        assert chain(flow) == f"story:{STORY}"

    assert seeded == []


def test_no_lane_takes_a_session_id_as_a_parameter(spy: _Spy) -> None:
    """A `Workflow` field is settable from outside with `--params`, and a lane pointed at a conversation from outside answers out of that conversation's memory rather than from the tree in front of it."""
    for flow_cls in (Docs, Qa, Dev):
        assert "session_id" not in flow_cls.model_fields




def test_the_two_lanes_never_share_a_conversation(spy: _Spy) -> None:
    """One story is repaired in both lanes, and the two repairs edit different files against different worklists."""
    assert _docs()._chain != _qa()._session


def test_every_qa_turn_continues_the_story_s_own_owner_conversation(spy: _Spy) -> None:
    """A repair turn already knows what the last turn planned, ran and audited."""
    with pytest.raises(_Reached):
        _qa().work(report="the dry runs do not pass", laps=1)

    turn = spy.turns[0]
    assert turn["session"] == f"qa:{STORY}"
    assert turn["power"] == "high"
    assert turn["timeout"] == UNBOUNDED
    assert turn["profile"] == owner_profile("qa")
    assert spy.resets == []


def test_a_passed_qa_ends_its_owner_conversation(spy: _Spy) -> None:
    """The next entry QAs a tree that has moved, so it starts from the tree."""
    done = _qa()._finish("passed", QaPlanRun(status="passed"))

    assert isinstance(done.result, QaFlowResult) and done.result.status == "passed"
    assert spy.resets == [f"qa:{STORY}"]
    assert f"story:{STORY}" not in spy.resets


def test_a_refix_keeps_the_owner_conversation_for_the_recheck(spy: _Spy) -> None:
    """The owner rechecks the dev owner's fix knowing what it proved before."""
    done = _qa()._finish("refix", QaPlanRun(status="failed"))

    assert isinstance(done.result, QaFlowResult) and done.result.status == "refix"
    assert spy.resets == []
