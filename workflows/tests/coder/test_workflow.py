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

from workhorse_workflows.coder import workflow as coder_workflow
from workhorse_workflows.coder.shared.backlog import prune_fix_item, select_fix_item
from workhorse_workflows.coder.shared.ci import poll_pr_checks
from workhorse_workflows.coder.nodes.pr import flag_ci_failure, merge_pr, open_pr, open_story_pr
from workhorse_workflows.coder.shared.queue import branch_story, commit_story, select_epic
from workhorse_workflows.coder.shared.story import prepare_fix_story, prepare_story
from workhorse_workflows.coder.shared.schemas.ci import CiChecks
from workhorse_workflows.coder.shared.schemas.dev import DevResult
from workhorse_workflows.coder.shared.schemas.docs import DocsResult
from workhorse_workflows.coder.shared.schemas.qa import QaFlowResult, QaResult
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

## Context

Users need a thing.

## Acceptance Criteria

- the thing exists

## Implementation Status

- **Status**: Not started
"""

#: One drainable backlog item, in the shape `select_fix_item` parses.
BULLET = "widget-pagination"
BULLET_TEXT = "the widget list does not paginate"
FIX_SLUG = "the-widget-list-does-not-paginate"
BACKLOG = f"""# Backlog

## Filed by coder

- [{BULLET}] {BULLET_TEXT}
"""


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

    Committed on purpose. `commit_story` reports whether the story's *work* landed, and an
    uncommitted fixture would make every story look like it built something; the zero-diff
    guard below is only testable against a repo whose only dirt is what the run made.
    """

    def _epic(count: int = 1) -> Path:
        slugs = [f"STORY-{n}" for n in range(1, count + 1)]
        stories = "\n".join(f"### {slug}\n\n- title: Story {slug}\n" for slug in slugs)
        write(
            repo / "docs" / "epics" / EPIC / "epic.md",
            f"---\ntitle: Epic One\nstatus: active\n---\n\n# Epic One\n\n## Stories\n\n{stories}",
        )
        for slug in slugs:
            write(
                repo / "docs" / "epics" / EPIC / "stories" / slug / "story.md",
                STORY_MD.format(title=f"Story {slug}"),
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


class _StubFlow(Workflow):
    """Every keyword the graph's five handoffs pass, because `Workflow` forbids extras.

    Declaring them all on one base is what makes the boundary assertion work in both
    directions: a keyword the graph stops passing is silently fine, and a keyword it starts
    passing that no flow declares fails construction — here, and in a real run, identically.
    """

    story: str = ""
    docs_path: str = ""
    epic: str = ""
    operator_mode: str = ""
    target_env: str = ""
    qa_stack_manifest: str = ""
    triage_scope_count: int = 0
    repo: str = ""
    branch: str = ""
    ci_summary: str = ""


class _Sub:
    """The five stand-ins, their call log, and the one file `dev` writes.

    `dev` writing a file is not decoration: `commit_story` asks git what changed, so a
    `dev` that only returned `ready` would make every story a zero-diff story and the
    happy path would trip the churn guard on its third iteration.
    """

    def __init__(
        self,
        repo: Path,
        *,
        changes: bool = True,
        dev_status: str = "ready",
        docs_status: str = "passed",
        qa_status: str = "passed",
        ci_status: str = "passed",
        explode: set[str] | None = None,
    ) -> None:
        self.repo = repo
        self.changes = changes
        self.dev_status = dev_status
        self.docs_status = docs_status
        self.qa_status = qa_status
        self.ci_status = ci_status
        self.explode = explode or set()
        self.calls: list[str] = []
        self.seen: list[Workflow] = []

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

    def _flow(self, name: str, reply: Callable[[Workflow], Any]) -> type:
        """A real `Workflow` subclass named for the flow it stands in for.

        The name matters twice over: `handoff` derives the recorded node id from it, and
        `_sub_scope` leaves an unclaimed class in its caller's environment — so a stub
        records under the same id, in the same run directory, as the flow it replaces.
        """
        calls, explode, seen = self.calls, self.explode, self.seen

        def start(child: Workflow) -> Done:
            calls.append(name)
            seen.append(child)
            if name in explode:
                raise RuntimeError(f"killed during {name}")
            return Done(reply(child))

        return type(name, (_StubFlow,), {"start": start})

    def calls_to(self, name: str) -> list[Workflow]:
        return [c for n, c in zip(self.calls, self.seen, strict=True) if n == name]

    # -- the replies, each the flow's own result model ---------------------

    def _dev(self, child: Workflow) -> DevResult:
        if self.changes:
            path = self.repo / "src" / f"{child.story}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {child.story}\n", encoding="utf-8")
        return DevResult(status=self.dev_status, operator_notes="rescope to the epic")

    def _review(self, child: Workflow) -> ReviewResult:
        return ReviewResult(status="approved", notes="")

    def _docs(self, child: Workflow) -> DocsResult:
        return DocsResult(status=self.docs_status, notes="")

    def _qa(self, child: Workflow) -> QaFlowResult:
        return QaFlowResult(
            status=self.qa_status,
            qa=QaResult(status=self.qa_status),
            qa_rework=1,
            triage_scope=child.triage_scope_count,
            operator_notes="",
        )

    def _fix_ci(self, child: Workflow) -> CiChecks:
        return CiChecks(status=self.ci_status, summary="")


# --------------------------------------------------------------------------- the agent


class _Agent:
    """The graph's own six prompts. Every other turn is inside a stubbed sub-flow.

    Only the drain reaches any of them in these tests, so the default handler asserts: a
    turn firing where none was expected is a routing bug, and a permissive stub would let it
    through as a pass.
    """

    def __init__(self, *, services: list[dict[str, Any]] | None = None) -> None:
        self.services = services if services is not None else []
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
        return {"status": "done", "summary": "one AC, one fix"}

    def _qa_fix_item(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"status": "passed", "notes": ""}


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


# ------------------------------------------------------------------ the epic happy path


def test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole loop in one pass: queue → story → PR → CI → merge → empty queue.

    The five sub-flows come back in the YAML's order and `docs` twice — once as the story's
    own documentation pass and once as `final_docs`, after the drain, which is the pass that
    exists so a fix drained behind the story is in the book before the single commit that
    covers both. Both are asserted, because collapsing them is the obvious wrong
    simplification and nothing else in the graph would notice.
    """
    repo = epic()
    sub = _Sub(repo).install(monkeypatch)
    run_env = env()

    result = drive_flow(Coder(), run_env, _Agent())

    assert result.has_epic is False, result
    assert sub.calls == ["Dev", "Review", "Docs", "Qa", "Docs"], sub.calls
    # The story built, and its work landed as one commit.
    assert _output(run_env, commit_story)["committed"] is True
    assert _dirty(repo) == "", _dirty(repo)
    assert (repo / "src" / "STORY-1.py").is_file()
    # The epic was popped off the queue before its PR was opened.
    assert EPIC not in (repo / "docs" / "epics" / "index.md").read_text(encoding="utf-8")
    # ...and the run ended because the queue is empty, not because anything failed.
    assert _output(run_env, select_epic)["reason"], _output(run_env, select_epic)


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
    without a GitHub token can ever finish an epic. The branch the gate polls is asserted
    here too: it is the bare epic name while the branch that exists is `feat/<epic>`, which
    is the inert-gate defect recorded in the progress ledger and preserved by this port.
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
    assert sub.calls == ["Dev", "Review", "Docs", "Qa", "Docs"], sub.calls
    # The queue was never consulted, and the epic PR cluster was never entered.
    assert not (run_env.writer.run_dir / select_epic.__name__).exists()
    assert not (run_env.writer.run_dir / open_pr.__name__).exists()
    # The branch the PR was opened from is the one `branch_story` cut.
    assert _output(run_env, open_story_pr)["story_pr"] == "skipped"
    assert _head(repo) == _output(run_env, branch_story)["story_branch"]


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


# ------------------------------------------------------------------- the counters


def test_three_stories_in_a_row_that_commit_nothing_stop_the_run(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The churn guard, and the run-global counter that carries it between stories.

    `zero_diff` is threaded through eight states to get from one story's commit to the
    next's, which is the noisiest thing in the port and the thing this test exists to hold
    down. Three stories that build nothing is not three failures — each one is allowed —
    it is a loop that is not making progress, and the run stops rather than walking the rest
    of the epic producing nothing.

    Four stories, not three, and the reason is behavior worth pinning: `branch_epic`
    reconciles the epic queue from the base branch by writing back what `git show` returns,
    and `git show` drops the file's trailing newline. So cutting the epic branch always
    leaves `docs/epics/index.md` one byte dirty, and the *first* story of any epic commits
    that byte whatever else it did. The YAML does exactly the same — its `branch-epic.py`
    is the same three lines — so the port keeps it and the test counts from the second
    story.
    """
    repo = epic(count=4)
    sub = _Sub(repo, changes=False).install(monkeypatch)

    with pytest.raises(WorkflowFailed, match="in a row committed no changes"):
        drive_flow(Coder(), env(), _Agent())

    # Four stories were built before the guard tripped, not one and not the whole epic.
    assert sub.calls.count("Dev") == 4, sub.calls
    assert _dirty(repo) == "", _dirty(repo)


def test_a_commit_that_lands_resets_the_zero_diff_counter(
    epic: Callable[..., Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the guard: *consecutive*, not cumulative.

    Three stories that each land a commit walk the whole epic and reach the PR, which is
    what says the counter resets rather than accumulating — and a three-story epic is the
    smallest one that can tell the difference.
    """
    repo = epic(count=3)
    sub = _Sub(repo).install(monkeypatch)
    run_env = env()

    result = drive_flow(Coder(), run_env, _Agent())

    assert result.has_epic is False, result
    assert sub.calls.count("Dev") == 3, sub.calls
    assert _output(run_env, open_pr)["should_gate"] is True


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
        def _qa(self, child: Workflow) -> QaFlowResult:
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
    _Sub(repo).install(monkeypatch)
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
    assert _output(run_env, commit_story)["committed"] is True
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
    assert resume.params["zero_diff"] == 0, resume.params

    sub = _Sub(repo).install(monkeypatch)
    result = drive_flow(Coder(**resume.inputs), env(run_dir=run_dir), _Agent(), resume)

    assert result.has_epic is False, result
    assert "Dev" not in sub.calls, sub.calls
    assert sub.calls == ["Qa", "Docs"], sub.calls


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

    with patch.object(pyflow_driver, "poll_until_touched", _answers(seen, green)):
        result = drive_flow(Coder(), run_env, _Agent())

    assert result.has_epic is False, result
    assert len(polls) == 5, polls
    assert sub.calls.count("FixCi") == 3, sub.calls
    # The note on the PR was attempted before the human was asked.
    assert _output(run_env, flag_ci_failure)["ci_flagged"] is False
    # The questions landed beside the epic they are about, and named the spent budget.
    assert len(seen) == 1, seen
    assert "after 3 automated attempt(s)" in seen[0], seen[0]
    assert (repo / "docs" / "epics" / EPIC / "ci-operator-context.md").is_file()
