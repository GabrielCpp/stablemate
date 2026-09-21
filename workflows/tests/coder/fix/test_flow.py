"""End-to-end tests for the `fix` flow — the standalone backlog drain."""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.fix.flow import MAX_FIX_LAPS, Fix
from workhorse_workflows.coder.shared import commits
from workhorse_workflows.coder.shared.backlog import mark_fix_blocked, prune_fix_item
from workhorse_workflows.kit.git import commit_all

BULLET = "widget-pagination"
TEXT = "the widget list does not paginate"
SLUG = "the-widget-list-does-not-paginate"
STORY_REL = f"docs/epics/0001-fixes/stories/{SLUG}"

BACKLOG = f"""# Backlog

## Filed by coder

- [{BULLET}] {TEXT}
"""

RED_MAKEFILE = "lint:\n\t@echo 'pagination.go:1: undefined: pageSize'; exit 1\n"




@pytest.fixture
def docs(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """The docs repo, carrying a backlog with one drainable item and nothing else."""
    write(repo / "docs" / "backlog.md", BACKLOG)
    return repo


@pytest.fixture
def workspace(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    ambient: dict[str, str],
) -> dict[str, Path]:
    """Two real code repos and the workspace file that names them, outside the docs tree."""
    root = tmp_path / "ws"
    repos: dict[str, Path] = {}
    for name in ("api", "web"):
        path = root / name
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")
        write(path / "README.md", f"# {name}\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", "Initial commit")
        repos[name] = path
    write(
        root / "acme.code-workspace",
        json.dumps({"folders": [{"name": n, "path": n} for n in repos]}),
    )
    ambient["workspace_file"] = str(root / "acme.code-workspace")
    return repos




class _Agent:
    """The flow's three prompts plus the `docs` sub-flow's three, scripted on the flow's arms."""

    def __init__(
        self,
        workspace: dict[str, Path],
        *,
        impl_blocked: int = 0,
        gate_red: int = 0,
        qa_fails: int = 0,
        apply_blocked: int = 0,
        review_blocks: bool = False,
        explode: set[str] | None = None,
    ) -> None:
        self.workspace = workspace
        self.impl_blocked = impl_blocked
        self.gate_red = gate_red
        self.qa_fails = qa_fails
        self.apply_blocked = apply_blocked
        self.review_blocks = review_blocks
        self.explode = explode or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []


    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        if stem in self.explode:
            raise RuntimeError(f"killed during {stem}")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]


    def _fix_item(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Write the change, so the gates and the commit have something to find."""
        if nth <= self.impl_blocked:
            return {
                "status": "blocked",
                "notes": "the page size is a product decision nobody has made",
            }
        repo = self.workspace["api"]
        (repo / "pagination.go").write_text(f"// pass {nth}\n", encoding="utf-8")
        makefile = repo / "Makefile"
        if nth <= self.gate_red:
            makefile.write_text(RED_MAKEFILE, encoding="utf-8")
        elif makefile.exists():
            makefile.unlink()
        message = commits.message(
            "fix",
            commits.scope(repo.name),
            TEXT,
            epic=str(data["epic"]),
            story=str(data["story_id"]),
        )
        commit_all(repo, message)
        return {"status": "done", "notes": f"paginated the widget list on pass {nth}"}

    def _fix_item_repair(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The repair lap: the same writer, counted as one pass further on."""
        return self._fix_item(data, nth + self.counts()["fix-item"])

    def _qa_fix_item(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.qa_fails:
            return {"status": "failed", "notes": f"page two is still empty (check {nth})"}
        return {"status": "passed", "notes": "pagination works"}

    def _apply_qa_fixes(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.apply_blocked:
            return {"status": "blocked", "notes": "QA wants a page size nobody has picked"}
        return {"status": "passed", "notes": "widened the page window"}


    def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        story_path = Path(str(data["story_path"]))
        docs_dir = next(parent for parent in story_path.parents if parent.name == "docs")
        feature = docs_dir / "features/api/concepts/widget.md"
        feature.parent.mkdir(parents=True, exist_ok=True)
        feature.write_text(
            "---\ntype: concept\nslug: widget\ntitle: Widget\n---\n"
            "# Widget\n\n- code: `repo://api/pagination.go`\n",
            encoding="utf-8",
        )
        return {
            "status": "documented",
            "nodes": ["docs/features/api/concepts/widget.md"],
            "notes": f"documented on pass {nth}",
        }

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The author's say on a documentation block, which this fake declines to give."""
        return {"decision": "escalated", "summary": "no answer to give"}

    def _review_story_documentation(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.review_blocks:
            return {"status": "blocked", "notes": "this change cannot be described as built"}
        return {"status": "approved", "notes": "reads as built"}


def _answers(seen: list[str]) -> Callable[..., None]:
    """A stand-in for the human the `Await` is waiting on."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(
            "STATUS: ANSWERED\n\nTwenty per page, as the widget grid already does.\n",
            encoding="utf-8",
        )

    return answered


def _backlog(docs: Path) -> str:
    return (docs / "docs" / "backlog.md").read_text(encoding="utf-8")


def _output(run_env: RunEnv, node: Any) -> dict[str, Any]:
    """A node's recorded output — the artifact, not the return value the flow saw."""
    path = run_env.writer.run_dir / node.__name__ / "output.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _log_of(repo: Path) -> list[str]:
    return subprocess.run(
        ["git", "log", "--format=%s"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.split("\n")


def _assert_agent_story_commit(repo: Path, agent: _Agent) -> None:
    story_id = str(agent.args_for("fix-item")[0]["story_id"])
    subject = _log_of(repo)[0]
    assert subject.startswith("fix(api): ")
    assert story_id not in subject


def _branch_of(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()




def test_one_item_is_seeded_fixed_checked_pruned_and_committed(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A whole iteration, and the second draw that ends the run."""
    agent = _Agent(workspace)
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    assert result.has_fix is False, result
    assert "no drainable bullet" in result.reason, result

    assert agent.counts() == {
        "fix-item": 1,
        "qa-fix-item": 1,
        "document-story": 1,
        "review-story-documentation": 1,
    }, agent.counts()

    story = (docs / STORY_REL / "story.md").read_text(encoding="utf-8")
    assert f"- {TEXT}" in story, story
    assert BULLET in story, story
    assert "## Non-Functional Acceptance Criteria\n\n(none)" in story, story
    assert (
        "## Technical Notes\n\nNo prior implementation reference exists." in story
    ), story

    assert BULLET not in _backlog(docs), _backlog(docs)
    assert "## Filed by coder" in _backlog(docs)

    story_id = str(agent.args_for("fix-item")[0]["story_id"])
    subject = _log_of(workspace["api"])[0]
    assert subject.startswith("fix(api): ")
    assert story_id not in subject
    body = subprocess.run(
        ["git", "log", "-1", "--format=%b"],
        cwd=workspace["api"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert f"Story: {story_id}" in body
    assert (workspace["api"] / "pagination.go").is_file()


def test_the_first_pass_is_handed_the_item_and_no_gate_report_at_all(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`fix-item.md` is the first-lap prompt, and a first lap has no gate to report."""
    agent = _Agent(workspace)

    drive_flow(Fix(), env(), agent)

    first = agent.args_for("fix-item")[0]
    assert first["bullet_text"] == TEXT, first
    assert first["story_path"].endswith("story.md"), first
    assert "gate_report" not in first, first
    assert first["operator_context"] == "", first
    assert agent.counts()["fix-item-repair"] == 0, agent.counts()


def test_the_drain_keeps_going_until_the_section_is_empty(
    docs: Path,
    workspace: dict[str, Path],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`commit`'s next is the draw, so two items are two full iterations in one run."""
    write(
        docs / "docs" / "backlog.md",
        BACKLOG + "- [mobile-pagination] the mobile widget list does not paginate\n",
    )
    agent = _Agent(workspace)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["fix-item"] == 2, agent.counts()
    assert agent.counts()["qa-fix-item"] == 2, agent.counts()
    assert "widget-pagination" not in _backlog(docs), _backlog(docs)
    assert "mobile-pagination" not in _backlog(docs), _backlog(docs)
    assert len([line for line in _log_of(workspace["api"]) if line.startswith("fix(api):")]) == 2




def test_a_red_gate_buys_a_repair_lap_and_hands_the_turn_its_output(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The deterministic half of the collapsed split: git names the repos, `make` judges them."""
    agent = _Agent(workspace, gate_red=1)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["fix-item"] == 1, agent.counts()
    assert agent.counts()["fix-item-repair"] == 1, agent.counts()

    lap = agent.args_for("fix-item-repair")[0]["gate_report"]
    assert "Repair lap 1" in lap, lap
    assert "make lint" in lap, lap
    assert "undefined: pageSize" in lap, lap
    assert str(workspace["api"]) in lap, lap

    assert BULLET not in _backlog(docs), _backlog(docs)


def test_a_gate_still_red_when_the_laps_run_out_parks_rather_than_giving_up(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A spent repair budget is a block, not a `WorkflowFailed` — AGENTS.md's rule, here."""
    agent = _Agent(workspace, gate_red=MAX_FIX_LAPS)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result

    (gate,) = seen
    assert "lint gate on the fix-drain item" in gate, gate
    assert f"after {MAX_FIX_LAPS} repair lap(s)" in gate, gate
    assert "undefined: pageSize" in gate, gate

    counts = agent.counts()
    assert counts["fix-item"] + counts["fix-item-repair"] == MAX_FIX_LAPS + 1, counts
    assert "Twenty per page" in agent.args_for("fix-item-repair")[-1]["operator_context"]
    assert BULLET not in _backlog(docs), _backlog(docs)


def test_an_untouched_repo_is_neither_gated_nor_committed(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The targets are git's account of the change, not the workspace manifest's list."""
    (workspace["web"] / "Makefile").write_text(RED_MAKEFILE, encoding="utf-8")
    subprocess.run(
        ["git", "add", "Makefile"], cwd=workspace["web"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-qm", "Add a lint target that fails"],
        cwd=workspace["web"],
        check=True,
        capture_output=True,
    )
    agent = _Agent(workspace)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["fix-item"] == 1, agent.counts()
    assert not any(line.startswith("fix(web):") for line in _log_of(workspace["web"]))
    _assert_agent_story_commit(workspace["api"], agent)


def test_the_commits_land_on_the_branch_the_repos_were_already_on(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """No story branch, no fix branch — "commit this one drained item onto the CURRENT branch"."""
    agent = _Agent(workspace)

    drive_flow(Fix(), env(), agent)

    assert _branch_of(workspace["api"]) == "main"
    assert _branch_of(docs) == "main"
    _assert_agent_story_commit(workspace["api"], agent)




def test_qa_gets_exactly_one_retry_and_the_fixer_is_handed_the_first_verdict(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`check → apply once → recheck`, and the notes that cross between the three."""
    agent = _Agent(workspace, qa_fails=1)
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    assert result.has_fix is False, result
    assert agent.counts()["qa-fix-item"] == 2, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
    assert agent.args_for("apply-qa-fixes")[0]["qa_notes"] == "page two is still empty (check 1)"

    assert BULLET not in _backlog(docs), _backlog(docs)
    assert _output(run_env, prune_fix_item)["pruned"] is True


def test_a_second_failing_check_flags_rather_than_retrying_again(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The retry is one, not a loop — a QA verdict the drain believes never escalates."""
    agent = _Agent(workspace, qa_fails=2)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["qa-fix-item"] == 2, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()

    line = next(ln for ln in _backlog(docs).splitlines() if BULLET in ln)
    assert "(blocked" in line, line
    assert "QA still failing after one retry" in line, line
    assert BULLET in _backlog(docs)


def test_a_retry_that_says_it_cannot_parks_instead_of_rechecking_nothing(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`apply_once`'s verdict was parsed and dropped, so a blocked fixer was rechecked anyway."""
    agent = _Agent(workspace, qa_fails=1, apply_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result

    (gate,) = seen
    assert "QA wants a page size nobody has picked" in gate, gate

    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
    assert agent.counts()["fix-item"] == 2, agent.counts()
    assert agent.counts()["qa-fix-item"] == 2, agent.counts()
    assert BULLET not in _backlog(docs), _backlog(docs)


def test_an_implementation_turn_that_says_it_cannot_parks_instead_of_qa_ing_nothing(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The fifth lane's copy of the dropped-verdict bug, from the outside."""
    agent = _Agent(workspace, impl_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result

    (gate,) = seen
    assert "the page size is a product decision nobody has made" in gate, gate
    assert "implementation stage, the fix-drain implementation turn" in gate, gate
    assert SLUG in gate, gate

    assert agent.counts()["fix-item"] == 2, agent.counts()
    assert agent.counts()["qa-fix-item"] == 1, agent.counts()
    retried = agent.args_for("fix-item")[1]
    assert "Twenty per page" in retried["operator_context"], retried

    assert BULLET not in _backlog(docs), _backlog(docs)
    _assert_agent_story_commit(workspace["api"], agent)


def test_a_blocked_item_is_flagged_and_the_next_draw_skips_it(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The annotated bullet is what stops the very next draw from picking it up again."""
    agent = _Agent(workspace, qa_fails=2)
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    assert result.has_fix is False, result
    assert agent.counts()["fix-item"] == 1, agent.counts()
    assert _output(run_env, mark_fix_blocked)["marked"] is True




def test_the_docs_sub_flow_runs_for_real_and_its_verdict_gates_the_commit(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`document` is a handoff, so the whole `docs` flow runs per drained item."""
    agent = _Agent(workspace)

    drive_flow(Fix(), env(), agent)

    assert agent.counts()["document-story"] == 1, agent.counts()
    assert agent.counts()["review-story-documentation"] == 1, agent.counts()
    assert agent.args_for("document-story")[0]["story_path"].endswith("story.md")
    _assert_agent_story_commit(workspace["api"], agent)


def test_documentation_that_cannot_converge_preserves_the_agent_commit(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blocked reviewer is the sub-flow saying the story cannot be documented as it stands."""
    agent = _Agent(workspace, review_blocks=True)

    with pytest.raises(WorkflowFailed):
        drive_flow(Fix(), env(), agent)

    _assert_agent_story_commit(workspace["api"], agent)
    assert BULLET not in _backlog(docs), _backlog(docs)




def test_a_run_killed_mid_check_resumes_at_the_check(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The checkpoint is written before a state runs, so the drawn item survives the kill."""
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during qa-fix-item"):
        drive_flow(Fix(), run_env, _Agent(workspace, explode={"qa-fix-item"}))

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "check", resume
    assert resume.flow == "Fix", resume

    agent = _Agent(workspace)
    result = drive_flow(Fix(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.has_fix is False, result
    assert "fix-item" not in agent.counts(), agent.counts()
    assert agent.counts()["qa-fix-item"] == 1, agent.counts()
    assert BULLET not in _backlog(docs), _backlog(docs)
