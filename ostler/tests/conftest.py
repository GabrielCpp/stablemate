"""Shared fixtures + builders: a minimal on-disk org tree in the new markdown Concept format."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ostler import index, testsupport


def present[T](value: T | None) -> T:
    """``value`` with its ``None`` ruled out — for a lookup the test arranged to hit."""
    assert value is not None
    return value


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    """Only ``.agents/ids.json`` remains JSON in this format."""
    write(path, json.dumps(data, indent=2) + "\n")


def epic_md(eid: str, title: str, seeds: list[tuple[str, str, str]],
            stories: list[tuple[str, str, list[str]]]) -> str:
    """seeds: (id, status, summary)."""
    out = ["---", "type: epic", f"id: {eid}", f"title: {title}", "---",
           f"# Epic: {title}", ""]
    if seeds:
        out += ["## Seeds", ""]
        for sid, status, summary in seeds:
            out += [f"### {sid}", f"- status: {status}", "", summary, ""]
    out += ["## Stories", ""]
    for slug, stitle, covers in stories:
        out += [f"### {slug}",
                f"- title: {stitle}",
                f"- covers: {', '.join(covers) if covers else '(none)'}",
                ""]
    return "\n".join(out) + "\n"


def story_md(slug: str, title: str, status: str,
             doc_ref: str | None = None, depends: list[str] | None = None,
             fixtures: list[str] | None = None) -> str:
    deps = [f"- Blocked by: {d}" for d in (depends or [])] or ["(none)"]
    fixes = [f"- Fixture: {name}" for name in (fixtures or [])] or ["(none)"]
    body = ["---", "type: story", f"slug: {slug}", f"status: {status}", "---",
            f"# Story: {title}", "", "## Dependencies", "", *deps, "",
            "## Fixtures", "", *fixes, "",
            "## Context", "",
            f"Why {title} matters.", "",
            *([f"Feature doc: [reference]({doc_ref}).", ""] if doc_ref else []),
            "## Acceptance Criteria", "", "- The thing works.", "",
            "## Non-Functional Acceptance Criteria", "", "- It stays fast.", "",
            "## Technical Notes", "", "`src/thing.py::run` is the seam.", "",
            "## Implementation Status", "",
            f"- **Status**: {status}"]
    return "\n".join(body) + "\n"


def feature_md(slug: str, title: str, area: str = "", route: str = "") -> str:
    out = ["---", "type: feature", f"slug: {slug}", f"title: {title}"]
    if area:
        out.append(f"area: {area}")
    if route:
        out.append(f"route: {route}")
    out += ["---", f"# {title}", "", "feature prose", ""]
    return "\n".join(out) + "\n"


def screen_md(slug: str, title: str, *, entry: bool = False, body: str = "") -> str:
    """A UI-profile screen carrying every bullet the linter makes mandatory."""
    out = ["---", "type: screen", f"slug: {slug}", f"title: {title}", "---",
           f"# {title}", ""]
    out += [f"- route: `{'/' if entry else '/' + slug}`",
           "- requires: none",
           "- params: none",
           ""]
    return "\n".join(out) + (body or "")


UI_DASH_LINKS = """
Sits next to [rec](../area/rec.md) and its [heading](../area/rec.md#rec).

## Components

### dash-detail-link

- selector: `a[role="link"]`
- role: link
- name: Detail
- leads-to: [Detail](detail.md)
"""

UI_DASH_UNLINKED = """
Sits next to [rec](../area/rec.md) and its [heading](../area/rec.md#rec).
"""


@pytest.fixture
def ui_book(repo: Path) -> Path:
    """`repo` plus two screens — an entry screen that reaches a detail screen through a component."""
    write(repo / "docs/features/ui/dash.md",
          screen_md("dash", "Dash", entry=True, body=UI_DASH_LINKS))
    write(repo / "docs/features/ui/detail.md", screen_md("detail", "Detail"))
    write(repo / "docs/features/app/ops/qa-stack.md", (
        "---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
        "- driver: web\n- entry-url: http://localhost:18084\n\n"
        "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
    ))
    return repo


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A clean two-epic repo with feature docs cited by story prose."""
    root = tmp_path

    write(root / "docs/epics/epic-a/epic.md", epic_md(
        "t-1", "epic-a",
        seeds=[("seed-a1", "researched", "first"), ("seed-a2", "resolved", "done")],
        stories=[("01-foo", "Foo", ["seed-a1"])],
    ))
    write(root / "docs/epics/epic-a/stories/01-foo/story.md",
          story_md("01-foo", "Foo", "Not started", "../../../features/area/rec.md"))

    write(root / "docs/epics/epic-b/epic.md", epic_md(
        "t-2", "epic-b",
        seeds=[("seed-b1", "researched", "bee")],
        stories=[("01-bar", "Bar", ["seed-b1"])],
    ))
    write(root / "docs/epics/epic-b/stories/01-bar/story.md",
          story_md("01-bar", "Bar", "Not started"))

    write(root / "docs/features/area/rec.md", feature_md("rec", "Rec", area="area"))
    write(root / "docs/features/area/rec2.md", feature_md("rec2", "Rec 2", area="area"))

    return root


@pytest.fixture
def index_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The resolved index directory, with the operator's real config and cache out of reach."""
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config" / "config.toml"))
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    resolved = tmp_path / "resolved-index"
    monkeypatch.setenv("OSTLER_INDEX_DIR", str(resolved))
    return resolved


def entry_files(directory: Path) -> list[Path]:
    """Every entry the store has written under *directory* — none, when it was never created."""
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*")
                  if p.is_file() and p.name != index.PRUNE_STAMP_NAME)


def report_of(capsys) -> dict:
    """The `--json` payload a command just printed."""
    return json.loads(capsys.readouterr().out)


def ostler_process(book: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """One `ostler` invocation in a process of its own."""
    code = "import sys; from ostler.cli import main; sys.exit(main(sys.argv[1:]))"
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, "-C", str(book), *argv],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.DEVNULL, timeout=300, check=False,
    )


def warm_index(book: Path, directory: Path) -> None:
    """Populate *directory* the way a real run does — from a process that then exits."""
    done = ostler_process(book, "doctor", "--json", "--index-dir", str(directory))
    assert done.returncode in (0, 1), done.stderr or done.stdout
    assert entry_files(directory), (
        f"a run that loads a graph must populate the index, but {directory} is empty")



UNKNOWN_BULLET_ALLOWED_TESTS = frozenset({
    "tests/test_ui_doctor.py::test_an_undeclared_bullet_key_is_a_warning",
    "tests/test_ui_doctor.py::test_a_claim_under_a_non_normative_key_is_reported",
    "tests/test_ui_doctor.py::test_a_minting_node_is_still_asked_about_its_other_bullets",
})


@pytest.fixture(autouse=True)
def _inline_books_are_legal_okf(request: pytest.FixtureRequest):
    """Every `UINode` a test constructs must be one `doctor`'s `unknown-bullet` would not flag — unless the test is in `UNKNOWN_BULLET_ALLOWED_TESTS`, because it exists to prove that check fires."""
    start = len(testsupport.CONSTRUCTED_UI_NODES)
    yield
    nodes = testsupport.CONSTRUCTED_UI_NODES[start:]
    if not nodes or request.node.nodeid in UNKNOWN_BULLET_ALLOWED_TESTS:
        return
    violations = testsupport.unknown_bullet_violations(nodes)
    assert not violations, (
        f"{request.node.nodeid} builds a book `unknown-bullet` would flag on a real "
        f"run — the fixture is written against a grammar these types no longer declare: "
        f"{violations}"
    )
