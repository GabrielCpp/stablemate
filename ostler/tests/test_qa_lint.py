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

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

api = target("api")


def seat_record(qa: Qa, seat: str) -> dict:
    return {"seat": seat}


@scenario(target=api, mechanism="live", covers=["okf:docs/features/demo/item.md:contract"])
def item_is_emitted(qa: Qa) -> None:
    """The emitted item carries the id it was asked for."""
    record = seat_record(qa, "A1")
    payload = json.loads(qa.tool("jq").run(".", "out.json").stdout)
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
    "import_pathlib": "import pathlib\n",
    "from_pathlib": "from pathlib import Path\n",
    "read_text_method": 'qa.root.read_text(encoding="utf-8")\n',
    "write_text_method": 'qa.root.write_text("x")\n',
    "mkdir_method": "qa.root.mkdir()\n",
    "glob_method": 'qa.root.glob("*")\n',
    "bare_wait_for": 'row.wait_for(state="visible")\n',
    "bare_wait_for_url": 'qa.page.wait_for_url("**/policies")\n',
    "playwright_expect": "expect(row).to_be_visible()\n",
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


def test_pathlib_is_not_importable() -> None:
    """The ban is on constructing a path, which is what made the `open()` ban decorative."""
    problems = lint_source(BANNED_CASES["from_pathlib"])
    assert "import pathlib" in problems[0]


def test_a_filesystem_method_names_the_verb_and_the_alternative() -> None:
    problems = lint_source(BANNED_CASES["read_text_method"])
    assert ".read_text(...)" in problems[0]
    assert "qa.tool(...)" in problems[0]


def test_open_stays_available_because_it_is_how_evidence_is_written() -> None:
    """`qa.artifact(...).open("w")` is the corpus's one sanctioned write, and it survives.

    It is not a hole while `pathlib` is unimportable: the only paths a plan holds are the
    ones `qa` handed it, so the only files it can open are its own.
    """
    source = (
        "import json\n"
        "from ostler_qa import Qa, plan, scenario, target\n"
        "plan(run_id=\"qa-x\", story=\"x\")\n"
        "api = target(\"api\")\n"
        "@scenario(target=api, mechanism=\"live\", covers=[\"ac:1\"])\n"
        "def s(qa: Qa) -> None:\n"
        "    json.dump({}, qa.artifact(\"steps/x.json\", kind=\"json\").open(\"w\"))\n"
    )
    assert lint_source(source) == []


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


def test_a_settle_statement_names_the_verb_and_the_repair() -> None:
    """The whole value of the rule is the message: the fix shape has to be in it."""
    problems = lint_source(BANNED_CASES["bare_wait_for"])
    assert "`wait_for(...)`" in problems[0]
    assert "qa.eventually" in problems[0]
    # `eventually`'s own docstring spells the callable as a lambda, which this pass rejects
    # by node type — so the message has to point somewhere a plan can actually go.
    assert "lambda" in problems[0]


def test_a_playwright_assertion_is_named_by_its_root_and_not_its_last_link() -> None:
    """`to_be_visible`/`to_have_text`/… is an open vocabulary; `expect` is the closed one."""
    problems = lint_source(BANNED_CASES["playwright_expect"])
    assert "`expect(...)`" in problems[0]


def test_a_settle_is_flagged_wherever_it_sits_not_only_at_the_end() -> None:
    """Position-independence is the correction: the round's canonical crash was mid-body."""
    source = (
        'row.wait_for(state="visible")\n'
        'qa.check("the row is the one that was written", row.count() == 1)\n'
    )
    problems = lint_source(source)
    assert problems and problems[0].startswith("line 1:")


def test_a_settle_used_as_a_value_is_left_alone() -> None:
    """Handling the result is the opposite of betting the trial on it.

    `expect_response` is deliberately not caught by the `expect` root-walk either — it is a
    context manager that hands back a response, not an assertion that raises.
    """
    assert lint_source('handle = row.wait_for(state="visible")\n') == []
    assert lint_source(
        'with qa.page.expect_response("**/api/policies") as got:\n'
        '    qa.by_role("button", name="Save").click()\n'
    ) == []


def test_the_settle_that_reads_is_what_the_rule_leaves_standing() -> None:
    """A bound method satisfies `eventually`'s callable without a lambda."""
    assert lint_source('qa.eventually("the row lands", row.is_visible, covers=["ac:1"])\n') == []
