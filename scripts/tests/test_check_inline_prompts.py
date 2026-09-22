"""What `check_inline_prompts.py` refuses, and the shapes it must not refuse."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_inline_prompts.py"

GOOD = '''
class Drains(Workflow):
    def drain(self) -> Transition:
        return Done(
            self.agent(
                "# Fix the findings\\n\\nFix {{ findings }}, each in a sub agent.\\n",
                label="fix-findings",
                returns=Fixed,
                args={"findings": items},
            )
        )
'''


@pytest.fixture(scope="module")
def guard() -> Any:
    spec = importlib.util.spec_from_file_location("check_inline_prompts", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _problems(guard: Any, source: str, rel: str = "workflows/src/w/main/flow.py") -> list[str]:
    sites, unreadable = guard._read(rel, source)
    return [*unreadable, *guard.site_problems(sites)]


def test_the_walker_finds_the_turn_it_is_written_to_bound(guard: Any) -> None:
    """A guard that matches nothing passes every tree, including the one it was written for."""
    sites, unreadable = guard._read("workflows/src/w/main/flow.py", GOOD)

    assert unreadable == []
    assert [s.label for s in sites] == ["fix-findings"]


def test_a_turn_within_bounds_is_left_alone(guard: Any) -> None:
    assert _problems(guard, GOOD) == []


def test_a_prompt_file_path_is_not_an_inline_turn(guard: Any) -> None:
    source = 'self.agent("main/prompts/fix.md", returns=Fixed)\n'

    assert guard._read("w/flow.py", source) == ([], [])


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('self.agent(f"# Fix\\n{x}", label="fix")', "not a literal string"),
        ('self.agent("# Fix\\nDo it.", label=name)', "the label is not a literal"),
        ('self.agent("# Fix\\nDo it.", label="Fix Findings")', "is not a node id"),
        ('self.agent("Do it.", label="fix")', "first line is not a heading"),
        ('self.agent("main/prompts/fix.md", label="fix")', "`label=` was typed onto"),
        ('self.agent("# Fix\\n{% for x in %}", label="fix")', "not valid Jinja"),
        ('self.agent("# Fix\\n{{ skill_file(\\"x\\") }}", label="fix")', "only a prompt file"),
        ('self.agent("# Fix\\n{% include \\"p.md\\" %}", label="fix")', "length bound is fiction"),
        ('self.agent("# Fix\\n" + "x\\n" * 40, label="fix")', "not a literal string"),
    ],
)
def test_a_turn_no_sweep_could_read_is_refused(guard: Any, source: str, expected: str) -> None:
    problems = _problems(guard, source)

    assert problems, source
    assert any(expected in p for p in problems), problems


def test_a_body_over_the_bounds_is_refused(guard: Any) -> None:
    body = "# Fix\\n" + "line\\n" * 60
    problems = _problems(guard, f'self.agent("{body}", label="fix")')

    assert any("over the 40-line bound" in p for p in problems), problems


def test_two_turns_sharing_a_label_share_a_run_directory(guard: Any) -> None:
    source = (
        'self.agent("# One\\nDo it.", label="fix")\n'
        'self.agent("# Two\\nDo it.", label="fix")\n'
    )

    assert any("two turns are labelled" in p for p in _problems(guard, source)), source


def test_the_coder_workflow_takes_no_inline_turn(guard: Any) -> None:
    rel = "workflows/src/workhorse_workflows/coder/dev/flow.py"

    problems = _problems(guard, GOOD, rel=rel)

    assert any("swept for stack names" in p for p in problems), problems


def test_a_test_file_is_a_fixture_not_a_turn(guard: Any) -> None:
    """The bounds exist so the repo's prompt sweeps can read a turn, and no sweep reads a test."""
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(REPO / "workhorse" / "tests" / "test_inline_prompt.py"),
            "content": 'self.agent(text, label=label)\n',
        },
    }

    assert guard.hook_decision(payload) is None


def test_the_hook_refuses_the_write_before_the_file_exists(guard: Any) -> None:
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(REPO / "workflows" / "src" / "w" / "flow.py"),
            "content": 'self.agent("Do it.", label="fix")\n',
        },
    }

    reason = guard.hook_decision(payload)

    assert reason is not None
    assert "first line is not a heading" in reason


def test_the_hook_reads_an_indented_edit_fragment(guard: Any) -> None:
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(REPO / "workflows" / "src" / "w" / "flow.py"),
            "new_string": '        self.agent("Do it.", label="fix")\n',
        },
    }

    assert guard.hook_decision(payload) is not None


def test_the_hook_ignores_what_it_cannot_parse(guard: Any) -> None:
    """Inconclusive lets it through, the same posture `check_no_shell` documents."""
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(REPO / "workflows" / "src" / "w" / "flow.py"),
            "new_string": "        elif dotted ==",
        },
    }

    assert guard.hook_decision(payload) is None


def test_the_tracked_sweep_passes_on_this_repo(guard: Any) -> None:
    assert guard.check_inline_prompts() == []
