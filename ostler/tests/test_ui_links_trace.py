"""Link resolution (§6.1) + `ostler trace` UI branch (§10)."""

from __future__ import annotations

from pathlib import Path

from ostler import links, trace
from ostler.model import load

from conftest import write


SCREEN = """\
---
type: screen
slug: changes-view
title: Changes view
---
# Changes view

Presents the [diff](../../concepts/diff.md) concept.

## Components

### changes-file-row
- selector: `.tree-file`
- extends: [tree-node](../components/design-system.md#tree-node)

## Interactions

### click-file
- on: [changes-file-row](#changes-file-row)
- trigger: click
- does:
  - state: mark row
"""

DESIGN = """\
---
type: feature
slug: design-system
title: DS
---
# DS

## Components

### tree-node
- selector: `.tree-file`
"""

DIFF = """\
---
type: concept
slug: diff
title: Diff
---
# Diff

A unified diff.
"""


def _repo_with_graph(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    write(repo / "docs/features/groom/gui/components/design-system.md", DESIGN)
    write(repo / "docs/features/groom/concepts/diff.md", DIFF)
    return load(repo)


# ---------------------------------------------------------------------------
# §6.1 — resolution
# ---------------------------------------------------------------------------
def test_resolve_cross_file_anchor(repo: Path):
    graph = _repo_with_graph(repo)
    src = repo / "docs/features/groom/gui/screens/changes-view.md"
    r = links.LinkResolver(graph)
    tgt = r.resolve(src, "../components/design-system.md#tree-node")
    assert tgt.file_exists and tgt.anchor_exists and tgt.resolved
    assert tgt.node_id == "docs/features/groom/gui/components/design-system.md#tree-node"


def test_resolve_same_file_anchor(repo: Path):
    graph = _repo_with_graph(repo)
    src = repo / "docs/features/groom/gui/screens/changes-view.md"
    tgt = links.LinkResolver(graph).resolve(src, "#changes-file-row")
    assert tgt.resolved and tgt.anchor == "changes-file-row"


def test_resolve_dangling_file(repo: Path):
    graph = _repo_with_graph(repo)
    src = repo / "docs/features/groom/gui/screens/changes-view.md"
    tgt = links.LinkResolver(graph).resolve(src, "../nope/missing.md")
    assert not tgt.file_exists and not tgt.resolved


def test_resolve_missing_anchor(repo: Path):
    graph = _repo_with_graph(repo)
    src = repo / "docs/features/groom/gui/screens/changes-view.md"
    tgt = links.LinkResolver(graph).resolve(src, "../../concepts/diff.md#ghost")
    assert tgt.file_exists and not tgt.anchor_exists and not tgt.resolved


def test_code_ref_is_not_a_doc_link():
    assert not links.is_doc_link("groom/groom/render.py::_inbox_row")
    assert not links.is_doc_link("https://example.com")
    assert links.is_doc_link("../concepts/diff.md")


# ---------------------------------------------------------------------------
# §10 — trace
# ---------------------------------------------------------------------------
def test_trace_section_node_outbound_and_inbound(repo: Path):
    graph = _repo_with_graph(repo)
    lines, found = trace.run(graph, "changes-file-row")
    assert found
    text = "\n".join(lines)
    assert "component" in text
    # outbound edge to tree-node resolves ok
    assert "design-system.md#tree-node  [ok]" in text
    # inbound: click-file interaction references changes-file-row
    assert "referenced by" in text and "click-file" in text


def test_trace_file_node_by_slug(repo: Path):
    graph = _repo_with_graph(repo)
    lines, found = trace.run(graph, "changes-view")
    assert found
    assert any("screen" in ln for ln in lines)


def test_trace_reports_dangling(repo: Path):
    write(repo / "docs/features/groom/flows/f.md",
          "---\ntype: flow\nslug: f\ntitle: F\n---\n# F\n\n"
          "- steps:\n  1. [gone](../gui/screens/gone.md)\n")
    graph = load(repo)
    lines, found = trace.run(graph, "f")
    assert found
    assert any("DANGLING" in ln for ln in lines)


def test_trace_unknown_token_returns_not_found(repo: Path):
    graph = _repo_with_graph(repo)
    lines, found = trace.run(graph, "no-such-thing")
    assert not found
