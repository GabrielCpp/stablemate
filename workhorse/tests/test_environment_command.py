"""`environment` compares two init events, and names what the engine turn does not load."""
from __future__ import annotations

from workhorse.cli.environment import compare

REFUSED = ("Workflow", "Monitor")
DELEGATES = ("lookup", "worker")


def _init(**lists: list[object]) -> dict[str, list[object]]:
    base: dict[str, list[object]] = {
        "tools": ["Read", "Bash"],
        "skills": ["a", "b"],
        "agents": ["general-purpose"],
        "plugins": [{"name": "p", "path": "/x"}],
        "slash_commands": ["/c"],
        "mcp_servers": [{"name": "m", "status": "connected"}],
    }
    return {**base, **lists}


def test_two_identical_inits_are_the_same_and_exit_0() -> None:
    lines, code = compare(_init(), _init(), REFUSED, DELEGATES)
    assert code == 0
    assert lines[0] == "tools: plain 2, engine 2; same"
    assert lines[-1] == "result: the engine turn loads everything the plain session loads"
    assert len(lines) == 7


def test_a_skill_the_engine_turn_lacks_is_named_and_exits_1() -> None:
    lines, code = compare(_init(), _init(skills=["a"]), REFUSED, DELEGATES)
    assert code == 1
    assert "skills: plain 2, engine 1; missing from the engine turn: b" in lines
    assert lines[-1] == "result: the engine turn misses 1 names"


def test_a_tool_the_engine_refuses_is_printed_and_does_not_count() -> None:
    plain = _init(tools=["Read", "Workflow", "Monitor"])
    lines, code = compare(plain, _init(tools=["Read"]), REFUSED, DELEGATES)
    assert code == 0
    assert lines[0] == "tools: plain 3, engine 1; same; refused by the engine: Workflow, Monitor"


def test_a_delegate_the_engine_adds_is_printed_and_does_not_count() -> None:
    lines, code = compare(_init(), _init(agents=["general-purpose", "lookup"]), REFUSED, DELEGATES)
    assert code == 0
    assert "agents: plain 1, engine 2; same; added by the engine: lookup" in lines


def test_a_name_the_engine_turn_has_extra_is_named_without_failing() -> None:
    lines, code = compare(_init(), _init(skills=["a", "b", "z"]), REFUSED, DELEGATES)
    assert code == 0
    assert "skills: plain 2, engine 3; extra in the engine turn: z" in lines
