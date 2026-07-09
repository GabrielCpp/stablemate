"""`ostler graph` — the whole-graph dump (nodes + bullets + resolved edges) agents filter on."""

from __future__ import annotations

from pathlib import Path

from ostler import graph
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
    assert any(n["id"].endswith("#file-row") for n in data["nodes"])  # section node

    row = next(n for n in data["nodes"] if n["id"].endswith("#file-row"))
    assert row["bullets"].get("selector")           # every `- key: value` captured
    assert "extends" in row["bullets"]
    assert row["surface"] == "groom"

    diff = next(n for n in data["nodes"] if n["id"].endswith("concepts/diff.md"))
    assert "diff.py::Diff" in diff["bullets"].get("code", "")  # code: bullet → dedup/coverage source


def test_graph_edges_resolve(repo: Path):
    data = graph.build(_repo(repo))
    assert data["counts"]["nodes"] == len(data["nodes"])
    # the `extends:` edge file-row -> ds#tree-node is present and resolves
    assert any(e["to"] and e["to"].endswith("components/ds.md#tree-node") and e["resolves"]
               for e in data["edges"])


def test_graph_scopes_by_type_and_surface(repo: Path):
    g = _repo(repo)
    concepts = graph.build(g, etype="concept")
    assert concepts["nodes"] and all(n["type"] == "concept" for n in concepts["nodes"])
    assert graph.build(g, surface="nope")["nodes"] == []
