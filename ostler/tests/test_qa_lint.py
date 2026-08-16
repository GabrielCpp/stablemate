"""`ostler qa lint` — the AST allowlist a `qa_plan.py` must pass before it may import.

Every banned construct gets its own case: a blocklist proves itself by naming the thing it
caught, but an allowlist proves itself by naming everything it did *not* have to catch —
the clean-plan case is the one that would silently regress if the allowlist grew too broad.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler.qa.lint import cmd_lint, lint_source

CLEAN_PLAN = '''\
import json
from pathlib import Path

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

api = target("api")


def seat_record(qa: Qa, seat: str) -> dict:
    return {"seat": seat}


@scenario(target=api, mechanism="live", covers=["okf:docs/features/demo/item.md:contract"])
def item_is_emitted(qa: Qa) -> None:
    """The emitted item carries the id it was asked for."""
    record = seat_record(qa, "A1")
    payload = json.loads(Path(qa.root, "out.json").read_text(encoding="utf-8"))
    with qa.step("check the item"):
        qa.require(len(payload) > 0)
        qa.require(isinstance(payload, dict))
        qa.check(
            "the item is the one requested",
            payload["item"]["id"] == record["seat"],
            actual=payload["item"]["id"],
            expected=record["seat"],
            covers=["okf:docs/features/demo/item.md:contract"],
        )
'''


def test_clean_plan_passes_lint() -> None:
    assert lint_source(CLEAN_PLAN) == []


BANNED_CASES = {
    "import_subprocess": "import subprocess\n",
    "import_os": "import os\n",
    "eval_call": 'eval("1")\n',
    "exec_call": 'exec("pass")\n',
    "open_call": 'open("x")\n',
    "dunder_import": '__import__("os")\n',
    "class_escape": "().__class__\n",
    "getattr_dunder": 'getattr(str, "__globals__")\n',
    "lambda_expr": "f = lambda: 1\n",
}


@pytest.mark.parametrize("name", sorted(BANNED_CASES))
def test_banned_construct_fails_lint(name: str) -> None:
    problems = lint_source(BANNED_CASES[name])
    assert problems, f"{name} should have been rejected"
    assert problems[0].startswith("line 1:")


def test_banned_import_names_the_module() -> None:
    problems = lint_source(BANNED_CASES["import_subprocess"])
    assert "import subprocess" in problems[0]


def test_dangerous_builtin_names_the_call() -> None:
    problems = lint_source(BANNED_CASES["eval_call"])
    assert "eval(...)" in problems[0]


def test_dunder_attribute_names_the_attribute() -> None:
    problems = lint_source(BANNED_CASES["class_escape"])
    assert ".__class__" in problems[0]


def test_lambda_is_rejected_by_node_type() -> None:
    problems = lint_source(BANNED_CASES["lambda_expr"])
    assert "Lambda" in problems[0]


def test_cmd_lint_reports_missing_plan(tmp_path: Path) -> None:
    outcome = cmd_lint(tmp_path / "qa_plan.py", root=tmp_path)
    assert not outcome.ok
    assert outcome.status == "invalid"
    assert "not found" in outcome.message


def test_cmd_lint_passes_a_clean_plan(tmp_path: Path) -> None:
    plan = tmp_path / "qa_plan.py"
    plan.write_text(CLEAN_PLAN, encoding="utf-8")
    outcome = cmd_lint(plan, root=tmp_path)
    assert outcome.ok
    assert outcome.status == "passed"


def test_cmd_lint_collects_every_violation_not_just_the_first() -> None:
    plan = "import subprocess\nimport os\neval('1')\n"
    problems = lint_source(plan)
    assert len(problems) == 3
