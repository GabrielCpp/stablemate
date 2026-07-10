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

    # inline `## concept:` and nested `### field:` both promote, with hierarchy
    fld = next(n for n in d["nodes"] if n["type"] == "field")
    assert fld["title"].startswith("timeout")
    assert fld["bullets"] == {"type": "float|null", "default": "3600"}
    assert fld["type_path"] == ["format", "concept", "field"]        # nested under the concept
    assert fld["parent"] == by_title["the agent node runs an LLM turn"]["id"]

    # `## Methods` container types its child as a method
    m = next(n for n in d["nodes"] if n["type"] == "method")
    assert m["title"].startswith("run_turn") and m["bullets"].get("sig")

    # a heading that names no type is still promoted — as `untyped`, caught by --title
    ov = by_title.get("Overview")
    assert ov is not None and ov["type"] == "untyped"


def test_selectors(repo: Path):
    write(repo / "docs/features/demo/wf.md", NESTED)
    d = graph.build(load(repo))

    # --path: "timeout of the agent node", relative, no absolute id
    hit = graph.select(d, path="concept:agent / field:timeout")
    assert len(hit) == 1 and hit[0]["title"].startswith("timeout")
    assert graph.select(d, path="field:nope") == []

    # --under (+ node-hop --depth): the concept's subtree holds the field one hop down
    concept = next(n for n in d["nodes"] if n["type"] == "concept")
    under = graph.select(d, under=concept["id"], depth=1)
    assert any(n["type"] == "field" for n in under)

    # bullet filters
    assert graph.select(d, bullet="default=3600")
    assert all("sig" in n["bullets"] for n in graph.select(d, has_bullet="sig"))
    assert graph.select(d, node_type="method") and graph.select(d, title="timeout")
