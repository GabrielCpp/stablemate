"""Tests for `globex_book_line3`, without ever asking an agent anything."""

from __future__ import annotations

import contextlib
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

from paddock import loader
from paddock.pointer import Pointer
from paddock.registry import REGISTRY, Task
from paddock.runner import Run

DATA = Path(__file__).parents[1]
APP = DATA / "apps" / "globex"


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
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    REGISTRY.reset()
    with _tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    REGISTRY.reset()
    return module


TASK = _load("_line3_task_under_test", DATA / "tasks" / "globex_book_line3.py")


def _run(tmp_path: Path) -> Run:
    """A real `Run`, pointed at the fixture, with no agent CLI ever invoked."""
    task = Task(name="globex-book-line3", seed="globex", config=TASK.CONFIG, steps=(),
               score=TASK.score, module="globex_book_line3")
    seed = Pointer(name="globex", repo_dir="globex", sha256="0" * 64, bytes=0)
    return Run(
        task=task, label="test", stage=tmp_path / "stage", repo=APP,
        scratch=tmp_path / "scratch", config=DATA / "configs" / "opencode.toml",
        data_dir=DATA, store=tmp_path / "store", seed=seed, echo=False,
    )




def test_the_module_registers_under_loader_load_all() -> None:
    """A duplicate task name or an import-time error would fail every task, not just this one — `loader.load_all` is the same entry point `paddock list` and every gate use."""
    tasks = loader.load_all(DATA)
    names = {item.name for item in tasks}
    assert "globex-book-line3" in names


def test_the_rubric_file_exists_beside_the_other_rubrics() -> None:
    assert (DATA / "rubric-line3.md").is_file()




def test_arrange_builds_one_tree_per_node_and_arm_with_no_app(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)

    ledger = run.stage / "artifacts" / "trials" / "trials.json"
    assert ledger.is_file()
    trials = run.read_json(ledger)
    assert len(trials) == len(TASK.NODES) * len(TASK.ARMS)

    for trial in trials:
        tree = TASK._tree_dir(run, trial["id"])
        assert (tree / "docs").is_dir()
        assert not (tree / "app").exists()
        assert not (tree / ".agents").exists()
        for name in ("agents.yml", ".agents.yml", "ostler.yml", "ostler.yaml"):
            assert not (tree / name).exists()




def _cited_paths(tree_docs_root: Path, slug: str) -> set[str]:
    from ostler.api import Ostler

    root = tree_docs_root.parent
    rows = Ostler(root).query("surfaces-referenced-by-story", slug)
    return {str(row["path"]) for row in rows}


def test_control_leaves_the_original_citation_intact(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    for node in TASK.NODES:
        tree = TASK._tree_dir(run, TASK._slug(node, "control"))
        cited = _cited_paths(tree / "docs", node.citing_story)
        assert f"docs/{node.path}" in cited


def test_absence_removes_the_link_and_names_no_replacement(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    for node in TASK.NODES:
        tree = TASK._tree_dir(run, TASK._slug(node, "absence"))
        cited = _cited_paths(tree / "docs", node.citing_story)
        assert f"docs/{node.path}" not in cited
        story_file = TASK._story_file(tree / "docs", node.citing_story)
        text = story_file.read_text(encoding="utf-8")
        original = APP / "docs" / "epics" / TASK.EPIC / "stories" / node.citing_story / "story.md"
        match = TASK._find_node_link(
            original.read_text(encoding="utf-8"), original, (APP / "docs" / node.path).resolve(),
        )
        assert match is not None
        assert match.group(1) in text


def test_substitution_moves_the_citation_to_the_other_story(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    for node in TASK.NODES:
        tree = TASK._tree_dir(run, TASK._slug(node, "substitution"))
        docs_root = tree / "docs"
        citing_cited = _cited_paths(docs_root, node.citing_story)
        other_cited = _cited_paths(docs_root, node.other_story)

        assert f"docs/{node.path}" not in citing_cited, (
            "the citing story must no longer cite the real node"
        )
        assert f"docs/{node.decoy}" in citing_cited, (
            "the citing story's link must now point at the decoy"
        )
        assert f"docs/{node.path}" in other_cited, (
            "the other story must now cite the real node instead"
        )


def test_every_node_has_a_distinct_decoy_no_story_originally_cites() -> None:
    """The decoy has to be a clean substitution target: real, and uncited by any story in the unperturbed book, or `substitution` would silently create a second citation."""
    all_cited: set[str] = set()
    for node in TASK.NODES:
        all_cited |= _cited_paths(APP / "docs", node.citing_story)
    for node in TASK.NODES:
        assert (APP / "docs" / node.decoy).is_file()
        assert f"docs/{node.decoy}" not in all_cited
