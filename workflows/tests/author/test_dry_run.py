"""A dry run walks the author's flat planner to its commit without a milestone or an agent."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from _fakes import StubRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv, stub_nodes

from workhorse_workflows import author
from workhorse_workflows.author.workflow import Author, workflow


def _no_agent(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("a dry run must not reach the agent")


def test_the_dry_run_completes_with_no_agent(repo: Path, tmp_path: Path) -> None:
    writer = ArtifactWriter("author", tmp_path / "runs", run_id="dry")
    env = RunEnv(
        writer=writer,
        workflow_dir=Path(author.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        agent_runner=StubRunner(_no_agent),
        nodes=stub_nodes(workflow.nodes),
        dry_run=True,
        agent_stubs=workflow.agent_stubs,
    )

    result = drive(Author(repo_dir=str(repo)), env)

    assert result is not None
