"""Tests for `globex_book_operate`, without ever asking an agent anything or running docker.

This only covers the deterministic half of the task: that the module loads and registers
cleanly, that `arrange`'s perturbations do exactly what the module claims they do, and
that `_appraise` is pure and testable. `ask` and `judge` invoke a real agent and drive
docker/a browser, so they are out of scope here — a suite that called them would grade a
model and a browser, not this module.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import re
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


TASK = _load("_operate_task_under_test", DATA / "tasks" / "globex_book_operate.py")


def _run(tmp_path: Path) -> Run:
    """A real `Run`, pointed at the fixture, with no agent CLI and no docker ever invoked."""
    task = Task(name="globex-book-operate", seed="globex", config=TASK.CONFIG, steps=(),
               score=TASK.score, module="globex_book_operate")
    seed = Pointer(name="globex", repo_dir="globex", sha256="0" * 64, bytes=0)
    return Run(
        task=task, label="test", stage=tmp_path / "stage", repo=APP,
        scratch=tmp_path / "scratch", config=DATA / "configs" / "opencode.toml",
        data_dir=DATA, store=tmp_path / "store", seed=seed, echo=False,
    )


# ── the module loads and registers ──────────────────────────────────────────────────────


def test_the_module_registers_under_loader_load_all() -> None:
    """A duplicate task name or an import-time error would fail every task, not just this
    one — `loader.load_all` is the same entry point `paddock list` and every gate use."""
    tasks = loader.load_all(DATA)
    names = {item.name for item in tasks}
    assert "globex-book-operate" in names


def test_the_rubric_file_exists_beside_the_other_rubrics() -> None:
    assert (DATA / "rubric-operate.md").is_file()


# ── arrange: the trees it builds ─────────────────────────────────────────────────────────


def test_arrange_builds_one_tree_per_line_and_arm_with_app_and_compose(tmp_path: Path) -> None:
    """One tree per `(line, arm)` pair, where each line's own `arms` picks the pairs —
    bring-up runs both, journey runs control only, three trials total."""
    run = _run(tmp_path)
    TASK.arrange(run)

    ledger = run.stage / "artifacts" / "trials" / "trials.json"
    assert ledger.is_file()
    trials = run.read_json(ledger)
    assert len(trials) == sum(len(line.arms) for line in TASK.LINES)
    assert len(trials) == 3

    for trial in trials:
        tree = TASK._tree_dir(run, trial["id"])
        assert (tree / "docs").is_dir()
        assert (tree / "app").is_dir()
        assert (tree / "compose.yml").is_file()

        mcp_path = tree / ".mcp.json"
        assert mcp_path.is_file()
        mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
        assert "playwright" in mcp["mcpServers"]


# ── arrange: control leaves the perturbed bullets intact ────────────────────────────────


def test_control_leaves_bring_up_bullets_intact(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    line = TASK.LINES_BY_NAME["bring-up"]
    tree = TASK._tree_dir(run, TASK._slug(line, "control"))
    for rel in TASK.BRING_UP_DOCS:
        text = (tree / "docs" / rel).read_text(encoding="utf-8")
        assert "- run: `docker compose up --build" in text
        assert "- entry-url: http://localhost:1810" in text


def test_control_leaves_journey_bullets_intact(tmp_path: Path) -> None:
    run = _run(tmp_path)
    TASK.arrange(run)
    line = TASK.LINES_BY_NAME["journey"]
    tree = TASK._tree_dir(run, TASK._slug(line, "control"))
    text = (tree / "docs" / TASK.JOURNEY_DOC).read_text(encoding="utf-8")
    assert "- start: [widget-list]" in text
    assert "- steps:" in text
    assert "  - [open-new-widget]" in text
    assert "  - [submit-new-widget]" in text


# ── arrange: absence empties the bullet values, keeps the keys ──────────────────────────


def test_bring_up_absence_empties_every_bullet_in_the_table_but_keeps_the_keys(
    tmp_path: Path,
) -> None:
    """Per-key check: every row `BRING_UP_BULLETS` names survives as a valueless bullet,
    in the file that row names — the key line is untouched, only its value is gone."""
    run = _run(tmp_path)
    TASK.arrange(run)
    line = TASK.LINES_BY_NAME["bring-up"]
    tree = TASK._tree_dir(run, TASK._slug(line, "absence"))

    by_path: dict[str, list[tuple[str, str]]] = {}
    for rel, key, kind in TASK.BRING_UP_BULLETS:
        by_path.setdefault(rel, []).append((key, kind))

    for rel, bullets in by_path.items():
        text = (tree / "docs" / rel).read_text(encoding="utf-8")
        lines = text.splitlines()
        for key, kind in bullets:
            if kind == "scalar-first":
                matches = [
                    row for row in lines
                    if row == f"- {key}:" or row.startswith(f"- {key}: ")
                ]
                assert matches[0] == f"- {key}:"
                assert all(row.startswith(f"- {key}: ") for row in matches[1:])
                continue
            assert f"- {key}:" in lines
            assert not any(row.startswith(f"- {key}: ") for row in lines)
            if kind == "list":
                index = lines.index(f"- {key}:")
                assert not (
                    index + 1 < len(lines) and lines[index + 1].startswith("  - ")
                )

    run_lines = (tree / "docs" / "features/web-app/fixtures/widgets-on-hand.md").read_text(
        encoding="utf-8",
    )
    assert "- run: curl -sf -X POST http://localhost:18101/api/widgets" in run_lines
    assert "- run: curl -sf http://localhost:18101/api/widgets |" in run_lines


def test_bring_up_absence_states_neither_18102_nor_the_up_command_anywhere_in_the_book(
    tmp_path: Path,
) -> None:
    """The load-bearing assertion this round adds: not "the two runbooks this arm was
    written to touch," but every page under the perturbed tree's `docs/` — the round 3
    defect was a fact restated on a page the scoped version of this test never looked at.
    `18101` is deliberately not checked here; see `BRING_UP_BULLETS`'s docstring for why."""
    run = _run(tmp_path)
    TASK.arrange(run)
    line = TASK.LINES_BY_NAME["bring-up"]
    tree = TASK._tree_dir(run, TASK._slug(line, "absence"))
    docs = tree / "docs"

    pages = sorted(docs.rglob("*.md"))
    assert pages, "no .md pages found under the perturbed docs/ tree"
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert "18102" not in text, f"{page} still states 18102"
        assert "docker compose up" not in text, f"{page} still states the up-command"

    assert any("18101" in page.read_text(encoding="utf-8") for page in pages), (
        "18101 should still be stated somewhere in the book — it is api-service's own "
        "address, a different fact from the one this line tests"
    )


def test_bring_up_absence_leaves_no_code_bullet_routing_to_18102_or_the_up_command(
    tmp_path: Path,
) -> None:
    """The round 4 defect, and the half of the sweep above that reads the book's routes
    rather than its spelling. The test above asserts no page *states* the two facts; it
    passed for three rounds while all three bring-up pages still carried
    `- code: `compose.yml``, which is exactly where both facts live. A citation is a
    route, and in an OKF book routing a reader to a fact and stating it are the same
    claim — so an agent that opened `compose.yml` on this arm had followed the book, not
    gone around it, and the arm's premise was false. This walks every surviving `- code:`
    bullet and opens the file it cites, so the next fact that hides one hop away fails
    here instead of being scored as a shortcut."""
    run = _run(tmp_path)
    TASK.arrange(run)
    line = TASK.LINES_BY_NAME["bring-up"]
    tree = TASK._tree_dir(run, TASK._slug(line, "absence"))

    bullet = re.compile(r"^- code: `([^`]+)`", re.MULTILINE)
    resolved = 0
    for page in sorted((tree / "docs").rglob("*.md")):
        for match in bullet.finditer(page.read_text(encoding="utf-8")):
            cited = tree / match.group(1).split("::", 1)[0]
            if not cited.is_file():
                continue
            resolved += 1
            text = cited.read_text(encoding="utf-8", errors="ignore")
            assert "18102" not in text, f"{page} cites {cited.name}, which states 18102"
            assert "docker compose up" not in text, (
                f"{page} cites {cited.name}, which states the up-command"
            )

    assert resolved, (
        "no `- code:` bullet resolved to a file in the tree — this sweep would pass "
        "vacuously, so it is not yet checking anything"
    )

# ── _appraise: pure, no agent involved ───────────────────────────────────────────────────


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
    real = tmp_path / "docs" / "features" / "api-service" / "ops" / "api-service-stack.md"
    real.parent.mkdir(parents=True)
    real.write_text("- run: `docker compose up --build api-service`\n", encoding="utf-8")

    text = json.dumps({
        "level": 2,
        "evidence": [str(real.relative_to(tmp_path))],
        "reason": "the runbook names the run command",
    })
    result = TASK._appraise(text, tmp_path)
    assert result["level"] == 2
    assert result["capped"] is False
    assert result["unverified_citations"] == []


def test_appraise_treats_malformed_json_as_level_zero(tmp_path: Path) -> None:
    result = TASK._appraise("not json at all", tmp_path)
    assert result["level"] == 0
