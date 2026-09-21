"""Every frozen `qa_plan.py` in the corpus must pass the lint that ships today."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from ostler.qa.lint import cmd_lint

DATA = Path(__file__).parents[1]
PLANS = sorted((DATA / "apps").glob("*/docs/specs/*/qa_plan.py"))


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does when it loads a task."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load(name: str, path: Path) -> ModuleType:
    """Load a task-dir module by file, the way `paddock.loader` loads a task."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    with _tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


_frozenapp = _load("_frozenapp", DATA / "tasks" / "_frozenapp.py")


def _plan_id(plan: Path) -> str:
    return f"{plan.parents[3].name}/{plan.parent.name}"


def test_the_corpus_has_plans_to_lint() -> None:
    """A glob that matches nothing passes every parametrized test under it, silently."""
    assert PLANS, f"no frozen qa_plan.py found under {DATA / 'apps'}"


@pytest.mark.parametrize("plan", PLANS, ids=_plan_id)
def test_a_frozen_plan_passes_the_lint_that_ships_today(plan: Path) -> None:
    """Lint through the shipping entry point, so the app's own declarations apply."""
    app = plan.parents[3]
    outcome = cmd_lint(plan, root=app)
    assert outcome.ok, outcome.message


def _story_file(root: Path, story: str) -> Path:
    """The story the spec was planned from, wherever the app filed its epics."""
    found = sorted(root.glob(f"docs/epics/*/stories/{story}/story.md"))
    assert len(found) == 1, f"{story}: expected one story.md, found {found}"
    return found[0]


@pytest.mark.parametrize("plan", PLANS, ids=_plan_id)
def test_a_frozen_plan_validates_against_a_trial_packet(plan: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind every `covers=` id against the packet a real trial would hand the plan."""
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs
    from ostler.qa.context import build_context  # noqa: PLC0415

    monkeypatch.setenv("STABLEMATE_CONFIG", str(DATA / "configs" / "opencode.toml"))

    app = plan.parents[3]
    story = plan.parent.name
    dest = _frozenapp.materialize(app, story, tmp_path / app.name)

    spec = dest / "docs" / "specs" / story
    context = build_context(
        dest,
        base="HEAD",
        head="WORKTREE",
        source_roots={app.name: [str(dest)]},
        story_file=_story_file(dest, story),
    )
    (spec / "qa-okf-context.json").write_text(json.dumps(context, indent=2), encoding="utf-8")

    okf = Ostler(dest)
    validated = okf.qa_validate(spec / "qa_plan.py", spec=spec)
    assert validated.ok, validated.data
