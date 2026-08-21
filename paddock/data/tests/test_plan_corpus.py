"""Every frozen `qa_plan.py` in the corpus must pass the lint that ships today.

`ostler.qa.lint` is an allowlist, and an allowlist tightens: a module leaves
`ALLOWED_IMPORT_MODULES`, a verb joins the rejected set, and a plan that was legal when
it was frozen stops being legal without anyone touching the fixture. What that costs is
not a test failure — it is a *round*. The plan refuses at trial time, the story arrives
as `inconclusive`, and the scoreboard reports a QA lane that detected nothing when what
actually happened is that the benchmark's own input went stale.

The lint pass is the cheap half of that guard: a static pass over the tracked tree, no
materialization, no config, so it runs in the same second as the rest of the suite and
fails on the commit that tightened the rule rather than on the next scored round.

The validate pass below is the expensive half, and it mints the packet the way a *trial*
mints it rather than the way a convenient test would: `story_file=` and `source_roots=`
are both passed, because the QA lane passes them. Leaving the story file out is not a
smaller version of the same check — it drops every acceptance criterion out of the packet,
and a plan binding none of them validates here and refuses at trial time, which is the
fixture bug this file exists to catch wearing a green test's clothes.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from ostler.qa.lint import lint_source

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
    problems = lint_source(plan.read_text(encoding="utf-8"), filename=str(plan))
    assert not problems, "\n".join(problems)


def _story_file(root: Path, story: str) -> Path:
    """The story the spec was planned from, wherever the app filed its epics."""
    found = sorted(root.glob(f"docs/epics/*/stories/{story}/story.md"))
    assert len(found) == 1, f"{story}: expected one story.md, found {found}"
    return found[0]


@pytest.mark.parametrize("plan", PLANS, ids=_plan_id)
def test_a_frozen_plan_validates_against_a_trial_packet(plan: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind every `covers=` id against the packet a real trial would hand the plan.

    `validate` preflights the opted-in QA tools, so the task config is pinned here for the
    same reason `sm.pin_config` pins it for a round: `docker`/`python3` must resolve out of
    the benchmark's own config rather than out of whatever this machine has under
    `~/.config/stablemate`.
    """
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
