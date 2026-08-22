"""End-to-end tests for `coder`'s main graph — the epic/story loop itself.

Eighty YAML nodes became twenty-seven states, and what is left to test at this level is the
*sequencing*: which state follows which, what the three counters do, what the two operator
gates escalate on, and what a kill in the middle resumes onto. So this file drives `Coder`
end to end against a real git repo with a real epic queue, and asserts on the queue, the
commits and the run's own artifacts.

**The five handed-off sub-flows are stand-ins here, and every node is real.** `dev`,
`review`, `docs`, `qa` and `fix_ci` each already have their own end-to-end suite in
its own directory beside this one, driven the same way and against the same fixtures; re-running them from the top
would test them twice and this graph once. What is *not* stubbed is the handoff boundary
itself — a stub is a real `Workflow` subclass handed to the real `self.handoff`, so it is
constructed with the real keywords, driven by the real driver, and recorded under the real
node id. A keyword this graph passes that a flow does not declare still fails here, which is
the half of the boundary the flow's own suite cannot check.

The stubs reply with the flows' real result models, because that is what the graph reads:
`DevResult.status` routes to `replan`, `QaFlowResult.triage_scope` is the budget that
survives a rescope, `DocsResult.status` is what `_require_documented` fails the run on. A
stub returning a bare dict would test the state machine against a fiction.

**One node is seamed, in one test.** `poll_pr_checks` is the only thing in the graph that
must be *red* for the CI escalation to be reachable at all, and offline it can only ever be
`unavailable`. It is replaced by a node of the same name stamped by a test-local blueprint,
which the engine resolves by the stamp — so the state, its counter and the gate above it are
the real ones. Everything else about the PR/CI/merge cluster runs offline exactly as a
tokenless run would, and that pass-through is itself asserted rather than mocked away.
"""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import Blueprint, Done, Workflow, WorkflowFailed
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.kit import commit_all, commit_paths, is_ancestor
from workhorse_workflows.coder import workflow as coder_workflow
from workhorse_workflows.coder.shared import commits
from workhorse_workflows.coder.shared.backlog import prune_fix_item, select_fix_item
from workhorse_workflows.coder.shared.ci import poll_pr_checks
from workhorse_workflows.coder.nodes.pr import (
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
from workhorse_workflows.coder.shared.story import prepare_fix_story, prepare_story
from workhorse_workflows.coder.shared.schemas.ci import CiChecks
from workhorse_workflows.coder.shared.schemas.dev import DevResult
from workhorse_workflows.coder.shared.schemas.docs import DocsResult
from workhorse_workflows.coder.shared.schemas.qa import QaFlowResult, QaResult
from workhorse_workflows.coder.shared.schemas.pr import MergeOutcome
from workhorse_workflows.coder.shared.schemas.review import ReviewResult
from workhorse_workflows.coder.workflow import Coder

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

## Implementation Status

- **Status**: {status}
"""

#: What `flag_qa_failure` leaves on a story it gave up on — the status a re-run supersedes.
GAVE_UP = "QA FAILED after 3 QA-plan review revision attempts — needs manual review"

#: One drainable backlog item, in the shape `select_fix_item` parses.
BULLET = "widget-pagination"
BULLET_TEXT = "the widget list does not paginate"
FIX_SLUG = "the-widget-list-does-not-paginate"
BACKLOG = f"""# Backlog

## Filed by coder

- [{BULLET}] {BULLET_TEXT}
"""

#: Why a documentation author refuses a story, in the shape a real one gave.
BLOCK_REASON = "the handler allows every origin when the allow-list is unset"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _no_ambient_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both variables `resolve_github_token` falls back to, unset for every test here.

    Nothing else in the suite needs this because nothing else reaches the PR boundary. On a
    developer's machine with either exported, `open_pr`, `poll_pr_checks` and `merge_pr`
    would stop reporting `unavailable` and start talking to github.com about a branch named
    after a temp directory. Unsetting them is what makes "offline" a property of the test
    rather than of the machine running it.
    """
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


@pytest.fixture
def epic(
    repo: Path,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> Callable[..., Path]:
    """An epic of N stories in the queue, committed — so the tree starts clean.

    Committed on purpose. `check_repos_clean` asks git what is uncommitted, and a fixture
    that left the queue dirty would make every story look like it forgot to commit — the
    dirty-tree gate is only testable against a repo whose only dirt is what the run made.
    """

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


# ----------------------------------------------------------------------- the sub-flows


def _story_message(package: str, slug: str) -> str:
    """The subject a real dev agent is told to write, built from the shared helper.

    Spelled through `commits` rather than as a literal so the trailers the run record ties
    a commit back to stay one definition — the stand-in and the prompt agree by
    construction, not by two people remembering the same format.
    """
    return commits.message(
        "feat", commits.scope(package), f"story {slug}", epic=EPIC, story=slug
    )


class _StubFlow(Workflow):
    """Every keyword the graph's five handoffs pass, because `Workflow` forbids extras.

    Declaring them all on one base is what makes the boundary assertion work in both
    directions: a keyword the graph stops passing is silently fine, and a keyword it starts
    passing that no flow declares fails construction — here, and in a real run, identically.
    """

    story: str = ""
    docs_path: str = ""
    epic: str = ""
    preexisting: tuple[str, ...] = ()
    operator_mode: str = ""
    target_env: str = ""
    qa_stack_manifest: str = ""
    sandbox: bool = False
    qa_lane_budget_s: int = 0
    plan_lane_budget_s: int = 0
    triage_scope_count: int = 0
    repo: str = ""
    branch: str = ""
    ci_summary: str = ""
    session_id: str = ""
    session_turns: int = 0


class _Sub:
    """The five stand-ins, their call log, and the one file `dev` writes.

    `dev` writing a file *and committing it* is not decoration: it is what the real dev
    lane does now that the workflow no longer commits on the agent's behalf, and
    `check_repos_clean` reads exactly that. A `dev` that wrote and did not commit would
    take the settle lap on every story; `leave_dirty` is the stand-in for the agent that
    forgets, and only the two tests about that arm pass it.
    """

    def __init__(
        self,
        repo: Path,
        *,
        changes: bool = True,
        leave_dirty: bool = False,
        dev_status: str = "ready",
        docs_status: str = "passed",
        docs_notes: str = "",
        docs_authored_nodes: list[str] | None = None,
        qa_status: str = "passed",
        qa_statuses: list[str] | None = None,
        qa_docs_recheck_required: bool = False,
        ci_status: str = "passed",
        explode: set[str] | None = None,
    ) -> None:
        self.repo = repo
        self.changes = changes
        self.leave_dirty = leave_dirty
        self.dev_status = dev_status
        self.docs_status = docs_status
        self.docs_notes = docs_notes
        self.docs_authored_nodes = docs_authored_nodes or []
        self.qa_status = qa_status
        self.qa_statuses = qa_statuses or []
        self.qa_docs_recheck_required = qa_docs_recheck_required
        self.ci_status = ci_status
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
        ):
            monkeypatch.setattr(coder_workflow, name, self._flow(name, reply))
        return self

    def _flow(self, name: str, reply: Callable[[_StubFlow], Any]) -> type:
        """A real `Workflow` subclass named for the flow it stands in for.

        The name matters twice over: `handoff` derives the recorded node id from it, and
        `_sub_scope` leaves an unclaimed class in its caller's environment — so a stub
        records under the same id, in the same run directory, as the flow it replaces.
        """
        calls, explode, seen = self.calls, self.explode, self.seen

        def start(child: _StubFlow) -> Done:
            calls.append(name)
            seen.append(child)
            if name in explode:
                raise RuntimeError(f"killed during {name}")
            return Done(reply(child))

        # Redeclared, not just inherited: pydantic only re-resolves a shadowed field's
        # default against the *defining* class's own namespace, so a dynamic subclass
        # that never repeats the annotation would see `Workflow.session_id`'s method,
        # not `_StubFlow`'s "" default, whenever nothing overrides it at construction.
        return type(
            name,
            (_StubFlow,),
            {"start": start, "__annotations__": {"session_id": str}, "session_id": ""},
        )

    def calls_to(self, name: str) -> list[_StubFlow]:
        return [c for n, c in zip(self.calls, self.seen, strict=True) if n == name]

    # -- the replies, each the flow's own result model ---------------------

    def _dev(self, child: _StubFlow) -> DevResult:
        if self.changes:
            path = self.repo / "src" / f"{child.story}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {child.story}\n", encoding="utf-8")
            if not self.leave_dirty:
                # By explicit path, which is what the prompt asks of a real one: a stray
                # file in the tree is the operator's, and `git add -A` is how it stops
                # being theirs.
                commit_paths(
                    self.repo,
                    _story_message(self.repo.name, child.story),
                    f"src/{child.story}.py",
                )
        return DevResult(status=self.dev_status, operator_notes="rescope to the epic")

    def _review(self, child: _StubFlow) -> ReviewResult:
        return ReviewResult(status="approved", notes="")

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
            qa=QaResult(status=status),
            qa_rework=1,
            triage_scope=child.triage_scope_count,
            operator_notes="",
            docs_recheck_required=self.qa_docs_recheck_required,
        )

    def _fix_ci(self, child: _StubFlow) -> CiChecks:
        return CiChecks(status=self.ci_status, summary="")


# --------------------------------------------------------------------------- the agent


class _Agent:
    """The graph's own six prompts. Every other turn is inside a stubbed sub-flow.

    Only the drain reaches any of them in these tests, so the default handler asserts: a
    turn firing where none was expected is a routing bug, and a permissive stub would let it
    through as a pass.
    """

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
        # Committed, like every producer turn is now told to: the plan is an artifact the
        # story leaves behind, and an uncommitted one is dirt `check_repos_clean` reads.
        root = Path.cwd()
        commit_all(root, commits.message("docs", commits.scope(root.name), "plan a drained item"))
        return {"status": "done", "summary": "one AC, one fix"}

    def _qa_fix_item(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"status": "passed", "notes": ""}

    def _settle_worktree(self, data: dict[str, Any]) -> dict[str, Any]:
        """The one lap a story gets to record work it left on disk.

        `settle` is empty for every test that does not expect this turn at all, and the
        assertion is the same one the default handler makes: a settle lap firing where the
        story committed as it went is a routing bug, and a permissive stub would pass it.
        """
        assert self.settle, "unexpected settle lap — the story committed nothing"
        if self.settle == "commit":
            root = Path.cwd()
            slug = data["story_slug"]
            commit_all(root, _story_message(root.name, slug))
            return {"status": "settled", "notes": f"committed {slug}"}
        if self.settle == "claimed":
            # The optimistic self-report the workflow is written not to believe: the turn
            # says it recorded the work and the tree still holds it.
            return {"status": "settled", "notes": "recorded everything the story wrote"}
        return {"status": self.settle, "notes": "the tree holds an edit I did not write"}


# --------------------------------------------------------------------------- helpers


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


# ------------------------------------------------------------------ the epic happy path


def test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole loop in one pass: queue → story → PR → CI → merge → empty queue.

    The four sub-flows come back in order. Clean QA reports that nothing changed after the
    first Docs pass, so the redundant final documentation handoff is skipped.
    """
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)
    run_env = env()

    result = drive_flow(Coder(), run_env, _Agent())

    assert result.has_epic is False, result
    assert sub.calls == ["Dev", "Review", "Docs", "Qa"], sub.calls
    # The story built, and its work landed as one commit.
    assert _output(run_env, check_repos_clean)["clean"] is True
    assert _output(run_env, stamp_story_passed)["stamped"] is True
    assert _dirty(repo) == "", _dirty(repo)
    assert (repo / "src" / "STORY-1.py").is_file()
    # The epic was popped off the queue before its PR was opened.
    assert EPIC not in (repo / "docs" / "epics" / "index.md").read_text(encoding="utf-8")
    # ...and the run ended because the queue is empty, not because anything failed.
    assert _output(run_env, select_epic)["reason"], _output(run_env, select_epic)


def test_the_backbone_session_threads_through_every_lane_unread(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every lane is handed the story's conversation, and `review` passes it on untouched.

    `Review` gets the id because its *apply* turns rejoin the implementer — whether its
    *judging* turns stay cold is `Review`'s own affair, asserted in its own tests. What the
    graph owes is the thread itself, and that nothing is read back off `Review`'s result:
    what reaches `document` is exactly what `dev` produced, with the turn count that says
    how much of the recycle budget the conversation has already spent.
    """
    repo = epic()

    class _ChainingSub(_Sub):
        def _dev(self, child: _StubFlow) -> DevResult:
            super()._dev(child)
            return DevResult(
                status="ready", session_id="story:from-dev", session_turns=3
            )

        def _docs(self, child: _StubFlow) -> DocsResult:
            return DocsResult(status="passed", session_id="story:from-docs")

    sub = _ChainingSub(repo).install(monkeypatch)

    drive_flow(Coder(), env(), _Agent())

    assert sub.calls_to("Review")[0].session_id == "story:from-dev"
    assert sub.calls_to("Review")[0].session_turns == 3
    assert sub.calls_to("Docs")[0].session_id == "story:from-dev"
    assert sub.calls_to("Qa")[0].session_id == "story:from-docs"


def test_a_fresh_story_starts_with_no_backbone_session(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`prepare` hands `dev` nothing to resume — the chain is `dev`'s own to open."""
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)

    drive_flow(Coder(), env(), _Agent())

    assert sub.calls_to("Dev")[0].session_id == ""


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

    assert sub.calls == ["Dev", "Review", "Docs", "Qa", "Docs"], sub.calls
    assert "feat(acme): story STORY-1" in _subjects(repo), _subjects(repo)


def test_the_story_and_its_status_stamp_commit_as_conventional_commits(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The subjects the coder writes into somebody else's repo are release inputs.

    Those repos cut releases with release-please, which reads commit subjects and nothing
    else. `EPIC-0: STORY-1` parses as no type, so the story ships and the release never
    names it — a silence that surfaces weeks later as a bug report against a version that
    was supposed to contain the feature.

    Two subjects, two types, and the difference between them is the point: the story's own
    commit is a `feat` because a story is documented behavior that did not exist before,
    while the status stamp moves a `status:` line and no code, so typing it as the story
    would cut a second release for the act of recording the first.
    """
    repo = epic()
    _Sub(repo).install(monkeypatch)

    drive_flow(Coder(), env(), _Agent())

    subjects = _subjects(repo)
    story = next(s for s in subjects if s.startswith("feat("))
    stamp = next(s for s in subjects if "QA passed" in s)
    assert story == "feat(acme): story STORY-1", story
    assert stamp.startswith("docs(acme): "), stamp
    # The epic and the story stay findable, in the body where they cannot reach a changelog.
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
    """`branch_epic` can only recognise its own branch on a later visit if the graph hands
    it the run dir — and a node that takes `run_dir` but is never given one is silent, not
    an error, so the ledger is asserted from the graph rather than from the node."""
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
    """A run dir outlives the run that made it, and the two skip files must not.

    Workhorse derives the run id from the params digest, so the same command lands in the
    same directory every time. `blocked-epics.txt` and `qa-skip-stories.txt` both mean "set
    aside for the rest of THIS run", and both live there — so before `begin_run` existed, a
    retry read the previous run's verdicts and ended on `select_epic`'s "all 1 queued
    epic(s) were set aside this run" before doing any work. Every retry was a no-op, which
    to an unattended queue is indistinguishable from "nothing left to do".

    So the run dir is seeded here with exactly what the previous run would have written —
    the only epic in the queue, and the only story in it — and the assertion is that the
    story still builds.
    """
    repo = epic()
    _Sub(repo).install(monkeypatch)
    run_env = env()
    run_env.writer.run_dir.mkdir(parents=True, exist_ok=True)
    (run_env.writer.run_dir / BLOCKED_FILE).write_text(f"{EPIC}\n", encoding="utf-8")
    (run_env.writer.run_dir / SKIP_FILE).write_text("STORY-1\n", encoding="utf-8")

    result = drive_flow(Coder(), run_env, _Agent())

    assert _output(run_env, begin_run)["cleared"] == [BLOCKED_FILE, SKIP_FILE]
    # The story the previous run gave up on built, and its epic was never set aside.
    assert (repo / "src" / "STORY-1.py").is_file()
    assert "set aside" not in _output(run_env, select_epic)["reason"]
    assert result.has_epic is False, result


def test_the_story_is_stamped_and_the_next_selection_reads_it_as_done(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What actually terminates the story loop: the status the commit stamps.

    `select_story` is called twice with identical arguments and must answer differently the
    second time, and the only thing that changed between them is the story's own frontmatter.
    That is the loop's whole termination argument, so it is a test of its own rather than an
    incidental consequence of the happy path.
    """
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
    """`should_gate` is read off the *epic*, not off whether GitHub could be reached.

    So a tokenless run still traverses the gate and the merge, and both report `unavailable`
    — the pass-through the port kept deliberately, because the alternative is that no run
    without a GitHub token can ever finish an epic. `ci_epic` stays the bare epic name —
    it is what names the operator-context file and the escalation prose — and the branch is
    derived from it at the call site, which is the inert-gate defect the port preserved and
    this suite now pins the other way round in the red-CI test below.
    """
    repo = epic()
    _Sub(repo).install(monkeypatch)
    run_env = env()

    drive_flow(Coder(), run_env, _Agent())

    assert _output(run_env, open_pr)["should_gate"] is True
    assert _output(run_env, open_pr)["ci_epic"] == EPIC
    assert _output(run_env, poll_pr_checks)["status"] == "unavailable"
    assert _output(run_env, merge_pr)["merge_status"] == "unavailable"
    # The merge was a no-op, so HEAD is left on the epic branch for a manual push.
    assert _head(repo) == f"feat/{EPIC}"


def test_an_epic_branch_carrying_a_set_aside_epic_declines_to_open_a_pr(
    epic: Callable[..., Path],
    logger: logging.Logger,
    tmp_path: Path,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """`flag_epic_blocked`'s "NOT merged" promise, kept at the only boundary that can keep it.

    `branch_epic` cuts every epic from HEAD rather than from the base — deliberately, and
    load-bearing: an epic that needs the previous one's code only compiles because of it. But
    a *set-aside* epic sits on that HEAD too, so its commits ride into the next epic's branch,
    whose PR targets trunk. Merging that PR merges the failed epic, past the gate that set it
    aside, with nobody having looked at the failure. Observed on a benchmark run where two
    QA-gated epics both ended up as ancestors of the third's branch.

    Two controls, because the rule has to be *contributed unmerged commits* rather than plain
    ancestry, and each control fails a different sloppier version of it. An epic set aside on
    a branch of its own is not carried, so it must still ship. And an epic set aside before it
    committed anything leaves `feat/<epic>` sitting on the base — an ancestor of every later
    branch — so a bare containment test would wedge the whole remaining queue on the first
    story that failed early, which is the opposite of what the gate is for.
    """
    repo = epic()
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    # A failed epic's work, then this epic cut on top of it, exactly as `branch_epic` does.
    git(repo, "checkout", "-q", "-b", "feat/EPIC-0")
    (repo / "failed.txt").write_text("half-built\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "EPIC-0: story [QA FAILED — needs manual review]")
    git(repo, "checkout", "-q", "-b", f"feat/{EPIC}")
    # One set aside with work of its own that this epic does not carry, and one that never
    # committed anything at all.
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
    # Declining the PR must not strand the branch: it is still there for the manual review.
    assert git(repo, "rev-parse", "--verify", f"feat/{EPIC}").returncode == 0

    (run_dir / BLOCKED_FILE).write_text("EPIC-9\nEPIC-8\n", encoding="utf-8")
    unrelated = open_pr(logger, epic=EPIC, base_branch="main", run_dir=str(run_dir),
                        repo_dir=str(repo))

    assert unrelated.should_gate is True, "an unrelated set-aside epic must not block the queue"
    assert unrelated.ci_epic == EPIC


# --------------------------------------------------------------------------- epic branch


def test_retrying_at_the_same_commit_continues_and_leaves_no_refs_behind(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """A retry after a failure *is* a second attempt at an unchanged HEAD.

    `branch_epic` used to rename the leftover `feat/<epic>` aside to
    `archive/<epic>-<sha>` on every attempt. That was fine while the refs landed in a
    container-local clone that `down -v` destroyed. Under worktrees they land in the
    **operator's own repo**, so three attempts left two permanent `archive/*` branches
    in their `git branch` — for a case that is not stale at all: this working tree
    already has the branch checked out, so the run is simply resuming itself.
    """
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
    """The point of not renaming aside. A restart mid-epic must not lose the stories
    already committed to the branch — under worktrees the branch is the run's work,
    not a disposable copy of it."""
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
    """The case concurrency creates. Two runs of the same workflow may pick the same
    epic; the second must be told that, and where the first is, rather than getting
    git's generic checkout failure through a `failed to create epic branch`."""
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
    """Archival renamed this aside silently. In the operator's own repo that is either
    burying somebody's work under an `archive/*` nobody will look at, or continuing an
    epic on top of unrelated content. Neither is a run's call to make."""
    repo = epic()
    base = _head(repo)
    git(repo, "checkout", "-q", "-b", f"feat/{EPIC}")
    write(repo / "src" / "someone-elses.txt", "unmerged\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "work in progress")
    git(repo, "checkout", "-q", base)

    with pytest.raises(WorkflowFailed, match="not in"):
        branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo))

    # Refused, not renamed: the branch is exactly where the human left it.
    branches = git(repo, "branch", "--format=%(refname:short)").stdout.split()
    assert f"feat/{EPIC}" in branches
    assert not [b for b in branches if b.startswith("archive/")], branches


def test_a_merged_epic_branch_is_reused_rather_than_refused(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """The ordinary case after an epic ships: the branch is still lying around, and it
    holds nothing the base does not. Reusing the name is safe and is what keeps a
    re-run of a merged epic from needing a human."""
    repo = epic()
    base = _head(repo)
    git(repo, "branch", f"feat/{EPIC}", base)  # exists, merged, held by nobody

    result = branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo))

    assert result.epic_branch == f"feat/{EPIC}"
    assert _head(repo) == f"feat/{EPIC}"


def test_a_squash_merged_branch_counts_as_merged(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
) -> None:
    """Squash is the default merge on most repos, and it leaves a branch whose commits
    are ancestors of nothing — so an ancestry-only test would call every landed epic
    'unmerged' and refuse it, which is a queue that stops needing a human every time.
    The content test is what catches it."""
    repo = epic()
    base = _head(repo)
    git(repo, "checkout", "-q", "-b", f"feat/{EPIC}")
    write(repo / "src" / "shipped.txt", "content\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the epic")
    git(repo, "checkout", "-q", base)
    git(repo, "merge", "-q", "--squash", f"feat/{EPIC}")
    git(repo, "commit", "-qm", "squashed epic")

    # Its commits are reachable from nothing on base...
    unreachable = subprocess.run(
        ["git", "merge-base", "--is-ancestor", f"feat/{EPIC}", base],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    assert unreachable.returncode != 0
    # ...but the content is identical, so the name is free.
    result = branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo))
    assert result.epic_branch == f"feat/{EPIC}"


def test_a_squash_merged_branch_that_then_diverged_is_still_refused(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
) -> None:
    """The one case archival existed to defend against. It is refused directly here,
    rather than renamed past — the divergence is real work that base does not have."""
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
    """The multi-epic drain. A run cuts epic A, sets it aside, works epic B, then comes
    back to A — and used to die on "unmerged work this run did not create", because
    ownership was inferred from "is it checked out right now", which is only ever true of
    the epic in hand. The run's own ledger is what tells the two cases apart.
    """
    repo = epic()
    base = _head(repo)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir))
    write(repo / "src" / "ours.txt", "story one\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "story one")
    landed = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "-b", "feat/another-epic", base)  # moved on to epic B

    result = branch_epic(
        logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir)
    )

    assert result.epic_branch == f"feat/{EPIC}"
    assert _head(repo) == f"feat/{EPIC}"
    # Returned to, not reset: the stories it already committed are still there.
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == landed
    assert (repo / "src" / "ours.txt").exists()


def test_returning_to_a_set_aside_epic_brings_in_what_landed_meanwhile(
    epic: Callable[..., Path],
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    tmp_path: Path,
) -> None:
    """The other half of the multi-epic drain, and the one that used to ship corruption.

    Epic A is cut, set aside, and epic B is finished and merged into base while A waits.
    The branch A comes back to is now behind by all of B — it carries B's story files as
    they were *before* B finished, including statuses B has since moved to `QA passed`.
    Every reviewer on A then reads those stale files as truth, and whatever survives to
    A's own squash merge puts them back on base.

    Returning must therefore mean "return and catch up", not "return".
    """
    repo = epic()
    base = _head(repo)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    branch_epic(logger, epic=EPIC, base_branch=base, repo_dir=str(repo), run_dir=str(run_dir))
    git(repo, "checkout", "-q", base)
    write(repo / "src" / "epic-b.txt", "finished elsewhere\n")  # epic B lands on base
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
    """Two epics that edited the same lines are a human's call, not a run's — and the
    refusal must leave a clean tree, not a conflicted one the next node would commit."""
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
    """The ledger must not become a way to walk past the refusal. `begin_run` clears it,
    so the next run in the same dir sees the same branch as what it now is to *that* run:
    unmerged work it did not create."""
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


# --------------------------------------------------------------------------- story mode


def test_story_mode_cuts_its_own_branch_and_ends_at_its_own_pr(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`decide_mode`'s other arm: no queue, no epic PR, no CI gate.

    The branch is cut in `start` and read back in `commit_pr` from the node that cut it —
    never re-derived from the slug, which is the drift the port's docstring records. So the
    PR node is handed exactly what `branch_story` recorded, and that is what is asserted.
    """
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)
    run_env = env()

    result = drive_flow(Coder(mode="story", story="STORY-1", epic=EPIC), run_env, _Agent())

    assert result.story_pr == "skipped", result
    assert sub.calls == ["Dev", "Review", "Docs", "Qa"], sub.calls
    # The queue was never consulted, and the epic PR cluster was never entered.
    assert not (run_env.writer.run_dir / select_epic.__name__).exists()
    assert not (run_env.writer.run_dir / open_pr.__name__).exists()
    # The branch the PR was opened from is the one `branch_story` cut.
    assert _output(run_env, open_story_pr)["story_pr"] == "skipped"
    assert _head(repo) == _output(run_env, branch_story)["story_branch"]


def test_the_epic_pr_title_is_the_subject_a_squash_merge_will_release(
    epic: Callable[..., Path],
) -> None:
    """The title is not decoration: under squash-merge it *becomes* the merge commit.

    GitHub uses the PR title as the squashed subject, so for an epic branch — which is
    always bot-authored and usually squash-merged — this one string is everything
    release-please gets to read about the epic. `Epic: EPIC-1` parses as no type.

    Asserted directly on the builder because the node around it needs a reachable GitHub,
    and every test in this file runs offline; the offline path leaves the branch for a
    manual PR and never forms a title at all.
    """
    repo = epic()

    assert _epic_pr_title(repo, EPIC) == "feat(acme): epic One"


def test_the_epic_reaches_the_sub_flows_and_story_mode_passes_its_own(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_story_epic` — the *story's* epic, which in story mode is discovered by scanning.

    The run is given a bare slug and no epic at all, and every handoff still receives
    `EPIC-1`, because `prepare_story` found it. This is the first of the two disjunctions
    the port's docstring keeps apart, and the one that would be invisible if the run were
    handed the epic it needed.
    """
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
    """`Docs` and `Qa` build the same `HEAD..WORKTREE` packet, so both need the snapshot.

    `Docs` got it first, when an abandoned story's untracked package made the grounding gate
    demand symbols the next story had never written. Wiring only that one left the same code
    reaching the QA planner as obligations — scenarios for a feature the story does not have.
    The assertion is that the snapshot reaches *both*, because one without the other reads
    like the defect is fixed while half of it still costs a cycle.
    """
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


# --------------------------------------------------- the stamp and the dirty-tree gate


def test_re_verifying_given_up_stories_moves_each_status_to_passed(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The re-verification pass, which produces no diff at all and is still the loop's
    most valuable work.

    A story given up on is committed behind its `[QA FAILED]` marker — the work is already
    in the tree. Re-running it later commits nothing *by construction*: there is no diff
    left to make, only a status to move from the failure marker to `QA passed`. So the
    only evidence the pass happened is the stamp, which is precisely why the stamp stayed
    a node of this workflow's when the commits went to the agent.

    Four stories, none of them building anything, and all four end `QA passed` — with the
    tree clean throughout, because a story that writes nothing has nothing to leave behind.
    """
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
    """A dirty tree is not a failure on the first reading — it is one more turn.

    The workflow does not commit on the agent's behalf any more, so `check_repos_clean` is
    the only thing standing between a story's work and being silently left on disk. What it
    finds first is almost always an agent that built the thing and forgot the last step,
    and that is a turn's worth of work, not an operator's ten minutes: the same conversation
    is handed the list and asked to record it, and the check is re-read afterwards.
    """
    repo = epic()
    _Sub(repo, leave_dirty=True).install(monkeypatch)
    run_env = env()
    agent = _Agent(settle="commit")
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, {})):
        result = drive_flow(Coder(), run_env, agent)

    assert result.has_epic is False, result
    assert agent.calls == ["settle-worktree"], agent.calls
    assert seen == [], seen  # nobody was asked for anything
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
    """The arm that used to be a `git commit -a` over whatever happened to be in the tree.

    An agent that will not speak for what is on disk is the one case where committing is
    the wrong answer in both directions: committing it ships a stranger's half-finished
    edit under this story's name, and discarding it destroys work nobody asked about. So
    the story parks, the operator resolves the tree, and the run re-reads it — which is
    also why the gate is answerable at all rather than being the end of the run.
    """
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
    # One lap, one gate: the second dirty reading does not buy another turn.
    assert agent.calls == ["settle-worktree"], agent.calls
    assert len(seen) == 1, seen
    assert "src/STORY-1.py" in seen[0], seen[0]
    assert "did not write" in seen[0], seen[0]
    # The operator's tree is what the run re-read, and the story went on to be stamped.
    assert _output(run_env, check_repos_clean)["clean"] is True
    assert _output(run_env, stamp_story_passed)["stamped"] is True
    # The only thing still dirty is the gate's own file, holding the answer that resolved
    # it — which is exactly the path `is_gate_context` excuses, and why the re-read is
    # clean rather than parking the story a second time on the note it just wrote.
    assert _dirty(repo) == "M dirty-tree-operator-context.STORY-1.md", _dirty(repo)


def test_a_settle_lap_that_claims_success_it_did_not_achieve_buys_a_reading_not_a_pass(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other way a second dirty reading happens — and the one a status field can hide.

    A settle lap that *blocks* announces its own failure, and the run parks on the
    announcement. This lap announces success instead, and the tree is unchanged. Nothing
    downstream re-derives whether it worked, so if the workflow believed the field the
    story would be stamped `QA passed` over work still sitting on disk — and story
    selection reads that line, not the git log. What makes it safe is that `commit`
    re-reads the tree either way: the claim buys the second reading, and the second
    reading is the one that parks.
    """
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
    # One lap, then the gate: a claim does not buy a second turn any more than a block does.
    assert agent.calls == ["settle-worktree"], agent.calls
    assert len(seen) == 1, seen
    assert "src/STORY-1.py" in seen[0], seen[0]
    # The gate carries the tree's reading, not the lap's account of it — this arm is
    # reached because the claim was checked, so there is no agent note to quote.
    assert "recorded everything" not in seen[0], seen[0]
    # The operator settled it, the run re-read the tree, and only then was the story stamped.
    assert _output(run_env, check_repos_clean)["clean"] is True
    assert _output(run_env, stamp_story_passed)["stamped"] is True


def test_the_operators_own_uncommitted_files_are_not_the_storys_to_answer_for(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`preexisting` subtracted, which is the difference between this check and `git status`.

    A developer's half-finished edit sitting in the tree when the run started belongs to
    them. Left in the reading it would park every story of the epic on someone else's work,
    which is the failure mode that makes an operator turn the gate off.
    """
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
    """`init_triage_counter` sits in `prepare`, not in `qa`, and this is why.

    A rescope sends the story back to `dev` and re-enters QA, and a budget seeded on each
    entry would never be spent. The stub echoes back the count it was handed, so a second
    entry carrying what the first spent is the whole assertion — and `prepare` running once
    for two QA entries is what proves the seed was not re-run.
    """
    repo = epic()

    class _Rescoping(_Sub):
        def _qa(self, child: _StubFlow) -> QaFlowResult:
            nth = self.calls.count("Qa")
            return QaFlowResult(
                status="rescope" if nth == 1 else "passed",
                qa=QaResult(status="passed"),
                triage_scope=child.triage_scope_count + 1,
            )

    sub = _Rescoping(repo).install(monkeypatch)
    run_env = env()

    drive_flow(Coder(), run_env, _Agent())

    assert [c.triage_scope_count for c in sub.calls_to("Qa")] == [0, 1], sub.calls
    assert sub.calls.count("Dev") == 2, sub.calls
    # One seed for two QA entries: `prepare` was not re-entered.
    assert _output(run_env, prepare_story)["story_slug"] == "STORY-1"


def test_a_product_class_refix_sends_the_story_back_through_dev(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`refix` is a `rescope` in wiring and its opposite in meaning, and both re-enter dev.

    A rescope means triage amended what the story promised; a refix means the promises stand
    and the product does not meet them. Neither is the QA lane's to fix in place, so the arm
    that matters here is that the parent re-runs `Dev` and carries the spent triage budget
    into the QA entry after it — a refix that reset it would let a story bounce forever.
    """
    repo = epic()

    class _Refixing(_Sub):
        def _qa(self, child: _StubFlow) -> QaFlowResult:
            nth = self.calls.count("Qa")
            return QaFlowResult(
                status="refix" if nth == 1 else "passed",
                qa=QaResult(status="passed"),
                triage_scope=child.triage_scope_count + 1,
            )

    sub = _Refixing(repo).install(monkeypatch)

    drive_flow(Coder(), env(), _Agent())

    assert sub.calls.count("Dev") == 2, sub.calls
    assert [c.triage_scope_count for c in sub.calls_to("Qa")] == [0, 1], sub.calls


def test_a_give_up_names_the_rework_count_in_its_failure_message(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure message is the only thing an operator triaging a give-up reads first.

    `give_up` is reachable only by the `target_env="dev"` report path now — every other QA
    exhaustion escalates to the operator gate inside the QA sub-flow instead of returning
    `inconclusive` at all. What still has to surface here is the rework count `qa()` threads
    through as `attempts`, because the operator reading this is as often a `/loop` tick
    polling the run's terminal state as a human, and neither can act on a story that shipped
    behind a marker.
    """
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
    """A docs recheck can repair the executable QA contract, not merely describe failure.

    The give-up path runs Docs before stamping a skipped story. If that Docs pass amends the
    story-owned QA plan, the next honest step is a fresh QA run against the new contract. Filing
    the old inconclusive result skips work that has just become runnable.
    """
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
    """A documentation block parks the run for a human, carrying the refusal's reason.

    Observed: the author was asked to document a CORS story, found that the implementation
    granted every origin when the allow-list was unset — the opposite of the fail-closed
    guarantee the story's own plan required — and refused to write the book's claim as true.

    This node has been three ways now. Failing the run cost eight unrelated epics behind the
    first; flagging and continuing cost worse, because it committed the refused story behind
    a `[DOCS BLOCKED — needs manual review]` marker and reported the run a success, so the
    queue built on a baseline the reviewer had rejected and the review it asked for never
    happened. Parking is the recoverable half of both trades: the run is checkpointed, so
    the epics behind this one are deferred rather than lost or wrongly shipped, and an
    operator patches the finding and touches the gate file to try again — with no cap on how
    many times a story can bounce back here.

    `notes` has to reach the escalation because it is the only place the refusal is written
    down — unlike a QA give-up there is no `qa.md`, and the story file is no longer stamped.
    """
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
    # The refused story is redocumented once the operator has acted — the flow that just
    # refused would refuse again on the same grounds, but a resume only pays off after
    # something changed, and this one goes on to build both stories.
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
    """A tainted story's required recheck parks for a human when it blocks — in either mode.

    The parametrisation is the point. Epic mode used to contain this finding in the queue
    while story mode failed, so the same refusal shipped a commit or didn't depending on how
    the run was launched. The two modes now agree, and this asserts they keep agreeing —
    including on where the resume lands: `finalize`, the state that refused, not `document`
    at the top of the story. Re-entering `document` would send a story that had already
    passed QA back through QA on the strength of a docs recheck.
    """
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
    # Documented three times: the initial pass, the final recheck that refused, and that
    # same recheck again on the operator's answer. QA ran once — the resume landed at
    # `finalize`, so nothing before it was repeated.
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
    """`failed` is not a second-class `blocked` — it is the same escalation.

    It used to be the one docs verdict that ended the run: a `WorkflowFailed` raised
    beside the `blocked` arm that parked. The distinction was
    never load-bearing — neither is fixable by running the same handoff again unchanged,
    and both need the same person to change the code, the spec or the plan — so the run
    now parks on the same gate either way, carrying the verdict that produced it.
    """
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
    # The gate names the verdict, not just the notes: "failed" and "blocked" reach the
    # same file and an operator has to be able to tell which one they are reading.
    assert "failed" in seen[0], seen[0]
    assert "the book's coverage check errored" in seen[0], seen[0]
    # This one refused before QA, so the resume does re-enter `document` and QA runs after.
    assert sub.calls.count("Docs") == 2, sub.calls
    assert sub.calls.count("Qa") == 1, sub.calls
    assert "feat(acme): story STORY-1" in _subjects(repo), _subjects(repo)


# ------------------------------------------------------------------- the nested drain


def test_a_drained_backlog_item_ships_in_the_storys_own_commit(
    epic: Callable[..., Path],
    workspace: Path,
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The drain nested inside the story, and the node id that keeps the two apart.

    `prepare_fix_story` exists because the nested drain runs in the *parent's* run scope: a
    second `prepare_story` call would overwrite the record `commit` reads to know which
    story it is committing, and the story would be committed under the drained item's slug.
    Both records surviving side by side is the assertion, and the single commit covering
    both is what the nesting is for.
    """
    repo = epic()
    write(repo / "docs" / "backlog.md", BACKLOG)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "File one fix")
    sub = _Sub(repo).install(monkeypatch)
    run_env = env()
    agent = _Agent()

    drive_flow(Coder(), run_env, agent)

    # The drain ran, on the graph's own prompts rather than the `fix` flow's.
    assert agent.calls == ["plan-story", "qa-fix-item"], agent.calls
    # Two story records, not one overwriting the other.
    assert _output(run_env, prepare_story)["story_slug"] == "STORY-1"
    assert _output(run_env, prepare_fix_story)["story_slug"] == FIX_SLUG
    # The shipped item left the backlog, and everything landed in one commit.
    assert _output(run_env, prune_fix_item)["pruned"] is True
    assert BULLET not in (repo / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert _output(run_env, check_repos_clean)["clean"] is True
    assert sub.calls.count("Docs") == 2, sub.calls
    assert _dirty(repo) == "", _dirty(repo)


def test_an_empty_backlog_skips_the_drain_entirely(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The draw is the loop's exit, and a repo with no backlog file takes it on the first pass."""
    repo = epic()
    _Sub(repo).install(monkeypatch)
    run_env = env()
    agent = _Agent()

    drive_flow(Coder(), run_env, agent)

    assert agent.calls == [], agent.calls
    assert _output(run_env, select_fix_item)["has_fix"] is False
    assert not (run_env.writer.run_dir / prepare_fix_story.__name__).exists()


# --------------------------------------------------------------------------- resume


def test_a_run_killed_in_qa_resumes_on_qa_without_rebuilding_the_story(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason `dev`, `review`, `document` and `qa` are four states and not one.

    A kill during QA must not re-run the implementation, and the checkpoint is what makes
    that true: the resumed run re-enters `qa` with the epic and both counters it was
    carrying, and `dev` is not called a second time. The sub-flow records the first run
    wrote are still in the run directory, which is what the resumed run's `self.output`
    reads its story back from.
    """
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
    assert resume.params["epic"] == EPIC, resume.params

    sub = _Sub(repo).install(monkeypatch)
    result = drive_flow(Coder(**resume.inputs), env(run_dir=run_dir), _Agent(), resume)

    assert result.has_epic is False, result
    assert "Dev" not in sub.calls, sub.calls
    assert sub.calls == ["Qa"], sub.calls


# ----------------------------------------------------------------- the CI operator gate


_test_bp = Blueprint("test")


def _red_ci(polls: list[str], green: dict[str, bool]) -> Any:
    """`poll_pr_checks`, red until the operator answers the gate.

    Stamped by a blueprint of its own and monkeypatched over the graph's global, which the
    engine resolves by the stamp — so the node id, the artifact directory and the reply
    schema are the real ones, and the state that calls it, the counter it spends and the
    gate above it are untouched.
    """

    @_test_bp.node
    def poll_pr_checks(logger: Any, repo_dir: str = "", branch: str = "") -> CiChecks:
        polls.append(branch)
        if green["yes"]:
            return CiChecks(status="passed", summary="")
        return CiChecks(status="failed", summary="the unit suite is red")

    return poll_pr_checks


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
    """`ci → repair_ci → ci` three times, then the gate — which is human whatever the mode.

    `operator_mode` is left at `auto` deliberately: the YAML records on the variable itself
    that this gate does not consult it, because a red PR that cannot be pushed is an
    infrastructure wall rather than a question an agent can answer by trying harder. The
    escalation is therefore reachable in the default configuration, which is exactly why it
    needs a test.

    The operator's answer resets the budget, so the fourth poll is a *fifth* call: four red
    ones spending three attempts, and one green one after the gate.
    """
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)
    polls: list[str] = []
    green = {"yes": False}
    monkeypatch.setattr(coder_workflow, "poll_pr_checks", _red_ci(polls, green))
    run_env = env()
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, green)):
        result = drive_flow(Coder(), run_env, _Agent())

    assert result.has_epic is False, result
    assert len(polls) == 5, polls
    # Every poll asked about the branch the PR is actually opened from. Handed the bare
    # epic instead, `find_open_pr` matches nothing, the gate reports `unavailable`, and the
    # flow passes that through — so the epic merges with CI never read and the log says
    # only what a tokenless run would say.
    assert set(polls) == {f"feat/{EPIC}"}, polls
    assert sub.calls.count("FixCi") == 3, sub.calls
    # The fix loop is handed that same branch; the epic name would push nothing.
    assert {c.branch for c in sub.calls_to("FixCi")} == {f"feat/{EPIC}"}
    # The note on the PR was attempted before the human was asked.
    assert _output(run_env, flag_ci_failure)["ci_flagged"] is False
    # The questions landed beside the epic they are about, and named the spent budget.
    assert len(seen) == 1, seen
    assert "after 3 automated attempt(s)" in seen[0], seen[0]
    assert (repo / "docs" / "epics" / EPIC / "ci-operator-context.md").is_file()


# -------------------------------------------------------------- the merge operator gate


def _failing_merge(merges: list[str], landed: dict[str, bool]) -> Any:
    """`merge_pr`, conflicted until the operator answers the gate.

    Seamed the same way `_red_ci` is, and for the same reason: offline the real node can
    only ever report `unavailable`, which is the arm that passes straight through to the
    next epic — so the whole rework side of the cluster is unreachable without it.
    """

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
    """One resolver turn, then the gate — not `MAX_MERGE_REWORKS` of them.

    A resolver saying the choice is not its to make is the one claim the re-merge cannot
    check: pushing an unresolved branch and merging again would spend the whole budget
    re-asking a turn that has already answered. So it goes straight to the gate the
    budget's own exhaustion goes to, and gets there carrying the resolver's reason.
    """
    repo = epic()
    _Sub(repo).install(monkeypatch)
    merges: list[str] = []
    landed = {"yes": False}
    monkeypatch.setattr(coder_workflow, "merge_pr", _failing_merge(merges, landed))
    run_env = env()
    seen: list[str] = []

    agent = _BlockedResolver()

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, landed)):
        result = drive_flow(Coder(), run_env, agent)

    assert result.has_epic is False, result
    # One turn, not three: the resolver was asked once and believed.
    assert agent.calls.count("fix-merge") == 1, agent.calls
    # Two merges: the conflicted one that raised the block, and the one after the answer.
    assert merges == [EPIC, EPIC], merges
    # The gate was reached with the budget untouched, so it names zero spent attempts.
    assert len(seen) == 1, seen
    assert "after 0 automated attempt(s)" in seen[0], seen[0]
    assert (repo / "docs" / "epics" / EPIC / "merge-operator-context.md").is_file()
