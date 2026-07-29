"""A story cites the OKF book by linking node ids — the three pieces that make that an edge.

``References.doc_hrefs`` (which links are document citations at all) → ``Graph.resolve_doc_ref``
(href → node identity, however the link was written) → ``query.surfaces-referenced-by-story``
(identity → a typed row). A UI node's identity **is** its location, so a citation is an ordinary
markdown link and nothing story-shaped had to be invented to carry it.

The rows are tagged rather than filtered on purpose: a caller (author's grounding gate) must be
able to tell "cited a node" from "cited a node id that resolves to nothing" from "cited no node",
and dropping unresolvable citations would collapse the last two.
"""
from __future__ import annotations

from pathlib import Path

from ostler import markdown, query
from ostler.model import load

from conftest import write

SCREEN = "docs/features/gui/screens/settings.md"
SCREEN_MD = """\
---
type: screen
slug: settings
title: Settings
---
# Settings

- route: /settings
- requires: none
- params: none

## Components

### Save profile

- role: button
- name: Save profile
"""

STORY_DIR = "docs/epics/e/stories/01-s"


def story(context: str) -> str:
    return (
        "---\ntype: story\nslug: 01-s\nstatus: Not started\n---\n"
        "# Story: S\n\n"
        f"## Context\n\n{context}\n\n"
        "## Acceptance Criteria\n\n- It works.\n\n"
        "## Implementation Status\n\n- **Status**: Not started\n"
    )


def book_repo(root: Path, context: str) -> Path:
    write(root / SCREEN, SCREEN_MD)
    write(root / "docs/epics/e/epic.md",
          "---\ntype: epic\nid: t-1\ntitle: E\n---\n# Epic: E\n\n"
          "## Stories\n\n### 01-s\n- title: S\n- covers: (none)\n- depends on: (none)\n")
    write(root / STORY_DIR / "story.md", story(context))
    return root


def refs(root: Path) -> list[dict]:
    return query.query(load(root), "surfaces-referenced-by-story", "01-s")


# ── doc_hrefs: which links are citations of a document in this repo ───────────────────────

def test_doc_hrefs_keeps_document_links_verbatim():
    r = markdown.extract_refs(
        "See [a](docs/features/x.md) and [b](../x.md#anchor) and [c](/docs/x.md)."
    )
    assert r.doc_hrefs == ["docs/features/x.md", "../x.md#anchor", "/docs/x.md"]


def test_doc_hrefs_drops_non_documents_and_dedupes():
    r = markdown.extract_refs(
        "[url](https://example.com/x.md) [mail](mailto:a@example.com) "
        "[here](#section) [a](x.md) [again](x.md)"
    )
    assert r.doc_hrefs == ["x.md"]


# ── resolve_doc_ref: every way a link can be written names the same node ──────────────────

def test_resolve_doc_ref_accepts_all_three_link_forms(tmp_path: Path):
    g = load(book_repo(tmp_path, "no citations here"))
    origin = tmp_path / STORY_DIR / "story.md"
    for href in (SCREEN,                                        # node id copied verbatim
                 f"/{SCREEN}",                                  # root-anchored
                 "../../../../features/gui/screens/settings.md"):  # relative to the story
        assert g.resolve_doc_ref(href, origin=origin) == SCREEN, href


def test_resolve_doc_ref_keeps_the_anchor(tmp_path: Path):
    g = load(book_repo(tmp_path, "no citations here"))
    ident = g.resolve_doc_ref(f"{SCREEN}#save-profile", origin=tmp_path / STORY_DIR / "story.md")
    assert ident == f"{SCREEN}#save-profile"


def test_resolve_doc_ref_returns_unresolvable_refs_instead_of_dropping_them(tmp_path: Path):
    """A typo must come back as an identity the caller can report, not as an empty string."""
    g = load(book_repo(tmp_path, "no citations here"))
    ident = g.resolve_doc_ref("nope/missing.md", origin=tmp_path / STORY_DIR / "story.md")
    assert ident.endswith("missing.md")


def test_a_link_that_escapes_the_repo_is_not_silently_resolved(tmp_path: Path):
    """It is not a document in this repo, so neither reading lands — it comes back verbatim
    and is reported as a citation of nothing rather than quietly becoming some in-repo path."""
    href = "../" * 12 + "elsewhere.md"
    g = load(book_repo(tmp_path, "no citations here"))
    assert g.resolve_doc_ref(href, origin=tmp_path / STORY_DIR / "story.md") == href
    assert [r["kind"] for r in refs(book_repo(tmp_path, f"See [x]({href}))."))] == ["missing"]


# ── the query rows: ui / file / missing ───────────────────────────────────────────────────

def test_citing_a_file_node_yields_a_ui_row(tmp_path: Path):
    rows = refs(book_repo(tmp_path, f"Reworks [settings]({SCREEN})."))
    assert rows == [{"path": SCREEN, "kind": "ui", "type": "screen", "title": "Settings"}]


def test_citing_a_section_node_yields_a_ui_row(tmp_path: Path):
    rows = refs(book_repo(tmp_path, f"Reworks [Save]({SCREEN}#save-profile)."))
    assert [r["kind"] for r in rows] == ["ui"]
    assert rows[0]["type"] == "component"


def test_a_document_that_is_not_a_node_is_a_file_row(tmp_path: Path):
    root = book_repo(tmp_path, "Per [the spec](docs/spec.md).")
    write(root / "docs/spec.md", "# Spec\n")
    assert [r["kind"] for r in refs(root)] == ["file"]


def test_a_path_that_resolves_to_nothing_is_a_missing_row(tmp_path: Path):
    rows = refs(book_repo(tmp_path, "Reworks [settings](docs/features/gui/screens/setttings.md)."))
    assert [r["kind"] for r in rows] == ["missing"]


def test_a_bad_anchor_into_a_book_node_is_missing_not_file(tmp_path: Path):
    """The document existing is not evidence the cited section does — and it is the likelier typo."""
    rows = refs(book_repo(tmp_path, f"Reworks [Save]({SCREEN}#save-prophile)."))
    assert [r["kind"] for r in rows] == ["missing"]


def test_a_bad_anchor_into_an_ordinary_document_stays_a_file_row(tmp_path: Path):
    """Deep-linking a spec is not a node citation, so its anchors are not held to node identity."""
    root = book_repo(tmp_path, "Per [the spec](docs/spec.md#whatever).")
    write(root / "docs/spec.md", "# Spec\n")
    assert [r["kind"] for r in refs(root)] == ["file"]


def test_citations_are_deduped_across_link_forms(tmp_path: Path):
    rows = refs(book_repo(
        tmp_path,
        f"Reworks [settings]({SCREEN}), see also "
        "[settings again](../../../../features/gui/screens/settings.md).",
    ))
    assert [r["path"] for r in rows] == [SCREEN]


def test_a_story_that_cites_nothing_yields_no_rows(tmp_path: Path):
    assert refs(book_repo(tmp_path, "Reworks the settings screen.")) == []
