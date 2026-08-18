"""Named session chains: the laps of a repair loop as one conversation.

The default is one clean context per turn, and everything here is about the deliberate
exception — `self.agent(..., session="docs-repair:STORY-4")`. What matters is that the
chain is kept *beside* the clean-context session rather than instead of it (a chain must
not leak into the next reviewer's turn), that a second lap actually resumes rather than
re-deriving, that `reset_session` ends it, and that a session the CLI will not resume
costs the node no budget of any kind.

    ./.venv/bin/python tests/test_session_chain.py
    ./.venv/bin/python -m pytest tests/test_session_chain.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _fakes import FakeBackend, FakeClock  # noqa: E402
from workhorse import sessions  # noqa: E402
from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.config_run import AgentResilience, RunConfig  # noqa: E402
from workhorse.context import WorkflowContext  # noqa: E402
from workhorse.pyflow import Continue, Done, Workflow  # noqa: E402
from workhorse.pyflow.driver import drive  # noqa: E402
from workhorse.pyflow.engine import RunEnv  # noqa: E402
from workhorse.runner import ladder  # noqa: E402
from workhorse.runner.failure import (  # noqa: E402
    BackendInvocationError,
    is_unresumable_session,
)
from workhorse.runner.spec import AgentNode  # noqa: E402

Transition = Any


class Payload(BaseModel):
    kind: str = "?"


class ScriptedRunner:
    """The recovery ladder as a plain function the test supplies (see test_pyflow)."""

    def __init__(self, run: Any) -> None:
        self.run = run


def _env(tmp: str, **kwargs: Any) -> RunEnv:
    writer = ArtifactWriter("acme", Path(tmp) / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(tmp),
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        **kwargs,
    )


def _enters(env: RunEnv, node_id: str) -> list[dict[str, Any]]:
    """The `enter` records of one node. Filtered by node because the driver records a
    state's entry the same way, and a state is not the turn under test."""
    path = env.run_dir / ArtifactWriter.EVENTS_FILE
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [
        e for e in events if e.get("phase") == "enter" and e.get("node") == node_id
    ]


# ------------------------------------------------------------------- the engine side


def test_a_chain_files_its_session_under_the_key_and_leaves_session_id_alone():
    """A chain lives in `.sessions/<key>`, so it cannot be the session the next
    clean-context node inherits — which is the whole reason the default exists."""
    with tempfile.TemporaryDirectory() as tmp:
        seen: list[dict[str, Any]] = []

        def fake_run(node: Any, ctx: Any, wdir: Any, sid: Any, **kwargs: Any) -> Any:
            seen.append({"node": node.id, "sid": sid, **kwargs})
            return "rendered", {"kind": "ok"}

        env = _env(tmp, agent_runner=ScriptedRunner(fake_run))

        class Asks(Workflow):
            def start(self) -> Transition:
                self.agent("prompts/repair.md", returns=Payload, session="docs:STORY-1")
                self.agent("prompts/review.md", returns=Payload)
                return Done(None)

        drive(Asks(), env)

        assert seen[0]["sid"] == env.run_dir / ".sessions" / "docs-STORY-1", seen[0]
        # The chain is resumed by definition; without this the ladder would unlink the
        # file it was just handed and every lap would start fresh anyway.
        assert seen[0]["resume_session"] is True, seen[0]
        assert seen[0]["session_chain"] == "docs:STORY-1", seen[0]
        # The unchained node keeps the ordinary per-node clean context.
        assert seen[1]["sid"] == env.run_dir / ".session_id", seen[1]
        assert seen[1]["resume_session"] is False, seen[1]
        assert seen[1]["session_chain"] == "", seen[1]


def test_the_second_lap_of_a_chain_reports_the_session_it_resumed():
    """The `enter` record is where a reader finds out whether a lap continued a
    conversation or opened a new one — the alternative is joining three files by hand."""
    with tempfile.TemporaryDirectory() as tmp:

        def fake_run(node: Any, ctx: Any, wdir: Any, sid: Any, **kwargs: Any) -> Any:
            # What a backend does at the end of a turn: name the session it used.
            sid.parent.mkdir(parents=True, exist_ok=True)
            sid.write_text("sess-abc")
            return "rendered", {"kind": "ok"}

        env = _env(tmp, agent_runner=ScriptedRunner(fake_run))

        class Asks(Workflow):
            def start(self) -> Transition:
                self.agent("prompts/repair.md", returns=Payload, session="docs:S-1")
                return Continue(None, self.again)

            def again(self) -> Transition:
                self.agent("prompts/repair.md", returns=Payload, session="docs:S-1")
                return Done(None)

        drive(Asks(), env)

        enters = _enters(env, "repair")
        assert [e.get("chain") for e in enters] == ["docs:S-1", "docs:S-1"], enters
        # Lap one had nothing to resume; lap two continues what lap one opened.
        assert enters[0]["resumed_session"] == "", enters[0]
        assert enters[1]["resumed_session"] == "sess-abc", enters[1]


def test_an_unchained_turn_says_nothing_about_chains():
    """An `enter` carrying `chain: ""` would say a chainless turn had been considered
    for one, which is not a distinction the record should invent."""
    with tempfile.TemporaryDirectory() as tmp:

        def fake_run(node: Any, ctx: Any, wdir: Any, sid: Any, **kwargs: Any) -> Any:
            return "rendered", {"kind": "ok"}

        env = _env(tmp, agent_runner=ScriptedRunner(fake_run))

        class Asks(Workflow):
            def start(self) -> Transition:
                self.agent("prompts/review.md", returns=Payload)
                return Done(None)

        drive(Asks(), env)

        (enter,) = _enters(env, "review")
        assert "chain" not in enter, enter
        assert "resumed_session" not in enter, enter


def test_reset_session_ends_the_chain_and_forgives_one_that_never_ran():
    with tempfile.TemporaryDirectory() as tmp:

        def fake_run(node: Any, ctx: Any, wdir: Any, sid: Any, **kwargs: Any) -> Any:
            sid.parent.mkdir(parents=True, exist_ok=True)
            sid.write_text("sess-abc")
            return "rendered", {"kind": "ok"}

        env = _env(tmp, agent_runner=ScriptedRunner(fake_run))

        class Asks(Workflow):
            def start(self) -> Transition:
                self.agent("prompts/repair.md", returns=Payload, session="docs:S-1")
                self.reset_session("docs:S-1")
                # A chain that never ran is a no-op, not an error: a flow resets on
                # entry, and on entry there is usually nothing to reset.
                self.reset_session("docs:S-2")
                return Done(None)

        drive(Asks(), env)

        assert not (env.run_dir / ".sessions" / "docs-S-1").exists()


def test_a_literal_session_id_resumes_that_exact_conversation():
    """The id a caller already holds — out of checkpointed state, or from an operator —
    goes where a key goes. Seeding the file with it *is* the resume."""
    with tempfile.TemporaryDirectory() as tmp:
        seen: list[dict[str, Any]] = []

        def fake_run(node: Any, ctx: Any, wdir: Any, sid: Any, **kwargs: Any) -> Any:
            seen.append({"sid": sid, "held": sid.read_text().strip(), **kwargs})
            return "rendered", {"kind": "ok"}

        env = _env(tmp, agent_runner=ScriptedRunner(fake_run))
        held = "3f2b1c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"

        class Asks(Workflow):
            def start(self) -> Transition:
                self.agent("prompts/repair.md", returns=Payload, session=held)
                return Done(None)

        drive(Asks(), env)

        assert seen[0]["held"] == held, seen[0]
        assert seen[0]["resume_session"] is True, seen[0]
        # And the record says which conversation, not just that there was one.
        (enter,) = _enters(env, "repair")
        assert enter["resumed_session"] == held, enter


def test_the_id_a_chain_is_on_is_readable_so_a_state_can_checkpoint_it():
    """A chain file survives a resume because it lives in the run directory; an id a
    *state* holds survives because the state's parameters are its checkpoint. This is
    the accessor that lets the second one exist."""
    with tempfile.TemporaryDirectory() as tmp:
        held: list[str] = []

        def fake_run(node: Any, ctx: Any, wdir: Any, sid: Any, **kwargs: Any) -> Any:
            sid.parent.mkdir(parents=True, exist_ok=True)
            sid.write_text("11111111-2222-4333-8444-555555555555")
            return "rendered", {"kind": "ok"}

        env = _env(tmp, agent_runner=ScriptedRunner(fake_run))

        class Asks(Workflow):
            def start(self) -> Transition:
                # Nothing has run on it yet, and an empty answer is the honest one.
                held.append(self.session_id("docs:S-1"))
                self.agent("prompts/repair.md", returns=Payload, session="docs:S-1")
                held.append(self.session_id("docs:S-1"))
                held.append(self.session_id("docs:S-2"))
                return Done(None)

        drive(Asks(), env)

        assert held == ["", "11111111-2222-4333-8444-555555555555", ""], held


def test_a_chain_key_is_never_mistaken_for_an_id():
    """The two live in one parameter, so the test that tells them apart is the contract."""
    assert sessions.is_session_id("11111111-2222-4333-8444-555555555555")
    assert not sessions.is_session_id("qa-plan-repair:STORY-1")
    assert not sessions.is_session_id("")


def test_two_stories_repairing_in_one_run_do_not_share_a_conversation():
    """The key is per worklist. Sharing one would open story two on story one's diff."""
    with tempfile.TemporaryDirectory() as tmp:
        seen: list[Path] = []

        def fake_run(node: Any, ctx: Any, wdir: Any, sid: Any, **kwargs: Any) -> Any:
            seen.append(sid)
            return "rendered", {"kind": "ok"}

        env = _env(tmp, agent_runner=ScriptedRunner(fake_run))

        class Asks(Workflow):
            def start(self) -> Transition:
                for story in ("S-1", "S-2"):
                    self.agent(
                        "prompts/repair.md", returns=Payload, session=f"docs:{story}"
                    )
                return Done(None)

        drive(Asks(), env)

        assert seen[0] != seen[1], seen


def test_a_key_that_is_not_a_filename_still_names_one_file():
    """A key carries a story id and a colon, and a key is a name rather than a path —
    a `/` in one must not quietly make a directory."""
    assert sessions.slug("qa-plan-repair:STORY-1") == "qa-plan-repair-STORY-1"
    assert "/" not in sessions.slug("docs/repair:a/b")
    assert sessions.slug("///") == "chain"


def test_the_run_directory_is_recoverable_from_either_kind_of_session_file():
    """`sessions.jsonl`, the visit counter and the transcripts are per run, so a chain
    file one level deeper must not drag them into `.sessions/`."""
    run = Path("/runs/acme-t")
    assert sessions.run_dir_of(run / ".session_id") == run
    assert sessions.run_dir_of(sessions.chain_path(run, "docs:S-1")) == run


# ------------------------------------------------------------------- the ladder side


def _node() -> AgentNode:
    return AgentNode(type="agent", id="repair", prompt="Fix it.", next="done")


def _drive_ladder(turns: list[Any], session_id_path: Path, **kwargs: Any) -> list[str]:
    """Run the node against a scripted sequence of turn outcomes; return the prompts."""
    prompts: list[str] = []

    def turn(prompt: str, node_id: str, sid: Any, model: Any = None, **_: Any) -> str:
        prompts.append(prompt)
        outcome = turns.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    with patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)):
        ladder.AgentRunner(
            backend=FakeBackend(turn=turn),
            clock=FakeClock(),
            resilience=AgentResilience(),
        ).run(
            _node(),
            WorkflowContext(initial={}),
            Path("."),
            session_id_path,
            **kwargs,
        )
    return prompts


def test_a_session_the_cli_will_not_resume_is_dropped_and_the_same_prompt_re_run():
    """Not a retry and not a reframe: the id is dead, but nothing about the node is
    wrong. Re-asking a simplified prompt would spend a rephrase on the wrong problem."""
    with tempfile.TemporaryDirectory() as tmp:
        chain = sessions.chain_path(Path(tmp), "docs:S-1")
        chain.parent.mkdir(parents=True)
        chain.write_text("sess-gone")

        prompts = _drive_ladder(
            [
                BackendInvocationError("No conversation found with session ID sess-gone"),
                json.dumps({}),
            ],
            chain,
            resume_session=True,
            session_chain="docs:S-1",
        )

        # The dead id is forgotten...
        assert not chain.exists()
        # ...and the second attempt is the SAME prompt, not a reframed one.
        assert prompts == ["Fix it.", "Fix it."], prompts


def test_an_unresumable_first_turn_with_no_session_file_is_not_swallowed():
    """The recovery is bounded by the file: with nothing to unlink there is nothing to
    recover from, and the error has to reach the normal ladder rather than loop."""
    with tempfile.TemporaryDirectory() as tmp:
        chain = sessions.chain_path(Path(tmp), "docs:S-1")
        try:
            _drive_ladder(
                [BackendInvocationError("could not resume session")],
                chain,
                resume_session=True,
                session_chain="docs:S-1",
            )
        except BackendInvocationError:
            return
        raise AssertionError("expected the error to reach the ladder")


def test_the_markers_name_a_refused_resume_and_nothing_else():
    assert is_unresumable_session("No conversation found with session ID abc")
    assert is_unresumable_session("Error: session not found")
    assert is_unresumable_session("could not resume")
    # A cap and an overflow have their own layers; reading either as a dead session
    # would throw away a live conversation to fix a problem it does not have.
    assert not is_unresumable_session("session limit · resets 11:30am")
    assert not is_unresumable_session("prompt is too long")


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
