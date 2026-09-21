"""What `check_fixtures.py` can see that a run cannot."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_fixtures.py"

PLAN = '''"""A plan."""

from ostler_qa import plan, target

plan(run_id="qa-story", story="story")
thing = target("thing", driver="python")
'''


@pytest.fixture(scope="module")
def guard() -> Any:
    spec = importlib.util.spec_from_file_location("check_fixtures", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _app(root: Path, agents: str, *, plan: str = PLAN) -> Path:
    """One benchmark-app tree: an `agents.yml`, a story, and whatever fixtures are asked for."""
    specs = root / "docs" / "specs"
    (specs / "story").mkdir(parents=True)
    (root / "agents.yml").write_text(agents, encoding="utf-8")
    (specs / "story" / "qa_plan.py").write_text(plan, encoding="utf-8")
    return root


def test_a_fixture_naming_a_tool_the_repo_never_opted_into_is_reported(
    guard: Any, tmp_path: Path
) -> None:
    """The containment property: a fixture is an invocation of an admitted tool, not a door."""
    app = _app(
        tmp_path / "acme",
        "qa:\n"
        "  tools:\n"
        "    - python3\n"
        "  fixtures:\n"
        "    seeded_accounts:\n"
        "      tool: node\n"
        "      args: ['auth/seed.mjs']\n"
        "      provides: three identities in the auth emulator\n",
    )
    problems = guard._check_app(app)
    assert len(problems) == 1
    assert "has not opted into" in problems[0]


def test_a_plan_calling_an_undeclared_fixture_is_reported(guard: Any, tmp_path: Path) -> None:
    """Today this fails the run — after the app booted, and reported as a blocked scenario."""
    app = _app(
        tmp_path / "acme",
        "qa:\n  tools:\n    - python3\n",
        plan=PLAN + '\nqa.fixture("seeded_accounts")\n',
    )
    problems = guard._check_app(app)
    assert len(problems) == 1
    assert "qa.fixture('seeded_accounts')" in problems[0]
    assert "(none declared)" in problems[0]


def test_a_plan_calling_a_declared_fixture_is_clean(guard: Any, tmp_path: Path) -> None:
    app = _app(
        tmp_path / "acme",
        "qa:\n"
        "  tools:\n"
        "    - node\n"
        "  fixtures:\n"
        "    seeded_accounts:\n"
        "      tool: node\n"
        "      args: ['auth/seed.mjs']\n"
        "      provides: three identities in the auth emulator\n",
        plan=PLAN + '\nqa.fixture("seeded_accounts")\n',
    )
    assert guard._check_app(app) == []


def test_a_story_naming_a_fixture_nobody_declared_is_reported(guard: Any, tmp_path: Path) -> None:
    """Nothing fails on this at a run: the QA planner is told the story declared it, goes looking for the declaration, does not find it, and writes one — spending agent turns on an `agents.yml` entry instead of reporting a story that names a fixture that is not there."""
    app = _app(tmp_path / "acme", "qa:\n  tools:\n    - python3\n")
    (app / "docs" / "specs" / "story" / "plan-context.json").write_text(
        json.dumps({"qa_stack": {"fixtures": ["seeded_accounts"]}}), encoding="utf-8"
    )

    problems = guard._check_app(app)

    assert len(problems) == 1
    assert "declares fixture 'seeded_accounts'" in problems[0]


def test_prose_in_a_story_fixture_list_is_not_held_to_a_declaration(
    guard: Any, tmp_path: Path
) -> None:
    """Every frozen story in the corpus describes its arrangements in English there."""
    app = _app(
        tmp_path / "acme",
        "qa:\n  tools:\n    - python3\n",
    )
    (app / "docs" / "specs" / "story" / "plan-context.json").write_text(
        json.dumps({"qa_stack": {"fixtures": ["an empty desk (DELETE /api/claims)"]}}),
        encoding="utf-8",
    )

    assert guard._check_app(app) == []


def test_a_computed_fixture_name_is_not_read_as_a_fragment(guard: Any, tmp_path: Path) -> None:
    """A name built at runtime claims nothing static, so this pass sees none rather than half."""
    app = _app(
        tmp_path / "acme",
        "qa:\n  tools:\n    - python3\n",
        plan=PLAN + '\nqa.fixture("seeded_" + "accounts")\n',
    )
    assert guard._check_app(app) == []


def test_a_tree_with_no_specs_is_not_an_app_this_guard_judges(guard: Any, tmp_path: Path) -> None:
    root = tmp_path / "acme"
    root.mkdir()
    (root / "agents.yml").write_text("qa:\n  tools:\n    - python3\n", encoding="utf-8")
    assert guard._check_app(root) == []
