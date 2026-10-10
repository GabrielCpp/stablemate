"""A node's replacement session opens with its rebrief, and its watchdog waits on its own silence bound."""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pydantic

from _fakes import FakeBackend, FakeClock
from workhorse.config_run import AgentResilience
from workhorse.context import WorkflowContext
from workhorse.runner import ladder
from workhorse.runner.failure import BackendInvocationError
from workhorse.runner.spec import AgentNode, OutputSpec
from workhorse.runner.turn_record import parse_turn_record

BRIEF = "The plan is filed. Items one and two are done. Continue with item three."
DONE = json.dumps({"decision": "approve"})


def _node(**kw: Any) -> AgentNode:
    return AgentNode(
        type="agent",
        id="lead",
        prompt="Lead the work.",
        outputs=[OutputSpec(key="decision")],
        next=None,
        **kw,
    )


class _Warnings(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def _drive(
    script: Any,
    *,
    node: AgentNode | None = None,
    compact: Any = None,
    rebrief: Any = None,
    run_dir: Path | None = None,
    session: str | None = "sess-old",
    **resilience: Any,
) -> tuple[Path, list[str], tuple[str, dict[str, Any]]]:
    sidp = Path(tempfile.mkdtemp()) / ".sessions" / "lead"
    if session is not None:
        sidp.parent.mkdir(parents=True)
        sidp.write_text(session)

    class ScriptedRunner(ladder.AgentRunner):
        def turn(self, prompt, node_id, session_id_path, model=None, **kwargs):
            return script(prompt, session_id_path)

    runner = ScriptedRunner(
        backend=FakeBackend(compact=compact),
        resilience=AgentResilience(**resilience),
        clock=FakeClock(),
    )
    handler = _Warnings()
    ladder.logger.addHandler(handler)
    try:
        with patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)):
            result = runner.run(
                node or _node(),
                WorkflowContext(initial={}),
                Path("."),
                sidp,
                resume_session=True,
                session_chain="lead",
                run_dir=run_dir,
                rebrief=rebrief,
            )
    finally:
        ladder.logger.removeHandler(handler)
    return sidp, handler.lines, result


def test_an_unresumable_session_is_replaced_by_one_opened_with_the_rebrief():
    prompts: list[str] = []
    present: list[bool] = []

    def script(prompt: str, sidp: Path) -> str:
        prompts.append(prompt)
        present.append(sidp.exists())
        if len(prompts) == 1:
            raise BackendInvocationError("No conversation found with session ID: sess-old")
        return DONE

    run_dir = Path(tempfile.mkdtemp())
    _, warnings, (rendered, outputs) = _drive(script, rebrief=lambda: BRIEF, run_dir=run_dir)

    assert prompts == ["Lead the work.", BRIEF]
    assert present == [True, False]
    assert outputs == {"decision": "approve"}
    assert rendered == BRIEF
    assert (run_dir / "lead" / "prompt.md").read_text() == BRIEF
    assert len(warnings) == 1
    assert "[lead] chain lead replaced" in warnings[0]
    assert "cannot be resumed" in warnings[0]


def test_an_unresumable_session_without_a_rebrief_resends_the_same_prompt():
    prompts: list[str] = []

    def script(prompt: str, sidp: Path) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            raise BackendInvocationError("No conversation found with session ID: sess-old")
        return DONE

    _, warnings, _ = _drive(script)

    assert prompts == ["Lead the work.", "Lead the work."]
    assert warnings == []


def test_a_session_compaction_cannot_shrink_is_replaced_by_one_opened_with_the_rebrief():
    prompts: list[str] = []
    present: list[bool] = []

    def script(prompt: str, sidp: Path) -> str:
        prompts.append(prompt)
        present.append(sidp.exists())
        if prompt != BRIEF:
            raise BackendInvocationError("prompt is too long", overflow=True)
        return DONE

    sidp, warnings, (_, outputs) = _drive(
        script, compact=lambda *a, **k: False, rebrief=lambda: BRIEF
    )

    assert prompts == ["Lead the work.", BRIEF]
    assert present == [True, False]
    assert outputs == {"decision": "approve"}
    assert not sidp.exists()
    assert len(warnings) == 1
    assert "[lead] chain lead replaced" in warnings[0]
    assert "compaction can no longer shrink the session" in warnings[0]


def test_the_rebrief_follows_every_compaction_attempt_being_spent():
    compacted: list[int] = []

    def script(prompt: str, sidp: Path) -> str:
        if prompt != BRIEF:
            raise BackendInvocationError("context window exceeded", overflow=True)
        return DONE

    def compact(*args: Any, **kwargs: Any) -> bool:
        compacted.append(1)
        return True

    _, _, (_, outputs) = _drive(
        script, compact=compact, rebrief=lambda: BRIEF, max_compact_attempts=3
    )

    assert len(compacted) == 3
    assert outputs == {"decision": "approve"}


def test_a_node_is_rebriefed_for_overflow_once_and_then_fails_as_before():
    briefs: list[int] = []

    def brief() -> str:
        briefs.append(1)
        return BRIEF

    def script(prompt: str, sidp: Path) -> str:
        raise BackendInvocationError("prompt is too long", overflow=True)

    try:
        _drive(
            script,
            compact=lambda *a, **k: False,
            rebrief=brief,
            max_rephrase_attempts=0,
        )
    except BackendInvocationError:
        pass
    else:
        raise AssertionError("an overflow the rebrief cannot fix must still stop the node")
    assert briefs == [1]


def test_an_overflow_without_a_rebrief_reframes_as_before():
    prompts: list[str] = []

    def script(prompt: str, sidp: Path) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            raise BackendInvocationError("prompt is too long", overflow=True)
        return DONE

    _, warnings, _ = _drive(
        script, compact=lambda *a, **k: False, max_rephrase_attempts=1
    )

    assert len(prompts) == 2
    assert prompts[1] != prompts[0]
    assert BRIEF not in prompts[1]
    assert warnings == []


def _watchdog(node: AgentNode) -> float:
    seen: list[float] = []

    class ScriptedRunner(ladder.AgentRunner):
        def turn(self, prompt, node_id, session_id_path, model=None, **kwargs):
            seen.append(kwargs["timeout"])
            return DONE

    with patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)):
        ScriptedRunner(
            backend=FakeBackend(), resilience=AgentResilience(), clock=FakeClock()
        ).run(node, WorkflowContext(initial={}), Path("."), None)
    return seen[0]


def test_an_unbounded_node_still_waits_only_its_silence_bound():
    assert _watchdog(_node(timeout="infinity")) == float("inf")
    assert _watchdog(_node(timeout="infinity", silence=120)) == 120


def test_a_silence_bound_overrides_the_engine_floor_on_a_bounded_node():
    assert _watchdog(_node(timeout=300)) == AgentResilience().silence_timeout_s
    assert _watchdog(_node(timeout=300, silence=60)) == 60
    assert _watchdog(_node(timeout=7200, silence=60)) == 60


def test_a_silence_bound_must_be_positive():
    for bad in (0, -5):
        try:
            _node(silence=bad)
        except pydantic.ValidationError as exc:
            assert "silence" in str(exc)
        else:
            raise AssertionError(f"silence={bad} must be refused")
    assert _node(silence="30").silence == 30.0


def test_the_turn_record_keeps_the_silence_bound_of_an_unbounded_node():
    class ScriptedRunner(ladder.AgentRunner):
        def turn(self, prompt, node_id, session_id_path, model=None, **kwargs):
            return DONE

    def record(node: AgentNode) -> Any:
        root = Path(tempfile.mkdtemp())
        visit_dir = root / "turns" / "000-00001-lead"
        with patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)):
            ScriptedRunner(
                backend=FakeBackend(), resilience=AgentResilience(), clock=FakeClock()
            ).run(
                node, WorkflowContext(initial={}), Path("."), None,
                run_dir=root, visit_dir=visit_dir,
            )
        return parse_turn_record((visit_dir / "turn.json").read_text(encoding="utf-8"))

    assert record(_node(timeout="infinity", silence=120)).silence_budget_s == 120
    assert record(_node(timeout="infinity")).silence_budget_s is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
