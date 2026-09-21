"""The tracked `.dot` diagrams in `workflows/docs/` render exactly what their registry declares.

Each is generated output — `workhorse.pyflow.dot.to_dot` over `registry_graphs(registry)` —
not a hand drawing, and each workflow's console script exposes a `dot` subcommand that
reproduces it. Nothing else keeps a tracked `.dot` in step with the flows a registry
actually declares, so a flow renamed, added, or removed drifts silently until this fails.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import workhorse_workflows
from workhorse.pyflow.dot import to_dot
from workhorse.pyflow.graph import registry_graphs
from workhorse.pyflow.registry import Registry
from workhorse_workflows.author.workflow import workflow as author_workflow
from workhorse_workflows.okf_builder.workflow import workflow as okf_builder_workflow

DOCS = Path(workhorse_workflows.__file__).parent.parent.parent / "docs"

REGISTRIES = (author_workflow, okf_builder_workflow)


@pytest.mark.parametrize("registry", REGISTRIES, ids=[r.name for r in REGISTRIES])
def test_tracked_dot_matches_the_registry_it_documents(registry: Registry) -> None:
    tracked = DOCS / f"{registry.name}.dot"
    expected = to_dot(registry_graphs(registry), name=registry.name)
    script = f"workhorse-{registry.name}"
    assert tracked.read_text() == expected, (
        f"{tracked} is stale: regenerate it with `uv run {script} dot -o {tracked}`"
    )
