"""Tests for `globex_book_disagree`, without ever asking an agent anything or running docker."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

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


TASK = _load("_disagree_task_under_test", DATA / "tasks" / "globex_book_disagree.py")


def _run(tmp_path: Path) -> Run:
    """A real `Run`, pointed at the fixture, with no agent CLI and no docker ever invoked."""
    task = Task(name="globex-book-disagree", seed="globex", config=TASK.CONFIG, steps=(),
               score=TASK.score, module="globex_book_disagree")
    seed = Pointer(name="globex", repo_dir="globex", sha256="0" * 64, bytes=0)
    return Run(
        task=task, label="test", stage=tmp_path / "stage", repo=APP,
        scratch=tmp_path / "scratch", config=DATA / "configs" / "opencode.toml",
        data_dir=DATA, store=tmp_path / "store", seed=seed, echo=False,
    )


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


_CODE_BULLET = re.compile(r"^- code: `([^`]+)` @([0-9a-f]{12})$", re.MULTILINE)


def _code_digests(tree: Path) -> list[tuple[str, str, str]]:
    """Every `- code:` bullet under `tree/docs`, recomputed independently against disk."""
    rows: list[tuple[str, str, str]] = []
    for page in sorted((tree / "docs").rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        for match in _CODE_BULLET.finditer(text):
            cited = match.group(1).split("::", 1)[0]
            stated = match.group(2)
            actual = _digest((tree / cited).read_bytes())
            rows.append((cited, stated, actual))
    return rows


def _files_containing(root: Path, needle: str) -> list[Path]:
    """Every file anywhere under `root` whose text contains `needle` — a whole-subtree sweep, not a check scoped to the files a test's author had in mind."""
    return [
        path for path in sorted(root.rglob("*"))
        if path.is_file() and needle in path.read_text(encoding="utf-8", errors="ignore")
    ]




def test_the_module_registers_under_loader_load_all() -> None:
    """A duplicate task name or an import-time error would fail every task, not just this one — `loader.load_all` is the same entry point `paddock list` and every gate use."""
    tasks = loader.load_all(DATA)
    names = {item.name for item in tasks}
    assert "globex-book-disagree" in names


def test_the_rubric_file_exists_beside_the_other_rubrics() -> None:
    assert (DATA / "rubric-disagree.md").is_file()




def test_the_seed_index_html_actually_matches_the_digest_the_book_cites() -> None:
    """The whole discriminator rests on this holding for the seed as shipped — if `index.html` or the book's citation ever drifts, this catches it before a trial does."""
    data = (APP / TASK.TARGET_APP).read_bytes()
    assert _digest(data) == "ebed722d64ce"
    text = (APP / "docs" / TASK.TARGET_DOC).read_text(encoding="utf-8")
    assert "@ebed722d64ce" in text


def test_the_rubric_states_the_same_digest_the_book_and_the_file_agree_on() -> None:
    """The digest is stated in three documents — the book, this test, and the rubric prose the judge is handed."""
    actual = _digest((APP / TASK.TARGET_APP).read_bytes())
    rubric = (DATA / "rubric-disagree.md").read_text(encoding="utf-8")
    stated = set(re.findall(r"@([0-9a-f]{12})", rubric))
    assert stated == {actual}




def test_arrange_builds_one_tree_per_arm_with_app_docs_and_compose(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)

    ledger = run.stage / "artifacts" / "trials" / "trials.json"
    assert ledger.is_file()
    trials = run.read_json(ledger)
    assert len(trials) == len(TASK.ARMS)
    assert len(trials) == 3
    assert {t["arm"] for t in trials} == set(TASK.ARMS)

    for trial in trials:
        tree = TASK._tree_dir(run, trial["id"])
        assert (tree / "docs").is_dir()
        assert (tree / "app").is_dir()
        assert (tree / "compose.yml").is_file()

        mcp_path = tree / ".mcp.json"
        assert mcp_path.is_file()
        mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
        assert "playwright" in mcp["mcpServers"]




def test_agree_leaves_the_app_file_and_the_book_bullets_byte_identical(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "agree")

    app_bytes = (tree / TASK.TARGET_APP).read_bytes()
    assert app_bytes == (APP / TASK.TARGET_APP).read_bytes()
    assert _digest(app_bytes) == "ebed722d64ce"

    doc_text = (tree / "docs" / TASK.TARGET_DOC).read_text(encoding="utf-8")
    assert doc_text == (APP / "docs" / TASK.TARGET_DOC).read_text(encoding="utf-8")
    assert doc_text.count(f"- name: {TASK.OBSERVED_TEXT}") == 2
    assert "@ebed722d64ce" in doc_text


def test_agree_the_mutated_text_is_nowhere_under_the_whole_tree(tmp_path: Path) -> None:
    """Whole-tree, not scoped to the two `- name:` bullets — the mutated string must not have leaked in anywhere, on the one arm where nothing should have moved at all."""
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "agree")
    assert _files_containing(tree, TASK.MUTATED_TEXT) == []


def test_agree_every_cited_digest_matches_the_file_it_names_whole_tree(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "agree")
    rows = _code_digests(tree)
    assert rows, "no `- code:` bullets found under docs/ — the sweep found nothing to check"
    mismatches = [row for row in rows if row[1] != row[2]]
    assert mismatches == []




def test_app_wrong_edits_only_index_html_and_the_book_is_untouched(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "app-wrong")

    app_text = (tree / TASK.TARGET_APP).read_text(encoding="utf-8")
    assert TASK.MUTATED_TEXT in app_text
    assert TASK.OBSERVED_TEXT not in app_text
    assert 'id="new-widget-link"' in app_text

    doc_text = (tree / "docs" / TASK.TARGET_DOC).read_text(encoding="utf-8")
    assert doc_text == (APP / "docs" / TASK.TARGET_DOC).read_text(encoding="utf-8")
    assert doc_text.count(f"- name: {TASK.OBSERVED_TEXT}") == 2
    assert "@ebed722d64ce" in doc_text


def test_app_wrong_makes_the_cited_digest_stale(tmp_path: Path) -> None:
    """The discriminator itself: after this arm's edit, the digest the book still cites no longer matches the file it names — the book was correct and is now stale evidence of the app, not the other way around."""
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "app-wrong")
    app_bytes = (tree / TASK.TARGET_APP).read_bytes()
    assert _digest(app_bytes) != "ebed722d64ce"


def test_app_wrong_does_not_touch_any_other_file_under_docs(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "app-wrong")
    for page in sorted((tree / "docs").rglob("*.md")):
        rel = page.relative_to(tree / "docs").as_posix()
        original = (APP / "docs" / rel).read_text(encoding="utf-8")
        assert page.read_text(encoding="utf-8") == original, f"{rel} was touched"


def test_app_wrong_the_mutated_text_is_under_app_and_nowhere_under_docs_whole_tree(
    tmp_path: Path,
) -> None:
    """Whole-tree sweep of both subtrees, not the one file each side happens to name — `app/` must carry the mutation somewhere, `docs/` must carry it nowhere at all."""
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "app-wrong")
    assert _files_containing(tree / "app", TASK.MUTATED_TEXT) != []
    assert _files_containing(tree / "docs", TASK.MUTATED_TEXT) == []


def test_app_wrong_the_only_file_with_a_mismatched_digest_is_index_html(
    tmp_path: Path,
) -> None:
    """The discriminator this whole probe exists to pin: whole-tree over every `- code:` bullet under `docs/`, not just the bullets naming `index.html`."""
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "app-wrong")
    rows = _code_digests(tree)
    mismatches = [row for row in rows if row[1] != row[2]]
    assert {row[0] for row in mismatches} == {TASK.TARGET_APP}
    assert len(mismatches) == 2




def test_book_wrong_edits_only_the_two_name_bullets_and_the_app_is_untouched(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "book-wrong")

    doc_text = (tree / "docs" / TASK.TARGET_DOC).read_text(encoding="utf-8")
    assert doc_text.count(f"- name: {TASK.MUTATED_TEXT}") == 2
    assert f"- name: {TASK.OBSERVED_TEXT}" not in doc_text
    assert "@ebed722d64ce" in doc_text

    app_bytes = (tree / TASK.TARGET_APP).read_bytes()
    assert app_bytes == (APP / TASK.TARGET_APP).read_bytes()


def test_book_wrong_leaves_the_cited_digest_valid(tmp_path: Path) -> None:
    """The discriminator's other half: the app never changed, so the digest the book still cites keeps matching it — the app is correct, the book's own prose is not."""
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "book-wrong")
    app_bytes = (tree / TASK.TARGET_APP).read_bytes()
    assert _digest(app_bytes) == "ebed722d64ce"


def test_book_wrong_does_not_touch_any_file_under_app(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "book-wrong")
    for path in sorted((tree / "app").rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(tree / "app").as_posix()
        original = (APP / "app" / rel).read_bytes()
        assert path.read_bytes() == original, f"app/{rel} was touched"


def test_book_wrong_touches_only_widget_list_md_under_docs(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "book-wrong")
    for page in sorted((tree / "docs").rglob("*.md")):
        rel = page.relative_to(tree / "docs").as_posix()
        original = (APP / "docs" / rel).read_text(encoding="utf-8")
        text = page.read_text(encoding="utf-8")
        if rel == TASK.TARGET_DOC:
            assert text != original
        else:
            assert text == original, f"{rel} was touched"


def test_book_wrong_the_mutated_text_is_under_docs_and_nowhere_under_app_whole_tree(
    tmp_path: Path,
) -> None:
    """Whole-tree sweep of both subtrees, mirroring `app-wrong`'s: `docs/` must carry the mutation somewhere, `app/` must carry it nowhere at all."""
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "book-wrong")
    assert _files_containing(tree / "docs", TASK.MUTATED_TEXT) != []
    assert _files_containing(tree / "app", TASK.MUTATED_TEXT) == []


def test_book_wrong_every_cited_digest_still_matches_the_file_it_names_whole_tree(
    tmp_path: Path,
) -> None:
    """The discriminator's other half, swept whole-tree: the book's prose moved, but not one `- code:` bullet's digest under `docs/` should now disagree with the file on disk."""
    run = _run(tmp_path)
    TASK.arrange(run)
    tree = TASK._tree_dir(run, "book-wrong")
    rows = _code_digests(tree)
    assert rows, "no `- code:` bullets found under docs/ — the sweep found nothing to check"
    mismatches = [row for row in rows if row[1] != row[2]]
    assert mismatches == []




def test_perturb_app_wrong_refuses_when_the_anchor_is_not_found(tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>\n", encoding="utf-8")
    with pytest.raises(TASK.TrialError, match="new-widget-link"):
        TASK._perturb_app_wrong(static)


def test_perturb_book_wrong_refuses_when_the_name_bullets_are_not_found(tmp_path: Path) -> None:
    docs = tmp_path / "docs" / "features" / "web-app" / "gui" / "screens"
    docs.mkdir(parents=True)
    (docs / "widget-list.md").write_text("# nothing here\n", encoding="utf-8")
    with pytest.raises(TASK.TrialError, match="name"):
        TASK._perturb_book_wrong(tmp_path / "docs")


def test_perturb_rejects_an_unknown_arm(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    with pytest.raises(TASK.TrialError, match="arm"):
        TASK._perturb(tree, "not-a-real-arm")




def test_appraise_caps_a_level_two_verdict_whose_citation_does_not_resolve(tmp_path: Path) -> None:
    text = json.dumps({
        "level": 2,
        "evidence": ["docs/does/not/exist.md"],
        "reason": "the book states this plainly",
    })
    result = TASK._appraise(text, tmp_path)
    assert result["level"] == 1
    assert result["capped"] is True
    assert result["unverified_citations"] == ["docs/does/not/exist.md"]


def test_appraise_leaves_a_well_formed_level_two_verdict_alone(tmp_path: Path) -> None:
    real = tmp_path / "docs" / "features" / "web-app" / "gui" / "screens" / "widget-list.md"
    real.parent.mkdir(parents=True)
    real.write_text("- name: Add a widget\n", encoding="utf-8")

    text = json.dumps({
        "level": 2,
        "evidence": [str(real.relative_to(tmp_path))],
        "reason": "the digest still matches the app file, so the book is wrong",
    })
    result = TASK._appraise(text, tmp_path)
    assert result["level"] == 2
    assert result["capped"] is False
    assert result["unverified_citations"] == []


def test_appraise_treats_malformed_json_as_level_zero(tmp_path: Path) -> None:
    result = TASK._appraise("not json at all", tmp_path)
    assert result["level"] == 0
