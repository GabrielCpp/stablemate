"""The expense-split replay's two contracts: what a round plans, and what a rewind undoes.

Neither is checkable by running the task — a real trial is a forty-minute agent run behind
a docker stack — and both are exactly the kind of thing that breaks silently. A pin list
that has drifted still runs; it just replays a different commit. A rewind that deletes one
file too many still runs; it just measures a flow being handed less than it was handed
historically, which reads as the loop getting worse.
"""

from __future__ import annotations

import contextlib
import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from paddock import loader, registry
from paddock.pointer import Pointer
from paddock.runner import Run

BENCHMARKS = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does."""
    saved = sys.path[:]
    sys.path.insert(0, str(BENCHMARKS / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load() -> ModuleType:
    path = BENCHMARKS / "tasks" / "expense_split.py"
    spec = importlib.util.spec_from_file_location("expense_split", path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    with _tasks_dir_on_path():
        # The declaration calls in the module body write to the process-wide registry the
        # loader owns; resetting first is what lets this import happen beside any other.
        registry.REGISTRY.reset()
        sys.modules["expense_split"] = module
        spec.loader.exec_module(module)
    return module


task_module = _load()


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def make_run(tmp_path: Path, **params: str) -> Run:
    """A `Run` carrying nothing but params — every function under test reads only those."""
    return Run(
        task=loader.load_path(BENCHMARKS / "tasks" / "expense_split.py"),
        label="t1",
        stage=tmp_path / "stage",
        repo=tmp_path / "stage" / "expense-split",
        scratch=tmp_path / "scratch",
        config=tmp_path / "config.toml",
        data_dir=BENCHMARKS,
        store=tmp_path / "store",
        seed=Pointer(name="expense-split", repo_dir="expense-split", sha256="0" * 64, bytes=1),
        params=params,
    )


def test_every_story_is_pinned_once_on_both_flows() -> None:
    stories = [pin.story for pin in task_module.PINS]
    assert stories == sorted(set(stories), key=stories.index), "a story is pinned twice"
    assert len(stories) == 5
    for pin in task_module.PINS:
        # A pin that lost half its pair still runs and replays the wrong flow's state.
        assert pin.commit("qa") and pin.commit("docs")


def test_a_round_pairs_every_pinned_story_with_every_flow(tmp_path: Path) -> None:
    plan = task_module.plan_round(make_run(tmp_path))
    assert len(plan) == len(task_module.PINS) * len(task_module.FLOWS)
    # Stories outermost, so a round interrupted halfway has finished stories rather than
    # half a flow of every story.
    assert [flow for _, flow in plan[:2]] == ["qa", "docs"]


def test_params_narrow_a_round_and_a_typo_is_refused(tmp_path: Path) -> None:
    plan = task_module.plan_round(make_run(tmp_path, stories="expense-list", flows="qa"))
    assert [(pin.story, flow) for pin, flow in plan] == [("expense-list", "qa")]

    with pytest.raises(task_module.sm.TrialError, match="no pin for"):
        task_module.plan_round(make_run(tmp_path, stories="expense-lists"))
    with pytest.raises(task_module.sm.TrialError, match="known flows"):
        task_module.plan_round(make_run(tmp_path, flows="review"))


def test_the_qa_rewind_removes_the_flows_outputs_and_nothing_else(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    spec = repo / "docs" / "specs" / "expense-list"
    spec.mkdir(parents=True)
    (spec / "story.md").write_text("the story", encoding="utf-8")
    (spec / "implementation-plan.md").write_text("the plan", encoding="utf-8")
    (spec / "qa-plan.yml").write_text("scenarios: []", encoding="utf-8")
    (spec / "qa-evidence.json").write_text("{}", encoding="utf-8")
    (spec / "qa").mkdir()
    (spec / "qa" / "shot.png").write_bytes(b"")

    task_module.rewind(repo, task_module.PINS[3], "qa")

    # The story and the plan are what the flow is *entered* with; everything the flow
    # writes has to be gone, or the trial measures a repair of its own last answer.
    assert sorted(p.name for p in spec.iterdir()) == ["implementation-plan.md", "story.md"]


def test_the_qa_rewind_refuses_a_pin_whose_spec_dir_is_absent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    with pytest.raises(task_module.sm.TrialError, match="still right"):
        task_module.rewind(repo, task_module.PINS[0], "qa")


def test_the_docs_rewind_leaves_the_book_one_story_behind(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    features = repo / "docs" / "features"
    features.mkdir(parents=True)
    git("init", "--quiet", "--initial-branch", "main", cwd=repo)
    git("config", "user.email", "benchmark@example.com", cwd=repo)
    git("config", "user.name", "stablemate benchmark", cwd=repo)
    (features / "group.md").write_text("group", encoding="utf-8")
    git("add", "--all", cwd=repo)
    git("commit", "--quiet", "-m", "group-membership", cwd=repo)
    (features / "expense.md").write_text("expense", encoding="utf-8")
    git("add", "--all", cwd=repo)
    git("commit", "--quiet", "-m", "expense-record", cwd=repo)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), check=True, capture_output=True, text=True
    ).stdout.strip()

    task_module.rewind(repo, task_module.Pin(story="expense-record", qa=head, docs=head), "docs")

    # The book as it stood *before* this story landed: the real historical input, and one
    # story behind rather than empty — a book rewound further is missing entries outside
    # this story's obligations, which is a different complaint for a reviewer to make.
    assert sorted(p.name for p in features.iterdir()) == ["group.md"]


def test_the_backfill_gives_a_predating_story_the_dependencies_section(tmp_path: Path) -> None:
    """The bundle was captured before `## Dependencies` was a required story section.

    Without the backfill every pin stops at the first node — "story.md is still a bare
    scaffold" — on both flows, and the fixture measures nothing.
    """
    story_md = tmp_path / "docs" / "epics" / "0001-groups" / "stories" / "create-group" / "story.md"
    story_md.parent.mkdir(parents=True)
    story_md.write_text(
        "---\nslug: create-group\n---\n# Story: Create a Group\n\n## Context\n\nprose.\n",
        encoding="utf-8",
    )

    task_module.backfill_story_sections(tmp_path)

    written = story_md.read_text(encoding="utf-8")
    assert "## Dependencies\n\n(none)\n" in written
    # Ahead of the prose, and the prose itself untouched — the trial is entered with the
    # story the original run was entered with, plus a heading that reads as no edge.
    assert written.index("## Dependencies") < written.index("## Context")
    assert written.endswith("## Context\n\nprose.\n")


def test_the_backfill_leaves_a_story_that_already_declares_dependencies_alone(
    tmp_path: Path,
) -> None:
    story_md = tmp_path / "docs" / "epics" / "0001-groups" / "stories" / "create-group" / "story.md"
    story_md.parent.mkdir(parents=True)
    # A real edge, which a second `(none)` section would sit above and contradict.
    before = "# Story\n\n## Dependencies\n\n- Blocked by: group-membership\n\n## Context\n\nx.\n"
    story_md.write_text(before, encoding="utf-8")

    task_module.backfill_story_sections(tmp_path)

    assert story_md.read_text(encoding="utf-8") == before
