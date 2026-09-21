"""End-to-end tests for `coder`'s main graph — the epic/story loop itself."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import Blueprint, Done, Workflow, WorkflowFailed
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.kit import commit_all, commit_paths, is_ancestor
from workhorse_workflows.coder.main import flow as coder_main
from workhorse_workflows.coder.shared import commits
from workhorse_workflows.coder.shared.schemas.backlog import FixPick
from workhorse_workflows.coder.shared.ci import poll_pr_checks
from workhorse_workflows.coder.main.nodes.pr import (
    _epic_pr_title,
    flag_ci_failure,
    merge_pr,
    open_pr,
    open_story_pr,
)
from workhorse_workflows.coder.shared.queue import (
    BLOCKED_FILE,
    CLAIMED_FILE,
    SKIP_FILE,
    begin_run,
    branch_epic,
    branch_story,
    check_repos_clean,
    select_epic,
    stamp_story_passed,
)
from workhorse_workflows.coder.shared.story import prepare_story
from workhorse_workflows.coder.shared.schemas.ci import CiChecks, CiStatus
from workhorse_workflows.coder.shared.schemas.dev import DevResult
from workhorse_workflows.coder.shared.schemas.docs import DocsResult, DocsStatus
from workhorse_workflows.coder.shared.schemas.qa import (
    QaFlowResult,
    QaFlowStatus,
    QaResult,
)
from workhorse_workflows.coder.shared.schemas.pr import MergeOutcome
from workhorse_workflows.coder.shared.schemas.review import ReviewResult
from workhorse_workflows.coder.main import Coder

EPIC = "EPIC-1"
INDEX = f"""# Epics

The epic queue, front first.

- [{EPIC}]({EPIC}/epic.md) — Epic One
"""

STORY_MD = """---
type: story
---

# {title}

## Dependencies

(none)

## Fixtures

(none)

## Context

Users need a thing.

## Acceptance Criteria

- the thing exists

## Non-Functional Acceptance Criteria

- the thing is fast

## Technical Notes

- the thing is a function

## Implementation Status

- **Status**: {status}
"""

GAVE_UP = "QA FAILED after 3 QA-plan review revision attempts — needs manual review"

BULLET = "widget-pagination"
BULLET_TEXT = "the widget list does not paginate"
FIX_SLUG = "the-widget-list-does-not-paginate"
BACKLOG = f"""# Backlog

## Filed by coder

- [{BULLET}] {BULLET_TEXT}
"""

BLOCK_REASON = "the handler allows every origin when the allow-list is unset"




@pytest.fixture(autouse=True)
def _no_ambient_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both variables `resolve_github_token` falls back to, unset for every test here."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


@pytest.fixture
def epic(
    repo: Path,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> Callable[..., Path]:
    """An epic of N stories in the queue, committed — so the tree starts clean."""

    def _epic(count: int = 1, status: str = "Not started") -> Path:
        slugs = [f"STORY-{n}" for n in range(1, count + 1)]
        stories = "\n".join(f"### {slug}\n\n- title: Story {slug}\n" for slug in slugs)
        write(
            repo / "docs" / "epics" / EPIC / "epic.md",
            f"---\ntitle: Epic One\nstatus: active\n---\n\n# Epic One\n\n## Stories\n\n{stories}",
        )
        for slug in slugs:
            write(
                repo / "docs" / "epics" / EPIC / "stories" / slug / "story.md",
                STORY_MD.format(title=f"Story {slug}", status=status),
            )
        write(repo / "docs" / "epics" / "index.md", INDEX)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "Queue one epic")
        return repo

    return _epic


@pytest.fixture
def workspace(
    tmp_path: Path,
    repo: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    ambient: dict[str, str],
) -> Path:
    """A workspace file naming one code repo, for the drain's `resolve_impl_context`."""
    root = tmp_path / "ws"
    api = root / "api"
    api.mkdir(parents=True)
    git(api, "init", "-q", "-b", "main")
    write(api / "README.md", "# api\n")
    git(api, "add", "-A")
    git(api, "commit", "-qm", "Initial commit")
    write(root / "acme.code-workspace", json.dumps({"folders": [{"name": "api", "path": "api"}]}))
    ambient["workspace_file"] = str(root / "acme.code-workspace")
    return root




def _story_message(package: str, slug: str) -> str:
    """The subject a real dev agent is told to write, built from the shared helper."""
    return commits.message(
        "feat", commits.scope(package), f"story {slug}", epic=EPIC, story=slug
    )


class _StubFlow(Workflow):
    """Every keyword the graph's six handoffs pass, because `Workflow` forbids extras."""

    story: str = ""
    docs_path: str = ""
    epic: str = ""
    preexisting: tuple[str, ...] = ()
    operator_mode: str = ""
    target_env: str = ""
    sandbox: bool = False
    triage_scope: int = 0
    repo: str = ""
    branch: str = ""
    session_turns: int = 0
    inherited_turns: int = 0


class _Sub:
    """The six stand-ins, their call log, and the one file `dev` writes."""

    def __init__(
        self,
        repo: Path,
        *,
        changes: bool = True,
        leave_dirty: bool = False,
        dev_status: Literal["ready", "replan"] = "ready",
        docs_status: DocsStatus = "passed",
        docs_notes: str = "",
        docs_authored_nodes: list[str] | None = None,
        qa_status: QaFlowStatus = "passed",
        qa_statuses: list[QaFlowStatus] | None = None,
        qa_docs_recheck_required: bool = False,
        ci_status: CiStatus = "passed",
        explode: set[str] | None = None,
    ) -> None:
        self.repo = repo
        self.changes = changes
        self.leave_dirty = leave_dirty
        self.dev_status: Literal["ready", "replan"] = dev_status
        self.docs_status: DocsStatus = docs_status
        self.docs_notes = docs_notes
        self.docs_authored_nodes = docs_authored_nodes or []
        self.qa_status: QaFlowStatus = qa_status
        self.qa_statuses: list[QaFlowStatus] = qa_statuses or []
        self.qa_docs_recheck_required = qa_docs_recheck_required
        self.ci_status: CiStatus = ci_status
        self.explode = explode or set()
        self.calls: list[str] = []
        self.seen: list[_StubFlow] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> _Sub:
        for name, reply in (
            ("Dev", self._dev),
            ("Review", self._review),
            ("Docs", self._docs),
            ("Qa", self._qa),
            ("FixCi", self._fix_ci),
            ("Fix", self._fix),
        ):
            monkeypatch.setattr(coder_main, name, self._flow(name, reply))
        return self

    def _flow(self, name: str, reply: Callable[[_StubFlow], Any]) -> type:
        """A real `Workflow` subclass named for the flow it stands in for."""
        calls, explode, seen = self.calls, self.explode, self.seen

        def start(child: _StubFlow) -> Done:
            calls.append(name)
            seen.append(child)
            if name in explode:
                raise RuntimeError(f"killed during {name}")
            return Done(reply(child))

        return type(name, (_StubFlow,), {"start": start})

    def calls_to(self, name: str) -> list[_StubFlow]:
        return [c for n, c in zip(self.calls, self.seen, strict=True) if n == name]


    def _dev(self, child: _StubFlow) -> DevResult:
        if self.changes:
            path = self.repo / "src" / f"{child.story}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {child.story}\n", encoding="utf-8")
            if not self.leave_dirty:
                commit_paths(
                    self.repo,
                    _story_message(self.repo.name, child.story),
                    f"src/{child.story}.py",
                )
        return DevResult(status=self.dev_status, operator_notes="rescope to the epic")

    def _review(self, child: _StubFlow) -> ReviewResult:
        return ReviewResult(notes="")

    def _docs(self, child: _StubFlow) -> DocsResult:
        return DocsResult(
            status=self.docs_status,
            notes=self.docs_notes,
            authored_nodes=self.docs_authored_nodes,
        )

    def _qa(self, child: _StubFlow) -> QaFlowResult:
        status = self.qa_statuses.pop(0) if self.qa_statuses else self.qa_status
        return QaFlowResult(
            status=status,
            qa=QaResult(status="passed" if status == "passed" else "failed"),
            qa_rework=1,
            triage_scope=child.triage_scope,
            operator_notes="",
            docs_recheck_required=self.qa_docs_recheck_required,
        )

    def _fix_ci(self, child: _StubFlow) -> CiChecks:
        return CiChecks(status=self.ci_status, summary="")

    def _fix(self, child: _StubFlow) -> FixPick:
        """The drain, run to dry — which is the only shape `Fix` ever returns to a parent."""
        return FixPick(has_fix=False, reason="the backlog is dry")




class _Agent:
    """The graph's own six prompts."""

    def __init__(
        self, *, services: list[dict[str, Any]] | None = None, settle: str = ""
    ) -> None:
        self.services = services if services is not None else []
        self.settle = settle
        self.calls: list[str] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        handler = getattr(self, f"_{stem.replace('-', '_')}", None)
        assert handler is not None, f"unexpected agent turn: {stem}"
        return f"(scripted) {node.prompt}", handler(data)

    def _plan_story(self, data: dict[str, Any]) -> dict[str, Any]:
        """Write the plan the drain's `resolve_impl_context` then decodes for real."""
        spec = Path(data["spec_dir"])
        spec.mkdir(parents=True, exist_ok=True)
        (spec / "plan-context.json").write_text(
            json.dumps({"services": self.services, "implementation_order": []}, indent=2) + "\n",
            encoding="utf-8",
        )
        root = Path.cwd()
        commit_all(root, commits.message("docs", commits.scope(root.name), "plan a drained item"))
        return {"status": "done", "summary": "one AC, one fix"}

    def _qa_fix_item(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"status": "passed", "notes": ""}

    def _settle_worktree(self, data: dict[str, Any]) -> dict[str, Any]:
        """The one lap a story gets to record work it left on disk."""
        assert self.settle, "unexpected settle lap — the story committed nothing"
        if self.settle == "commit":
            root = Path.cwd()
            slug = data["story_slug"]
            commit_all(root, _story_message(root.name, slug))
            return {"status": "settled", "notes": f"committed {slug}"}
        if self.settle == "claimed":
            return {"status": "settled", "notes": "recorded everything the story wrote"}
        return {"status": self.settle, "notes": "the tree holds an edit I did not write"}




def _output(run_env: RunEnv, node: Any) -> Any:
    return json.loads((run_env.writer.run_dir / node.__name__ / "output.json").read_text())


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _dirty(repo: Path) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _subjects(repo: Path) -> list[str]:
    return subprocess.run(
        ["git", "log", "--format=%s"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.splitlines()




def test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole loop in one pass: queue → story → PR → CI → merge → empty queue."""
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)
    run_env = env()

    result = drive_flow(Coder(), run_env, _Agent())

    assert result.has_epic is False, result
    assert sub.calls == ["Dev", "Review", "Docs", "Qa", "Fix"], sub.calls
    assert _output(run_env, check_repos_clean)["clean"] is True
    assert _output(run_env, stamp_story_passed)["stamped"] is True
    assert _dirty(repo) == "", _dirty(repo)
    assert (repo / "src" / "STORY-1.py").is_file()
    assert EPIC not in (repo / "docs" / "epics" / "index.md").read_text(encoding="utf-8")
    assert _output(run_env, select_epic)["reason"], _output(run_env, select_epic)


def test_no_lane_is_handed_a_conversation_but_the_turn_count_threads(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The graph names no conversation; it only carries how much of the budget is spent."""
    repo = epic()

    class _ChainingSub(_Sub):
        def _dev(self, child: _StubFlow) -> DevResult:
            super()._dev(child)
            return DevResult(status="ready", session_turns=3)

    sub = _ChainingSub(repo).install(monkeypatch)

    drive_flow(Coder(), env(), _Agent())

    assert sub.calls_to("Review")[0].inherited_turns == 3
    assert "session_id" not in _StubFlow.model_fields


def test_a_qa_mutation_requires_final_documentation_before_commit(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The QA result's durable taint controls the second Docs handoff."""
    repo = epic()
    sub = _Sub(repo, qa_docs_recheck_required=True).install(monkeypatch)

    drive_flow(Coder(), env(), _Agent())

    assert sub.calls == ["Dev", "Review", "Docs", "Qa", "Fix", "Docs"], sub.calls
    assert "feat(acme): story STORY-1" in _subjects(repo), _subjects(repo)


def test_the_story_and_its_status_stamp_commit_as_conventional_commits(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The subjects the coder writes into somebody else's repo are release inputs."""
    repo = epic()
    _Sub(repo).install(monkeypatch)

    drive_flow(Coder(), env(), _Agent())

    subjects = _subjects(repo)
    story = next(s for s in subjects if s.startswith("feat("))
    stamp = next(s for s in subjects if "QA passed" in s)
    assert story == "feat(acme): story STORY-1", story
    assert stamp.startswith("docs(acme): "), stamp
    bodies = subprocess.run(
        ["git", "log", "--format=%b"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert f"Epic: {EPIC}" in bodies, bodies
    assert "Story: STORY-1" in bodies, bodies


def test_the_graph_records_the_epic_branch_it_cut_in_the_run_dir(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`branch_epic` can only recognise its own branch on a later visit if the graph hands it the run dir — and a node that takes `run_dir` but is never given one is silent, not an error, so the ledger is asserted from the graph rather than from the node."""
    repo = epic()
    _Sub(repo).install(monkeypatch)
    run_env = env()

    drive_flow(Coder(), run_env, _Agent())

    ledger = run_env.writer.run_dir / CLAIMED_FILE
    assert ledger.read_text(encoding="utf-8").split() == [f"feat/{EPIC}"]


def test_a_fresh_run_drops_the_skip_state_a_previous_run_left_in_the_run_dir(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run dir outlives the run that made it, and the two skip files must not."""
    repo = epic()
    _Sub(repo).install(monkeypatch)
    run_env = env()
    run_env.writer.run_dir.mkdir(parents=True, exist_ok=True)
    (run_env.writer.run_dir / BLOCKED_FILE).write_text(f"{EPIC}\n", encoding="utf-8")
    (run_env.writer.run_dir / SKIP_FILE).write_text("STORY-1\n", encoding="utf-8")

    result = drive_flow(Coder(), run_env, _Agent())

    assert _output(run_env, begin_run)["cleared"] == [BLOCKED_FILE, SKIP_FILE]
    assert (repo / "src" / "STORY-1.py").is_file()
    assert "set aside" not in _output(run_env, select_epic)["reason"]
    assert result.has_epic is False, result


def test_the_story_is_stamped_and_the_next_selection_reads_it_as_done(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What actually terminates the story loop: the status the commit stamps."""
    repo = epic()
    _Sub(repo).install(monkeypatch)

    drive_flow(Coder(), env(), _Agent())

    story = (repo / "docs" / "epics" / EPIC / "stories" / "STORY-1" / "story.md").read_text(
        encoding="utf-8"
    )
    assert "status: QA passed" in story, story
    assert "- **Status**: QA passed" in story, story


def test_the_pr_cluster_passes_through_offline_and_still_advances_the_queue(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`should_gate` is read off the *epic*, not off whether GitHub could be reached."""
    repo = epic()
    _Sub(repo).install(monkeypatch)
    run_env = env()

    drive_flow(Coder(), run_env, _Agent())

    assert _output(run_env, open_pr)["should_gate"] is True
    assert _output(run_env, open_pr)["ci_epic"] == EPIC
    assert _output(run_env, poll_pr_checks)["status"] == "unavailable"
    assert _output(run_env, merge_pr)["merge_status"] == "unavailable"
    assert _head(repo) == f"feat/{EPIC}"


def test_an_epic_branch_carrying_a_set_aside_epic_declines_to_open_a_pr(
    epic: Callable[..., Path],
    logger: logging.Logger,
    tmp_path: Path,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """`flag_epic_blocked`'s "NOT merged" promise, kept at the only boundary that can keep it."""
    repo = epic()
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    git(repo, "checkout", "-q", "-b", "feat/EPIC-0")
    (repo / "failed.txt").write_text("half-built\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "EPIC-0: story [QA FAILED — needs manual review]")
    git(repo, "checkout", "-q", "-b", f"feat/{EPIC}")
    git(repo, "checkout", "-q", "-b", "feat/EPIC-9", "main")
    (repo / "elsewhere.txt").write_text("other work\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "EPIC-9: story")
    git(repo, "branch", "feat/EPIC-8", "main")
    git(repo, "checkout", "-q", f"feat/{EPIC}")

    (run_dir / BLOCKED_FILE).write_text("EPIC-0\n", encoding="utf-8")
    carried = open_pr(logger, epic=EPIC, base_branch="main", run_dir=str(run_dir),
                      repo_dir=str(repo))

    assert carried.should_gate is False
    assert carried.ci_epic == ""
    assert git(repo, "rev-parse", "--verify", f"feat/{EPIC}").returncode == 0

    (run_dir / BLOCKED_FILE).write_text("EPIC-9\nEPIC-8\n", encoding="utf-8")
    unrelated = open_pr(logger, epic=EPIC, base_branch="main", run_dir=str(run_dir),
                        repo_dir=str(repo))

    assert unrelated.should_gate is True, "an unrelated set-aside epic must not block the queue"
    assert unrelated.ci_epic == EPIC




def test_retrying_at_the_same_commit_continues_and_leaves_no_refs_behind(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """A retry after a failure *is* a second attempt at an unchanged HEAD."""
    repo = epic()

    for _ in range(3):
        result = branch_epic(logger, epic=EPIC, repo_dir=str(repo))
        assert result.epic_branch == f"feat/{EPIC}"

    assert _head(repo) == f"feat/{EPIC}"
    branches = git(repo, "branch", "--format=%(refname:short)").stdout.split()
    assert not [b for b in branches if b.startswith("archive/")], branches


def test_a_resumed_epic_branch_keeps_the_commits_it_already_made(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
) -> None:
    """The point of not renaming aside."""
    repo = epic()
    branch_epic(logger, epic=EPIC, repo_dir=str(repo))
    write(repo / "src" / "done.txt", "story one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "story one")
    landed = git(repo, "rev-parse", "HEAD").stdout.strip()

    branch_epic(logger, epic=EPIC, repo_dir=str(repo))

    assert git(repo, "rev-parse", "HEAD").stdout.strip() == landed
    assert (repo / "src" / "done.txt").exists()


def test_a_branch_another_working_tree_holds_is_refused_by_name(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    tmp_path: Path,
) -> None:
    """The case concurrency creates."""
    repo = epic()
    other = tmp_path / "other-run"
    git(repo, "worktree", "add", "--detach", "-q", str(other))
    git(other, "checkout", "-q", "-b", f"feat/{EPIC}")

    with pytest.raises(WorkflowFailed, match="another working tree"):
        branch_epic(logger, epic=EPIC, repo_dir=str(repo))


def test_unmerged_work_nobody_claimed_is_refused_rather_than_renamed(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
) -> None:
    """Archival renamed this aside silently."""
    repo = epic()
    base = _head(repo)
    git(repo, "checkout", "-q", "-b", f"feat/{EPIC}")
    write(repo / "src" / "someone-elses.txt", "unmerged\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "work in progress")
    git(repo, "checkout", "-q", base)

    with pytest.raises(WorkflowFailed, match="not in"):
        branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo))

    branches = git(repo, "branch", "--format=%(refname:short)").stdout.split()
    assert f"feat/{EPIC}" in branches
    assert not [b for b in branches if b.startswith("archive/")], branches


def test_a_merged_epic_branch_is_reused_rather_than_refused(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """The ordinary case after an epic ships: the branch is still lying around, and it holds nothing the base does not."""
    repo = epic()
    base = _head(repo)
    git(repo, "branch", f"feat/{EPIC}", base)

    result = branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo))

    assert result.epic_branch == f"feat/{EPIC}"
    assert _head(repo) == f"feat/{EPIC}"


def test_a_squash_merged_branch_counts_as_merged(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
) -> None:
    """Squash is the default merge on most repos, and it leaves a branch whose commits are ancestors of nothing — so an ancestry-only test would call every landed epic 'unmerged' and refuse it, which is a queue that stops needing a human every time."""
    repo = epic()
    base = _head(repo)
    git(repo, "checkout", "-q", "-b", f"feat/{EPIC}")
    write(repo / "src" / "shipped.txt", "content\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the epic")
    git(repo, "checkout", "-q", base)
    git(repo, "merge", "-q", "--squash", f"feat/{EPIC}")
    git(repo, "commit", "-qm", "squashed epic")

    unreachable = subprocess.run(
        ["git", "merge-base", "--is-ancestor", f"feat/{EPIC}", base],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    assert unreachable.returncode != 0
    result = branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo))
    assert result.epic_branch == f"feat/{EPIC}"


def test_a_squash_merged_branch_that_then_diverged_is_still_refused(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
) -> None:
    """The one case archival existed to defend against."""
    repo = epic()
    base = _head(repo)
    git(repo, "checkout", "-q", "-b", f"feat/{EPIC}")
    write(repo / "src" / "shipped.txt", "content\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the epic")
    git(repo, "checkout", "-q", base)
    git(repo, "merge", "-q", "--squash", f"feat/{EPIC}")
    git(repo, "commit", "-qm", "squashed epic")
    git(repo, "checkout", "-q", f"feat/{EPIC}")
    write(repo / "src" / "after.txt", "diverged\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "kept going after the squash")
    git(repo, "checkout", "-q", base)

    with pytest.raises(WorkflowFailed, match="not in"):
        branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo))


def test_an_epic_this_run_cut_is_returned_to_rather_than_refused(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    tmp_path: Path,
) -> None:
    """The multi-epic drain."""
    repo = epic()
    base = _head(repo)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir))
    write(repo / "src" / "ours.txt", "story one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "story one")
    landed = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "-b", "feat/another-epic", base)

    result = branch_epic(
        logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir)
    )

    assert result.epic_branch == f"feat/{EPIC}"
    assert _head(repo) == f"feat/{EPIC}"
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == landed
    assert (repo / "src" / "ours.txt").exists()


def test_returning_to_a_set_aside_epic_brings_in_what_landed_meanwhile(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    tmp_path: Path,
) -> None:
    """The other half of the multi-epic drain, and the one that used to ship corruption."""
    repo = epic()
    base = _head(repo)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir))
    git(repo, "checkout", "-q", base)
    write(repo / "src" / "epic-b.txt", "finished elsewhere\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "epic B")
    landed = git(repo, "rev-parse", "HEAD").stdout.strip()

    branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir))

    assert _head(repo) == f"feat/{EPIC}"
    assert (repo / "src" / "epic-b.txt").exists()
    assert is_ancestor(repo, landed, f"feat/{EPIC}")


def test_a_set_aside_epic_that_conflicts_with_base_is_refused_not_half_merged(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    tmp_path: Path,
) -> None:
    """Two epics that edited the same lines are a human's call, not a run's — and the refusal must leave a clean tree, not a conflicted one the next node would commit."""
    repo = epic()
    base = _head(repo)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir))
    write(repo / "src" / "contested.txt", "epic A's line\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "story one")
    git(repo, "checkout", "-q", base)
    write(repo / "src" / "contested.txt", "epic B's line\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "epic B")

    with pytest.raises(WorkflowFailed, match="does not merge cleanly"):
        branch_epic(
            logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir)
        )

    assert not git(repo, "status", "--porcelain").stdout.strip()
    assert not (repo / ".git" / "MERGE_HEAD").exists()


def test_a_claim_does_not_outlive_the_run_that_made_it(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    tmp_path: Path,
) -> None:
    """The ledger must not become a way to walk past the refusal."""
    repo = epic()
    base = _head(repo)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir))
    write(repo / "src" / "ours.txt", "story one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "story one")
    git(repo, "checkout", "-q", base)

    begin_run(logger, run_dir=str(run_dir))

    with pytest.raises(WorkflowFailed, match="not in"):
        branch_epic(
            logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir)
        )




def test_story_mode_cuts_its_own_branch_and_ends_at_its_own_pr(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`decide_mode`'s other arm: no queue, no epic PR, no CI gate."""
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)
    run_env = env()

    result = drive_flow(Coder(mode="story", story="STORY-1", epic=EPIC), run_env, _Agent())

    assert result.story_pr == "skipped", result
    assert sub.calls == ["Dev", "Review", "Docs", "Qa", "Fix"], sub.calls
    assert not (run_env.writer.run_dir / select_epic.__name__).exists()
    assert not (run_env.writer.run_dir / open_pr.__name__).exists()
    assert _output(run_env, open_story_pr)["story_pr"] == "skipped"
    assert _head(repo) == _output(run_env, branch_story)["story_branch"]


def test_the_epic_pr_title_is_the_subject_a_squash_merge_will_release(
    epic: Callable[..., Path],
) -> None:
    """The title is not decoration: under squash-merge it *becomes* the merge commit."""
    repo = epic()

    assert _epic_pr_title(repo, EPIC) == "feat(acme): epic One"


def test_the_epic_reaches_the_sub_flows_and_story_mode_passes_its_own(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_story_epic` — the *story's* epic, which in story mode is discovered by scanning."""
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)

    drive_flow(Coder(mode="story", story="STORY-1"), env(), _Agent())

    assert [c.epic for c in sub.calls_to("Dev")] == [EPIC]
    assert [c.epic for c in sub.calls_to("Qa")] == [EPIC]


def test_both_flows_that_diff_the_worktree_are_told_what_was_already_dirty(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Docs` and `Qa` build the same `HEAD..WORKTREE` packet, so both need the snapshot."""
    repo = epic()
    orphan = repo / "src" / "abandoned.py"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("def strand():\n    return 1\n", encoding="utf-8")
    sub = _Sub(repo).install(monkeypatch)

    drive_flow(Coder(mode="story", story="STORY-1"), env(), _Agent())

    recorded = [c.preexisting for c in sub.calls_to("Docs")] + [
        c.preexisting for c in sub.calls_to("Qa")
    ]
    assert recorded, sub.calls
    for snapshot in recorded:
        assert any(entry.startswith("src/abandoned.py\0") for entry in snapshot), snapshot




def test_re_verifying_given_up_stories_moves_each_status_to_passed(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The re-verification pass, which produces no diff at all and is still the loop's most valuable work."""
    repo = epic(count=4, status=GAVE_UP)
    sub = _Sub(repo, changes=False).install(monkeypatch)
    run_env = env()

    result = drive_flow(Coder(), run_env, _Agent())

    assert result.has_epic is False, result
    assert sub.calls.count("Dev") == 4, sub.calls
    assert _output(run_env, open_pr)["should_gate"] is True
    for n in range(1, 5):
        story = repo / "docs" / "epics" / EPIC / "stories" / f"STORY-{n}" / "story.md"
        assert "QA passed" in story.read_text(encoding="utf-8"), story


def test_a_story_that_left_work_uncommitted_gets_one_lap_to_record_it(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dirty tree is not a failure on the first reading — it is one more turn."""
    repo = epic()
    _Sub(repo, leave_dirty=True).install(monkeypatch)
    run_env = env()
    agent = _Agent(settle="commit")
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, {})):
        result = drive_flow(Coder(), run_env, agent)

    assert result.has_epic is False, result
    assert agent.calls == ["settle-worktree"], agent.calls
    assert seen == [], seen
    assert _output(run_env, check_repos_clean)["clean"] is True
    assert _output(run_env, stamp_story_passed)["stamped"] is True
    assert _dirty(repo) == "", _dirty(repo)
    assert "feat(acme): story STORY-1" in _subjects(repo), _subjects(repo)


def test_a_settle_lap_that_blocks_parks_the_story_for_an_operator(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The arm that used to be a `git commit -a` over whatever happened to be in the tree."""
    repo = epic()
    _Sub(repo, leave_dirty=True).install(monkeypatch)
    run_env = env()
    agent = _Agent(settle="blocked")
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "feat(acme): story STORY-1")
        path.write_text("STATUS: ANSWERED\n\nCommitted it myself.\n", encoding="utf-8")

    with patch.object(pyflow_driver, "wait_for_answer", answered):
        result = drive_flow(Coder(), run_env, agent)

    assert result.has_epic is False, result
    assert agent.calls == ["settle-worktree"], agent.calls
    assert len(seen) == 1, seen
    assert "src/STORY-1.py" in seen[0], seen[0]
    assert "did not write" in seen[0], seen[0]
    assert _output(run_env, check_repos_clean)["clean"] is True
    assert _output(run_env, stamp_story_passed)["stamped"] is True
    assert _dirty(repo) == "M .agents/operator/dirty-tree-operator-context.STORY-1.md", _dirty(repo)


def test_a_settle_lap_that_claims_success_it_did_not_achieve_buys_a_reading_not_a_pass(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other way a second dirty reading happens — and the one a status field can hide."""
    repo = epic()
    _Sub(repo, leave_dirty=True).install(monkeypatch)
    run_env = env()
    agent = _Agent(settle="claimed")
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "feat(acme): story STORY-1")
        path.write_text("STATUS: ANSWERED\n\nCommitted it myself.\n", encoding="utf-8")

    with patch.object(pyflow_driver, "wait_for_answer", answered):
        result = drive_flow(Coder(), run_env, agent)

    assert result.has_epic is False, result
    assert agent.calls == ["settle-worktree"], agent.calls
    assert len(seen) == 1, seen
    assert "src/STORY-1.py" in seen[0], seen[0]
    assert "recorded everything" not in seen[0], seen[0]
    assert _output(run_env, check_repos_clean)["clean"] is True
    assert _output(run_env, stamp_story_passed)["stamped"] is True


def test_the_operators_own_uncommitted_files_are_not_the_storys_to_answer_for(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`preexisting` subtracted, which is the difference between this check and `git status`."""
    repo = epic()
    write(repo / "src" / "scratch.py", "# mine, not the run's\n")
    _Sub(repo).install(monkeypatch)
    run_env = env()

    result = drive_flow(Coder(), run_env, _Agent())

    assert result.has_epic is False, result
    assert _output(run_env, check_repos_clean)["clean"] is True
    assert _dirty(repo) == "?? src/scratch.py", _dirty(repo)


def test_the_triage_budget_survives_a_rescope_back_to_dev(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`init_triage_counter` sits in `prepare`, not in `qa`, and this is why."""
    repo = epic()

    class _Rescoping(_Sub):
        def _qa(self, child: _StubFlow) -> QaFlowResult:
            nth = self.calls.count("Qa")
            return QaFlowResult(
                status="rescope" if nth == 1 else "passed",
                qa=QaResult(status="passed"),
                triage_scope=child.triage_scope + 1,
            )

    sub = _Rescoping(repo).install(monkeypatch)
    run_env = env()

    drive_flow(Coder(), run_env, _Agent())

    assert [c.triage_scope for c in sub.calls_to("Qa")] == [0, 1], sub.calls
    assert sub.calls.count("Dev") == 2, sub.calls
    assert _output(run_env, prepare_story)["story_slug"] == "STORY-1"


def test_a_product_class_refix_sends_the_story_back_through_dev(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`refix` is a `rescope` in wiring and its opposite in meaning, and both re-enter dev."""
    repo = epic()

    class _Refixing(_Sub):
        def _qa(self, child: _StubFlow) -> QaFlowResult:
            nth = self.calls.count("Qa")
            return QaFlowResult(
                status="refix" if nth == 1 else "passed",
                qa=QaResult(status="passed"),
                triage_scope=child.triage_scope + 1,
            )

    sub = _Refixing(repo).install(monkeypatch)

    drive_flow(Coder(), env(), _Agent())

    assert sub.calls.count("Dev") == 2, sub.calls
    assert [c.triage_scope for c in sub.calls_to("Qa")] == [0, 1], sub.calls


def test_a_give_up_names_the_rework_count_in_its_failure_message(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure message is the only thing an operator triaging a give-up reads first."""
    repo = epic()
    _Sub(repo, qa_status="inconclusive").install(monkeypatch)

    with pytest.raises(WorkflowFailed, match="after 1 attempt") as caught:
        drive_flow(Coder(), env(), _Agent())

    assert "nothing was committed" in str(caught.value), caught.value
    assert not any("QA FAILED" in s for s in _subjects(repo)), _subjects(repo)


def test_a_give_up_docs_recheck_that_changes_the_qa_plan_retries_qa(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A docs recheck can repair the executable QA contract, not merely describe failure."""
    repo = epic()
    sub = _Sub(
        repo,
        docs_authored_nodes=["docs/specs/STORY-1/qa_plan.py#compare_article_inventory"],
        qa_statuses=["inconclusive", "passed"],
    ).install(monkeypatch)
    run_env = env()

    drive_flow(Coder(), run_env, _Agent())

    assert sub.calls.count("Qa") == 2, sub.calls
    assert not (run_env.writer.run_dir / SKIP_FILE).exists()
    assert all("QA FAILED" not in subject for subject in _subjects(repo))


def test_a_blocked_docs_verdict_parks_for_an_operator_rather_than_shipping_the_story(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A documentation block parks the run for a human, carrying the refusal's reason."""
    repo = epic(count=2)

    class _BlockingFirst(_Sub):
        def _docs(self, child: _StubFlow) -> DocsResult:
            if child.story == "STORY-1" and self.calls.count("Docs") == 1:
                return DocsResult(status="blocked", notes=BLOCK_REASON)
            return DocsResult(status="passed", notes="")

    sub = _BlockingFirst(repo).install(monkeypatch)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, {"yes": True})):
        result = drive_flow(Coder(), env(), _Agent())

    assert result.has_epic is False, result
    assert len(seen) == 1, seen
    assert BLOCK_REASON in seen[0], seen[0]
    assert "STORY-1" in seen[0], seen[0]
    documented = [c.story for c in sub.calls_to("Docs")]
    assert documented.count("STORY-1") == 2, documented
    assert sub.calls.count("Qa") == 2, sub.calls
    assert not any("DOCS BLOCKED" in s for s in _subjects(repo)), _subjects(repo)


@pytest.mark.parametrize("mode", ["epic", "story"])
def test_a_required_final_docs_block_parks_for_an_operator_in_either_mode(
    mode: str,
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tainted story's required recheck parks for a human when it blocks — in either mode."""
    repo = epic()

    class _BlockingFinal(_Sub):
        def _docs(self, child: _StubFlow) -> DocsResult:
            if self.calls.count("Docs") == 2:
                return DocsResult(status="blocked", notes=BLOCK_REASON)
            return DocsResult(status="passed", notes="")

    sub = _BlockingFinal(repo, qa_docs_recheck_required=True).install(monkeypatch)
    flow = Coder() if mode == "epic" else Coder(mode="story", story="STORY-1", epic=EPIC)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, {"yes": True})):
        drive_flow(flow, env(), _Agent())

    assert len(seen) == 1, seen
    assert BLOCK_REASON in seen[0], seen[0]
    assert sub.calls.count("Docs") == 3, sub.calls
    assert sub.calls.count("Qa") == 1, sub.calls
    assert "feat(acme): story STORY-1" in _subjects(repo), _subjects(repo)
    assert not any("DOCS BLOCKED" in subject for subject in _subjects(repo)), _subjects(repo)


def test_a_docs_handoff_that_merely_failed_parks_on_the_same_gate_a_block_does(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`failed` is not a second-class `blocked` — it is the same escalation."""
    repo = epic()

    class _FailingFirst(_Sub):
        def _docs(self, child: _StubFlow) -> DocsResult:
            if self.calls.count("Docs") == 1:
                return DocsResult(status="failed", notes="the book's coverage check errored")
            return DocsResult(status="passed", notes="")

    sub = _FailingFirst(repo).install(monkeypatch)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, {"yes": True})):
        drive_flow(Coder(), env(), _Agent())

    assert len(seen) == 1, seen
    assert "failed" in seen[0], seen[0]
    assert "the book's coverage check errored" in seen[0], seen[0]
    assert sub.calls.count("Docs") == 2, sub.calls
    assert sub.calls.count("Qa") == 1, sub.calls
    assert "feat(acme): story STORY-1" in _subjects(repo), _subjects(repo)




def test_a_green_story_hands_the_backlog_to_the_fix_flow(
    epic: Callable[..., Path],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The drain is one handoff, and it is `Fix` — not a second copy of the loop here."""
    repo = epic()
    write(repo / "docs" / "backlog.md", BACKLOG)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "File one fix")
    sub = _Sub(repo).install(monkeypatch)
    run_env = env()
    agent = _Agent()

    drive_flow(Coder(), run_env, agent)

    assert sub.calls.count("Fix") == 1, sub.calls
    assert agent.calls == [], agent.calls
    assert _output(run_env, prepare_story)["story_slug"] == "STORY-1"
    assert _output(run_env, check_repos_clean)["clean"] is True
    assert _dirty(repo) == "", _dirty(repo)


def test_the_drain_runs_even_when_the_backlog_is_empty(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The draw is `Fix`'s exit, not this graph's precondition."""
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)

    drive_flow(Coder(), env(), _Agent())

    assert sub.calls.count("Fix") == 1, sub.calls




def test_a_run_killed_in_qa_resumes_on_qa_without_rebuilding_the_story(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason `dev`, `review`, `document` and `qa` are four states and not one."""
    repo = epic()
    _Sub(repo, explode={"Qa"}).install(monkeypatch)
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during Qa"):
        drive_flow(Coder(), run_env, _Agent())

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "qa", resume
    assert resume.flow == "Coder", resume

    sub = _Sub(repo).install(monkeypatch)
    result = drive_flow(Coder(**resume.inputs), env(run_dir=run_dir), _Agent(), resume)

    assert result.has_epic is False, result
    assert "Dev" not in sub.calls, sub.calls
    assert sub.calls == ["Qa", "Fix"], sub.calls
    assert [c.epic for c in sub.calls_to("Qa")] == [EPIC], "the epic is read back, not carried"




_test_bp = Blueprint("test")


_ci_seam: dict[str, Any] = {}


@_test_bp.node
def _seamed_poll_pr_checks(logger: Any, repo_dir: str = "", branch: str = "") -> CiChecks:
    seam = _ci_seam
    polls: list[str] = seam["polls"]
    polls.append(branch)
    if seam["green"]["yes"]:
        return CiChecks(status="passed", summary="")
    return CiChecks(status=seam["verdict"], summary=seam["summary"])


def _red_ci(
    polls: list[str],
    green: dict[str, bool],
    verdict: CiStatus = "failed",
    summary: str = "the unit suite is red",
) -> Any:
    """`poll_pr_checks`, not green until the operator answers the gate."""
    _ci_seam.update(polls=polls, green=green, verdict=verdict, summary=summary)
    return _seamed_poll_pr_checks


def _answers(seen: list[str], green: dict[str, bool]) -> Callable[..., None]:
    """The human the `Await` is waiting on: they fix CI, then touch the file."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        green["yes"] = True
        path.write_text("STATUS: ANSWERED\n\nThe runner was out of disk.\n", encoding="utf-8")

    return answered


def test_red_ci_spends_its_three_attempts_and_then_escalates_to_a_human(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ci → repair_ci → ci` three times, then the gate — which is human whatever the mode."""
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)
    polls: list[str] = []
    green = {"yes": False}
    monkeypatch.setattr(coder_main, "poll_pr_checks", _red_ci(polls, green))
    run_env = env()
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, green)):
        result = drive_flow(Coder(), run_env, _Agent())

    assert result.has_epic is False, result
    assert len(polls) == 5, polls
    assert set(polls) == {f"feat/{EPIC}"}, polls
    assert sub.calls.count("FixCi") == 3, sub.calls
    assert {c.branch for c in sub.calls_to("FixCi")} == {f"feat/{EPIC}"}
    assert _output(run_env, flag_ci_failure)["ci_flagged"] is False
    assert len(seen) == 1, seen
    assert "after 3 automated attempt(s)" in seen[0], seen[0]
    assert (repo / "docs" / "epics" / EPIC / "ci-operator-context.md").is_file()


def test_unreadable_ci_parks_at_once_instead_of_spending_a_repair_lap(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`blocked` is not `failed` and is not `unavailable`: it is the gate, on the first poll."""
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)
    polls: list[str] = []
    green = {"yes": False}
    monkeypatch.setattr(
        coder_main,
        "poll_pr_checks",
        _red_ci(polls, green, "blocked", "CI unreadable: 403 on Actions"),
    )
    run_env = env()
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, green)):
        result = drive_flow(Coder(), run_env, _Agent())

    assert result.has_epic is False, result
    assert len(polls) == 2, "one refusal, then the operator's answer re-polls green"
    assert sub.calls.count("FixCi") == 0, sub.calls
    assert len(seen) == 1, seen
    assert "after 0 automated attempt(s)" in seen[0], seen[0]
    assert "403 on Actions" in seen[0], seen[0]




def _failing_merge(merges: list[str], landed: dict[str, bool]) -> Any:
    """`merge_pr`, conflicted until the operator answers the gate."""

    @_test_bp.node
    def merge_pr(
        logger: Any, epic: str = "", base_branch: str = "main", repo_dir: str = ""
    ) -> Any:
        merges.append(epic)
        if landed["yes"]:
            return MergeOutcome(merge_status="merged", base_branch=base_branch)
        return MergeOutcome(merge_status="failed", base_branch=base_branch)

    return merge_pr


class _BlockedResolver(_Agent):
    """`_Agent` plus the one turn this test expects: a resolver that will not choose."""

    def _fix_merge(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "blocked",
            "notes": "both sides rewrote the same migration and only you know which wins",
        }


def test_a_merge_resolver_that_cannot_decide_parks_instead_of_spending_the_budget(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One resolver turn, then the gate — not `MAX_MERGE_REWORKS` of them."""
    repo = epic()
    _Sub(repo).install(monkeypatch)
    merges: list[str] = []
    landed = {"yes": False}
    monkeypatch.setattr(coder_main, "merge_pr", _failing_merge(merges, landed))
    run_env = env()
    seen: list[str] = []

    agent = _BlockedResolver()

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, landed)):
        result = drive_flow(Coder(), run_env, agent)

    assert result.has_epic is False, result
    assert agent.calls.count("fix-merge") == 1, agent.calls
    assert merges == [EPIC, EPIC], merges
    assert len(seen) == 1, seen
    assert "after 0 automated attempt(s)" in seen[0], seen[0]
    assert (repo / "docs" / "epics" / EPIC / "merge-operator-context.md").is_file()
