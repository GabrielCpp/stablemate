"""Every transition of every author flow says why it is taken, so the diagram reads as decisions."""
from __future__ import annotations

from workhorse.pyflow.graph import registry_graphs
from workhorse_workflows.author.workflow import workflow


def test_every_author_transition_says_why() -> None:
    unlabelled = [
        f"{graph.label}: {node.name} -> {edge.target or 'END'}"
        for graph in registry_graphs(workflow)
        for node in graph.states
        for edge in node.edges
        if not edge.reason
    ]
    assert not unlabelled, "transitions with no reason:\n" + "\n".join(unlabelled)
