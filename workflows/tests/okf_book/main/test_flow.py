"""One confined owner per surface writes the book, and the run commits, checks, runs and reports it."""
from __future__ import annotations

import pytest
from workhorse.pyflow.graph import registry_graphs, state_graph
from workhorse.pyflow.preflight import preflight

from workhorse_workflows.okf_book.main import exercise_book_flow, reground_book_flow, write_book_flow
from workhorse_workflows.okf_book.workflow import OkfBook, workflow

@pytest.mark.parametrize(
    "machine",
    [OkfBook, exercise_book_flow.ExerciseBook, reground_book_flow.RegroundBook, write_book_flow.WriteBook],
)
def test_every_transition_says_why(
    machine: type[OkfBook] | type[exercise_book_flow.ExerciseBook] | type[reground_book_flow.RegroundBook] | type[write_book_flow.WriteBook],
) -> None:
    edges = [edge for node in state_graph(machine).states for edge in node.edges]
    assert edges
    assert [edge.target for edge in edges if not edge.reason] == []


def test_the_dry_run_reads_every_prompt_and_every_transition() -> None:
    graphs = registry_graphs(workflow)
    prompts = {step.name for graph in graphs for node in graph.states for step in node.steps if step.kind == "agent"}
    assert preflight(graphs, workflow.directory()) == []
    assert prompts == {p.relative_to(workflow.directory()).as_posix() for p in workflow.directory().glob("*/prompts/*.md") if not p.name.startswith("_")}
