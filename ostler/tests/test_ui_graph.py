"""`ostler graph` — the whole-graph dump (nodes + bullets + resolved edges) agents filter on."""

from __future__ import annotations

from pathlib import Path

from ostler import graph, links
from ostler.model import load

from conftest import write

SCREEN = """\
---
type: screen
slug: dash
title: Dashboard
---
# Dashboard

Shows the [diff](../../concepts/diff.md) concept.

## Components

### file-row
- selector: `.row`
- extends: [tree-node](../components/ds.md#tree-node)
"""

DS = """\
---
type: feature
slug: ds
title: DS
---
# DS

## tree-node

A node.
"""

DIFF = """\
---
type: concept
slug: diff
title: Diff
---
# Diff

- code: `diff.py::Diff`

A unified diff.
"""


def _repo(repo: Path):
    write(repo / "docs/features/groom/gui/screens/dash.md", SCREEN)
    write(repo / "docs/features/groom/gui/components/ds.md", DS)
    write(repo / "docs/features/groom/concepts/diff.md", DIFF)
    return load(repo)


def test_graph_emits_nodes_bullets(repo: Path):
    data = graph.build(_repo(repo))
    ids = {n["id"] for n in data["nodes"]}
    assert "docs/features/groom/gui/screens/dash.md" in ids
    assert "docs/features/groom/concepts/diff.md" in ids
    assert any(n["id"].endswith("#file-row") for n in data["nodes"])

    row = next(n for n in data["nodes"] if n["id"].endswith("#file-row"))
    assert row["bullets"].get("selector")
    assert "extends" in row["bullets"]
    assert row["surface"] == "groom"

    diff = next(n for n in data["nodes"] if n["id"].endswith("concepts/diff.md"))
    assert "diff.py::Diff" in diff["bullets"].get("code", "")


def test_graph_edges_resolve(repo: Path):
    data = graph.build(_repo(repo))
    assert data["counts"]["nodes"] == len(data["nodes"])
    assert any(e["to"] and e["to"].endswith("components/ds.md#tree-node") and e["resolves"]
               for e in data["edges"])


TARGET = """\
---
type: concept
slug: target
title: Target
---
# Target

A target.
"""

MULTI_VIA = """\
---
type: concept
slug: multi
title: Multi
---
# Multi

- alpha: [t](target.md)
- beta: [t](target.md)
- gamma: nested value continues
  and a link to [g](target.md#g) sits on the next line
- omega: final bullet with no link of its own

Trailing prose links to [t](target.md) again, and even cites
[g](target.md#g) a second time, well past every bullet.
"""


def test_graph_edges_attribute_by_link_position(repo: Path):
    """`via` follows where a link sits, not what its href is."""
    write(repo / "docs/features/demo/target.md", TARGET)
    write(repo / "docs/features/demo/multi.md", MULTI_VIA)
    data = graph.build(load(repo))
    node = next(n for n in data["nodes"] if n["id"].endswith("multi.md"))
    edges = node["edges"]
    assert [e["via"] for e in edges] == ["alpha", "beta", "gamma", "prose", "prose"]


def test_graph_scopes_by_type_and_surface(repo: Path):
    g = _repo(repo)
    concepts = graph.build(g, etype="concept")
    assert concepts["nodes"] and all(n["type"] == "concept" for n in concepts["nodes"])
    assert graph.build(g, surface="nope")["nodes"] == []


def _count_resolvers(monkeypatch) -> list:
    """Record every ``LinkResolver`` constructed, wherever it is constructed from."""
    made: list = []
    real_init = links.LinkResolver.__init__

    def spy_init(self, graph_, *args, **kwargs) -> None:
        real_init(self, graph_, *args, **kwargs)
        made.append(self)

    monkeypatch.setattr(links.LinkResolver, "__init__", spy_init)
    return made


def test_build_resolves_links_with_the_resolver_it_is_handed(repo: Path, monkeypatch):
    """A caller that already has a resolver keeps its anchor memo."""
    g = _repo(repo)
    resolver = links.LinkResolver(g)
    made = _count_resolvers(monkeypatch)

    data = graph.build(g, resolver=resolver)

    assert not made, f"build constructed {len(made)} resolvers of its own, want 0"
    assert resolver._anchors, "the handed-in resolver never resolved anything"
    assert any(e["resolves"] for e in data["edges"])


def test_build_owns_one_resolver_when_handed_none(repo: Path, monkeypatch):
    """The standalone caller is unchanged — one resolver for the build's own lifetime."""
    g = _repo(repo)
    made = _count_resolvers(monkeypatch)

    data = graph.build(g)

    assert len(made) == 1, f"{len(made)} resolvers built for one build, want 1"
    assert any(e["resolves"] for e in data["edges"])


NESTED = """\
---
type: format
slug: wf
title: Workflow format
---
# Workflow format

## concept: the agent node runs an LLM turn

### field: timeout bounds the wall-clock
- type: float|null
- default: 3600

## Methods

### run_turn executes one turn
- sig: `run_turn(prompt) -> str`

## Overview

Plain prose heading — not a typed node.
"""


def test_nesting_container_and_inline_typing(repo: Path):
    write(repo / "docs/features/demo/wf.md", NESTED)
    d = graph.build(load(repo))
    by_title = {n["title"]: n for n in d["nodes"]}

    fld = next(n for n in d["nodes"] if n["type"] == "field")
    assert fld["title"].startswith("timeout")
    assert fld["bullets"] == {"type": "float|null", "default": "3600"}
    assert fld["type_path"] == ["format", "concept", "field"]
    assert fld["parent"] == by_title["the agent node runs an LLM turn"]["id"]

    m = next(n for n in d["nodes"] if n["type"] == "method")
    assert m["title"].startswith("run_turn") and m["bullets"].get("sig")

    ov = by_title.get("Overview")
    assert ov is not None and ov["type"] == "untyped"


def test_selectors(repo: Path):
    write(repo / "docs/features/demo/wf.md", NESTED)
    d = graph.build(load(repo))

    hit = graph.select(d, path="concept:agent / field:timeout")
    assert len(hit) == 1 and hit[0]["title"].startswith("timeout")
    assert graph.select(d, path="field:nope") == []

    concept = next(n for n in d["nodes"] if n["type"] == "concept")
    under = graph.select(d, under=concept["id"], depth=1)
    assert any(n["type"] == "field" for n in under)

    assert graph.select(d, bullet="default=3600")
    assert all("sig" in n["bullets"] for n in graph.select(d, has_bullet="sig"))
    assert graph.select(d, node_type="method") and graph.select(d, title="timeout")


REPEATED_HEADING = """\
---
type: concept
slug: queue
title: Queue
---
# Queue

Jump to the [second one](./queue.md#effects-1).

## Methods

### method-register
#### Effects
- does: the client is added

### method-unregister
#### Effects
- does: the client is dropped
"""


def test_a_repeated_heading_gets_the_anchor_github_renders(repo: Path):
    """Two headings with one title are two nodes, at the two anchors a browser jumps to."""
    write(repo / "docs/features/groom/concepts/queue.md", REPEATED_HEADING)
    g = load(repo)

    ids = [n.id for n in g.ui_nodes]
    assert len(ids) == len(set(ids)), f"node ids stated twice: {ids}"
    assert "docs/features/groom/concepts/queue.md#effects" in ids
    assert "docs/features/groom/concepts/queue.md#effects-1" in ids

    first = g.find_ui_node("docs/features/groom/concepts/queue.md#effects")
    second = g.find_ui_node("docs/features/groom/concepts/queue.md#effects-1")
    assert first is not None and second is not None and first.line < second.line
    assert first.meta["does"] == "the client is added"
    assert second.meta["does"] == "the client is dropped"

    resolver = links.LinkResolver(g)
    assert "effects-1" in resolver.anchors(repo / "docs/features/groom/concepts/queue.md")


def test_orphans_are_whole_pages_nothing_reaches(repo: Path):
    """A heading inside a linked page is reached through its page, and an unlinked page is one orphan."""
    write(repo / "docs/features/demo/wf.md", NESTED)
    write(repo / "docs/features/demo/lonely.md", NESTED.replace("slug: wf", "slug: lonely"))
    write(repo / "docs/features/demo/hub.md",
          "---\ntype: concept\nslug: hub\ntitle: Hub\n---\n# Hub\n\n"
          "Runs [a turn](wf.md#run_turn-executes-one-turn).\n")
    d = graph.build(load(repo))
    orphans = graph.select(d, orphans=True)

    assert sorted(n["path"] for n in orphans) == ["docs/features/demo/hub.md",
                                                   "docs/features/demo/lonely.md"]
    assert all(n["parent"] not in {m["id"] for m in d["nodes"]} for n in orphans)
