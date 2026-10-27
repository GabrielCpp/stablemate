"""The static read of `coder`: every prompt named, every state reachable, nothing drawn as `?`."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow.graph import registry_graphs
from workhorse.pyflow.preflight import preflight

from workhorse_workflows.coder.dev.flow import REVIEW_REFERENCES
from workhorse_workflows.coder.workflow import workflow


def test_the_static_read_names_every_prompt_the_coder_renders() -> None:
    graphs = registry_graphs(workflow)
    steps = [step for graph in graphs for node in graph.states for step in node.steps if step.kind == "agent"]
    assert [step for step in steps if step.dynamic] == []
    assert preflight(graphs, workflow.directory()) == []
    rendered = {step.name for step in steps}
    on_disk = {
        p.relative_to(workflow.directory()).as_posix()
        for p in workflow.directory().glob("*/prompts/*.md")
        if not p.name.startswith("_")
    }
    references = {f"dev/prompts/{Path(t).name}" for t in REVIEW_REFERENCES.values()}
    assert rendered | references == on_disk
    assert rendered.isdisjoint(references)
