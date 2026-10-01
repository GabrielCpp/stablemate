"""What a static read of a flow graph shows is wrong before a run starts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from jinja2 import Environment, TemplateSyntaxError

from workhorse.pyflow.graph import FlowGraph


def preflight(graphs: Sequence[FlowGraph], workflow_dir: Path | None = None) -> list[str]:
    """Everything wrong with these machines that a static read can see."""
    problems: list[str] = []
    for graph in graphs:
        where = f"flow '{graph.label}'"
        names = {node.name for node in graph.states}
        if graph.start not in names:
            problems.append(
                f"{where}: start state '{graph.start}' does not exist — "
                f"known states: {', '.join(sorted(names)) or '(none)'}"
            )
        if not any(node.terminal for node in graph.states):
            problems.append(
                f"{where}: no state returns Done(...) — the machine cannot terminate"
            )
        for node in graph.states:
            if node.opaque:
                problems.append(
                    f"{where}: cannot read the source of state '{node.name}' — "
                    "its transitions, prompts and reachability are unchecked"
                )
            for step in node.steps:
                if step.kind == "agent" and step.dynamic:
                    problems.append(
                        f"{where}: state '{node.name}' renders a prompt this read "
                        f"cannot name ({step.summary}) — it is checked by nothing"
                    )
            for edge in node.edges:
                if edge.dangling:
                    problems.append(
                        f"{where}: state '{node.name}' transitions to "
                        f"'self.{edge.target}', which is not a state"
                    )
        for dead in graph.unreachable():
            problems.append(
                f"{where}: state '{dead}' is unreachable from '{graph.start}'"
            )
        problems.extend(_inline_problems(graph, where))
        if workflow_dir is not None:
            problems.extend(_missing_prompts(graph, where, workflow_dir))
    return problems


def _inline_problems(graph: FlowGraph, where: str) -> list[str]:
    """What is wrong with the prompts a state writes in its own source: a label two turns share, and a body Jinja cannot parse."""
    problems: list[str] = []
    steps = [
        (node.name, step)
        for node in graph.states
        for step in node.steps
        if step.kind == "agent" and step.inline
    ]
    counts = Counter(step.name for _, step in steps)
    for label, count in sorted(counts.items()):
        if count > 1:
            problems.append(
                f"{where}: {count} agent turns are labelled '{label}' — a label is a "
                "node id, so they would write the same run directory and output.json"
            )
    for state, step in steps:
        try:
            Environment().parse(step.text)
        except TemplateSyntaxError as exc:
            problems.append(
                f"{where}: state '{state}' writes the prompt labelled "
                f"'{step.name}', which is not valid Jinja: {exc}"
            )
    return problems


def _missing_prompts(graph: FlowGraph, where: str, workflow_dir: Path) -> list[str]:
    """Prompt paths that do not resolve, the same way `templates.render` resolves them."""
    missing: list[str] = []
    for state, prompt in graph.prompts():
        path = Path(prompt)
        resolved = path if path.is_absolute() else workflow_dir / path
        if not resolved.is_file():
            missing.append(f"{where}: state '{state}' renders '{prompt}', which does not exist")
    return missing


__all__ = ["preflight"]
