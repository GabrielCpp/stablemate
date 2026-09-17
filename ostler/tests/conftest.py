"""Shared fixtures + builders: a minimal on-disk org tree in the new markdown Concept format."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ostler import index, testsupport


def present[T](value: T | None) -> T:
    """``value`` with its ``None`` ruled out — for a lookup the test arranged to hit.

    A test that fixtures a story and then reads ``select.next_story(...)["slug"]`` is not
    asking whether the lookup found anything. Saying so here keeps the failure legible if
    it ever stops finding it (``assert ... is not None`` naming the call, rather than a
    subscript of ``None`` several lines later) and lets the type checker see what the test
    already knows. Where absence is the thing under test, assert on it directly instead.
    """
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
    """seeds: (id, status, summary). stories: (slug, title, covers[]).

    No dependency edge here: a story's blockers are stated in its own `## Dependencies`
    section, which `story_md` renders.
    """
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
    # A written story: every `filled` section of registry.STORY_SECTIONS carries prose, so the
    # fixture repo is authored and `doctor` stays green. Leave one blank and it reports
    # `unwritten-story` — which is the point of the check.
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
    """A UI-profile screen carrying every bullet the linter makes mandatory.

    `route`/`requires`/`params` are *body* bullets, not frontmatter: the linter reads a node's
    bullets off the parsed sections, so a screen that states its route in the frontmatter still
    reports `missing-required-bullet`.
    """
    out = ["---", "type: screen", f"slug: {slug}", f"title: {title}", "---",
           f"# {title}", ""]
    # The root is the screen serving `/` — with no server contract in the book, that is the one
    # address the doctor seeds reachability from. A prose `entry:` would not do it.
    out += [f"- route: `{'/' if entry else '/' + slug}`",
           "- requires: none",
           "- params: none",
           ""]
    return "\n".join(out) + (body or "")


# The entry screen: it links out to two feature docs (one of them to an anchor, which is what
# makes the link resolver parse that file) and reaches `detail.md` through a component edge.
UI_DASH_LINKS = """
Sits next to [rec](../area/rec.md) and its [heading](../area/rec.md#rec).

## Components

### dash-detail-link

- selector: `a[role="link"]`
- role: link
- name: Detail
- leads-to: [Detail](detail.md)
"""

# The same screen with the component edge cut: `detail.md` is then reachable from nothing, and
# the finding lands on a file this run never re-read.
UI_DASH_UNLINKED = """
Sits next to [rec](../area/rec.md) and its [heading](../area/rec.md#rec).
"""


@pytest.fixture
def ui_book(repo: Path) -> Path:
    """`repo` plus two screens — an entry screen that reaches a detail screen through a component.

    Enough of a UI profile that one `doctor` run exercises all five read-only parse sites: the
    graph load, the per-file UI check, conformance, and the link resolver's anchor computation.
    """
    write(repo / "docs/features/ui/dash.md",
          screen_md("dash", "Dash", entry=True, body=UI_DASH_LINKS))
    write(repo / "docs/features/ui/detail.md", screen_md("detail", "Detail"))
    # A served surface needs a stack runbook, or `doctor` reports `runbook-missing` (an
    # error) — none of the read-only parse sites this fixture exercises are about that check.
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

    # epic-a: story 01-foo covers seed-a1; seed-a2 is resolved (inactive).
    write(root / "docs/epics/epic-a/epic.md", epic_md(
        "t-1", "epic-a",
        seeds=[("seed-a1", "researched", "first"), ("seed-a2", "resolved", "done")],
        stories=[("01-foo", "Foo", ["seed-a1"])],
    ))
    write(root / "docs/epics/epic-a/stories/01-foo/story.md",
          story_md("01-foo", "Foo", "Not started", "../../../features/area/rec.md"))

    # epic-b: story 01-bar covers seed-b1.
    write(root / "docs/epics/epic-b/epic.md", epic_md(
        "t-2", "epic-b",
        seeds=[("seed-b1", "researched", "bee")],
        stories=[("01-bar", "Bar", ["seed-b1"])],
    ))
    write(root / "docs/epics/epic-b/stories/01-bar/story.md",
          story_md("01-bar", "Bar", "Not started"))

    # features: docs referenced from story prose by ordinary markdown links
    write(root / "docs/features/area/rec.md", feature_md("rec", "Rec", area="area"))
    write(root / "docs/features/area/rec2.md", feature_md("rec2", "Rec 2", area="area"))

    return root


# ---------------------------------------------------------------------------
# the parse index: a directory of one's own, and a warm one to run against
# ---------------------------------------------------------------------------
@pytest.fixture
def index_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The resolved index directory, with the operator's real config and cache out of reach."""
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config" / "config.toml"))
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    resolved = tmp_path / "resolved-index"
    monkeypatch.setenv("OSTLER_INDEX_DIR", str(resolved))
    return resolved


def entry_files(directory: Path) -> list[Path]:
    """Every entry the store has written under *directory* — none, when it was never created.

    The prune stamp is not an entry and is left out. Counting it would let "the index is not
    empty" hold for a directory a store had only ever swept, which is the exact thing several
    of these assertions exist to rule out.
    """
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
    """Populate *directory* the way a real run does — from a process that then exits.

    A same-process warm-up proves nothing about the store: any process-lifetime memo would
    answer the second run before the index was ever consulted. Leaving the process makes the
    index the only thing that survives, so a later hit is a hit on disk.
    """
    done = ostler_process(book, "doctor", "--json", "--index-dir", str(directory))
    assert done.returncode in (0, 1), done.stderr or done.stdout
    assert entry_files(directory), (
        f"a run that loads a graph must populate the index, but {directory} is empty")


# ---------------------------------------------------------------------------
# a test's own fixture is a book: every inline book this suite builds must be
# legal OKF, or a reader-side check can go stale for years without a witness
# (this is what let `test_qa_fixture_wiring.py`'s `- route:` bullet and
# `test_qa_scope.py`'s bare `## Widget` heading pass since neither node's type
# ever declared the key it exercised — see fix(ostler) 894d2d0f). The recorder
# and the violation-check are shared plumbing, in `ostler.testsupport` — this
# file keeps only its own autouse fixture and its own allow-set, both scoped
# to this suite's nodeids.
# ---------------------------------------------------------------------------

#: Tests that build a book with an undeclared, load-bearing bullet key *on purpose* — the
#: deliberate negative fixtures this gate must tell apart from a stale one. Keyed by pytest
#: nodeid, so a stale fixture anywhere else in the suite has nowhere to hide behind someone
#: else's deliberate violation. Add to this set only for a test whose own assertions read the
#: report for what an undeclared key does (`unknown-bullet` firing directly, or another check —
#: `unminted-claim` — that exists precisely to catch a claim hiding under such a key) — never to
#: silence a failure this gate raises for a fixture nobody meant to write that way.
UNKNOWN_BULLET_ALLOWED_TESTS = frozenset({
    "tests/test_ui_doctor.py::test_an_undeclared_bullet_key_is_a_warning",
    "tests/test_ui_doctor.py::test_a_claim_under_a_non_normative_key_is_reported",
    "tests/test_ui_doctor.py::test_a_node_that_mints_is_not_asked_about_its_prose",
})


@pytest.fixture(autouse=True)
def _inline_books_are_legal_okf(request: pytest.FixtureRequest):
    """Every `UINode` a test constructs must be one `doctor`'s `unknown-bullet` would not flag —
    unless the test is in `UNKNOWN_BULLET_ALLOWED_TESTS`, because it exists to prove that check
    fires. A node a test builds is a book nothing else in the pipeline reads for grammar the way
    a real book is read by `doctor`; this fixture is what stands in for that reading here.
    """
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
