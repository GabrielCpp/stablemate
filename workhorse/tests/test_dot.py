"""Tests for rendering a workflow Graph to Graphviz DOT (workhorse/graph/dot.py).

The renderer is type-based and self-contained, so these tests use a small inline
fixture graph (no dependency on any real workflow) shaped like the coder workflow:
a `mode` branch at the start whose two cases lead to mode-specific subgraphs that
later re-converge, plus a numeric guard loop, a terminal, and a fail node.

  decide_mode ─epic→ init_base ┐
              └story→ reset_plan┴→ work → guard ─(>= 3)→ decide_fail ─epic→ give_up → done
                                    ↑        └default→ work (loop)     └story→ hard_fail(fail)
  orphan → done   (orphan is referenced by nobody — unreachable)

Run: ./.venv/bin/python tests/test_dot.py   (or via pytest)
"""
from __future__ import annotations

from workhorse.graph.dot import to_dot
from workhorse.graph.nodes import Graph

_NODES = [
    {
        "id": "decide_mode",
        "type": "branch",
        "path": "mode",
        "cases": {"epic": "init_base", "story": "reset_plan"},
        "default": "reset_plan",
    },
    {"id": "init_base", "type": "script", "script": "init.sh", "next": "work"},
    {"id": "reset_plan", "type": "script", "script": "reset.sh", "next": "work"},
    {"id": "work", "type": "agent", "prompt": "work.md", "next": "guard"},
    {
        "id": "guard",
        "type": "branch",
        "path": "count",
        "conditions": [{"op": ">=", "value": "3", "next": "decide_fail"}],
        "default": "work",
    },
    {
        "id": "decide_fail",
        "type": "branch",
        "path": "mode",
        "cases": {"epic": "give_up", "story": "hard_fail"},
        "default": "hard_fail",
    },
    {"id": "give_up", "type": "script", "script": "giveup.sh", "next": "done"},
    {"id": "hard_fail", "type": "fail"},
    {"id": "done", "type": "terminal"},
    {"id": "orphan", "type": "agent", "prompt": "orphan.md", "next": "done"},
]


def _graph() -> Graph:
    nodes = {n["id"]: n for n in _NODES}
    return Graph.model_validate(
        {"name": "demo-flow", "start": "decide_mode", "vars": {}, "nodes": nodes}
    )


def _decls(out: str) -> list[str]:
    """Stripped node-declaration lines (id followed by '['), excluding edges."""
    return [
        ln.strip()
        for ln in out.splitlines()
        if "->" not in ln and ln.strip().endswith("];")
    ]


def test_header_and_structure():
    out = to_dot(_graph())
    assert out.startswith("digraph demo_flow {")  # name sanitized (- -> _)
    assert "rankdir=TB;" in out
    assert 'node [shape=box, style="rounded,filled", fillcolor=lightblue];' in out
    assert "edge [color=darkblue, fontsize=10];" in out
    assert out.rstrip().endswith("}")


def test_branch_is_diamond_salmon():
    out = to_dot(_graph())
    assert 'guard [shape=diamond, fillcolor=lightsalmon, label="guard"];' in out


def test_case_edges_labeled_with_case_value():
    out = to_dot(_graph())
    assert 'decide_fail -> give_up [label="epic"];' in out
    # decide_fail's default also points at hard_fail, so the labels merge.
    assert 'decide_fail -> hard_fail [label="story|default"];' in out


def test_condition_and_default_edges_labeled():
    out = to_dot(_graph())
    assert 'guard -> decide_fail [label=">= 3"];' in out
    assert 'guard -> work [label="default"];' in out


def test_terminal_and_fail_styling():
    out = to_dot(_graph())
    assert 'done [fillcolor=lightgreen, label="done\\n(terminal)"];' in out
    assert 'hard_fail [fillcolor=lightcoral, label="hard_fail\\n(fail)"];' in out


def test_start_node_is_green_with_prefix():
    out = to_dot(_graph())
    # The start node is a branch, so it keeps the diamond shape but is recolored
    # green and gets the START prefix.
    assert (
        'decide_mode [shape=diamond, fillcolor=lightgreen, label="START\\ndecide_mode"];'
        in out
    )


def test_plain_agent_script_nodes_have_no_explicit_decl():
    # work/init_base are plain (default box, label == id) — emitted only via edges.
    out = to_dot(_graph())
    assert not any(ln.startswith("work [") for ln in _decls(out))
    assert not any(ln.startswith("init_base [") for ln in _decls(out))
    # ...but they still appear as edge endpoints.
    assert "work -> guard;" in out
    assert "init_base -> work;" in out


def test_unreachable_node_omitted():
    out = to_dot(_graph())
    assert "orphan" not in out


def test_pin_epic_collapses_branch_and_prunes_story():
    out = to_dot(_graph(), pins={"mode": "epic"})
    # decide_mode collapses to the single epic edge...
    assert 'decide_mode -> init_base [label="epic"];' in out
    assert "reset_plan" not in out  # story entry pruned
    # ...and the second mode branch likewise collapses, pruning the story terminal.
    assert 'decide_fail -> give_up [label="epic"];' in out
    assert "hard_fail" not in out
    assert "give_up" in out
    # Nothing story-flavored survives anywhere.
    assert "story" not in out


def test_pin_story_collapses_branch_and_prunes_epic():
    out = to_dot(_graph(), pins={"mode": "story"})
    assert 'decide_mode -> reset_plan [label="story"];' in out
    assert "init_base" not in out
    assert 'decide_fail -> hard_fail [label="story"];' in out
    assert "give_up" not in out
    assert 'hard_fail [fillcolor=lightcoral, label="hard_fail\\n(fail)"];' in out


def test_unpinned_branch_keeps_all_edges():
    out = to_dot(_graph())
    # Without a pin, the mode branch shows both cases; its default coincides with the
    # story case's target, so those two labels merge into one edge.
    assert 'decide_mode -> init_base [label="epic"];' in out
    assert 'decide_mode -> reset_plan [label="story|default"];' in out


def test_leaf_truncates_outgoing_edges_and_prunes_beyond():
    # Make `give_up` a leaf: it still appears as an edge target, but its edge to
    # `done` is suppressed and `done` is no longer reachable through it.
    out = to_dot(_graph(), pins={"mode": "epic"}, leaves={"give_up"})
    assert 'decide_fail -> give_up [label="epic"];' in out  # rendered as a dead-end
    assert "give_up -> done;" not in out  # outgoing edge suppressed
    assert "done" not in out  # only reachable via give_up in epic mode → pruned


def test_name_override():
    out = to_dot(_graph(), name="epic_mode")
    assert out.startswith("digraph epic_mode {")


def test_deterministic_output():
    g = _graph()
    assert to_dot(g) == to_dot(g)
    # All node declarations precede all edges in the document.
    out = to_dot(g)
    assert out.index('guard [shape=diamond') < out.index(" -> ")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
