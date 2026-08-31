from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import patch

from _fakes import StubRunner
from git import Repo
from ostler import Ostler
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows import author
from workhorse_workflows.author.epic_author import EpicAuthor
from workhorse_workflows.author.epic_author.nodes import validate_authored_epic
from workhorse_workflows.author.epic_author.schemas import EpicAuthorDone
from workhorse_workflows.author.workflow import workflow

ROADMAP = "docs/roadmaps/account-access.md"


def _planning_input(repo: Path) -> None:
    roadmap = repo / ROADMAP
    roadmap.parent.mkdir(parents=True)
    roadmap.write_text(
        "---\ntype: roadmap\ntitle: Account access\nstatus: approved\n---\n"
        "# Account access\n\n## User Journeys\n\nPeople sign in securely.\n",
        encoding="utf-8",
    )
    assert Ostler(repo).create_epic("sign-in", "Sign in").ok
    git = Repo(repo)
    git.index.add([ROADMAP, "docs/epics", ".agents/ids.json"])
    git.index.commit("planning input")


def _document_epic(repo: Path) -> None:
    okf = Ostler(repo)
    epic = okf.graph.epics[0]
    assert epic.epic_md is not None
    epic.epic_md.write_text(
        epic.epic_md.read_text(encoding="utf-8").replace(
            "## Seeds",
            "## User Outcome\n\nPeople can access their account.\n\n## Seeds",
        ),
        encoding="utf-8",
    )
    assert okf.add_seed(
        "sign-in",
        "credentials",
        status="researched",
        summary="Accept valid account credentials",
        meta={"layers": ["frontend", "backend"]},
    ).ok


class _Agent:
    def __init__(self, repo: Path, *, block_once: bool = False) -> None:
        self.repo = repo
        self.block_once = block_once
        self.calls: Counter[str] = Counter()
        self.args: dict[str, dict[str, Any]] = {}

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        self.calls[stem] += 1
        self.args[stem] = ctx.as_dict()
        if stem == "write-epic":
            if self.block_once and self.calls[stem] == 1:
                return "scripted", {"status": "blocked", "notes": "owner must decide"}
            _document_epic(self.repo)
            return "scripted", {"status": "complete", "notes": "documented"}
        if stem == "resolve-operator":
            return "scripted", {
                "decision": "escalated",
                "notes": "owner must decide",
                "tried": ["read the roadmap"],
            }
        raise AssertionError(stem)


def _env(tmp_path: Path, agent: _Agent) -> RunEnv:
    writer = ArtifactWriter("author-epic-author", tmp_path / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(author.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
        agent_runner=StubRunner(agent),
    )


def test_authors_only_the_explicit_epic_and_returns_document_evidence(
    repo: Path, tmp_path: Path
) -> None:
    _planning_input(repo)
    assert Ostler(repo).create_epic("recovery", "Recovery").ok
    git = Repo(repo)
    before = git.head.commit.hexsha
    agent = _Agent(repo)

    result = drive(
        EpicAuthor(epic="sign-in", roadmap=ROADMAP, repo_dir=str(repo)),
        _env(tmp_path, agent),
    )

    assert isinstance(result, EpicAuthorDone)
    assert result.epic.endswith("sign-in")
    assert result.seed_count == 1
    assert agent.calls == {"write-epic": 1}
    assert agent.args["write-epic"]["epic"].endswith("sign-in")
    assert Ostler(repo).list("story") == []
    recovery = next(epic for epic in Ostler(repo).graph.epics if epic.name.endswith("recovery"))
    assert recovery.seeds == []
    assert git.active_branch.name == "main"
    assert git.head.commit.hexsha == before


def test_block_is_diagnosed_then_retries_the_same_epic(repo: Path, tmp_path: Path) -> None:
    _planning_input(repo)
    agent = _Agent(repo, block_once=True)

    with patch.object(pyflow_driver, "wait_for_answer", return_value=None):
        result = drive(
            EpicAuthor(epic="sign-in", roadmap=ROADMAP, repo_dir=str(repo)),
            _env(tmp_path, agent),
        )

    assert isinstance(result, EpicAuthorDone)
    assert result.operator_resolutions == 1
    assert agent.calls == {"write-epic": 2, "resolve-operator": 1}
    assert agent.args["resolve-operator"]["block_stage"] == "write-epic"


def test_document_validation_uses_epic_md_and_seed_evidence(repo: Path, logger: Any) -> None:
    _planning_input(repo)

    missing = validate_authored_epic(logger, "sign-in", repo_dir=str(repo))
    assert not missing.ok
    assert "no researched seeds" in missing.errors

    _document_epic(repo)
    documented = validate_authored_epic(logger, "sign-in", repo_dir=str(repo))

    assert documented.ok
    assert documented.seed_count == 1
    assert documented.epic_path.endswith("/epic.md")
