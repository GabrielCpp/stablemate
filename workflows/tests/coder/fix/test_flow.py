"""End-to-end tests for the `fix` flow — the standalone backlog drain.

Twenty-four YAML nodes became nine states around one loop that re-enters at the draw. What
is worth testing is what each iteration does to the backlog file, because that file *is* the
worklist: a shipped item leaves it, a stuck item stays with a `(blocked` marker every later
draw skips, and an empty section is what ends the run. So the tests are organised by what
the bullet looks like afterwards.

**There are no seams here beyond the agent turn.** `select_fix_item` really parses a real
`docs/backlog.md`, `seed_fix_story` really creates the `fixes` bucket and really authors the
story ostler then loads back, `resolve_impl_context` really decodes the plan against a real
workspace, `branch_code_repos` really visits the code repo, `commit_story` really commits,
and the `docs` handoff really runs the whole `docs` flow — its OKF pre-gate, its grounding
gate and its reviewer — against a real graph. That last one is the point of the handoff test:
the sub-flow is not stubbed, so what crosses the boundary is what would cross it in a run.

The scripted agent dispatches on the prompt's filename, the same key the engine derives its
node id from, and every handler leaves behind the artifacts its reply claims — the plan turn
writes `plan-context.json` and the per-service plan file, the implement turn writes the code
change the commit then finds. A handler that only returned a status would be testing the
state machine against a fiction.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.fix.flow import Fix
from workhorse_workflows.coder.shared.backlog import mark_fix_blocked, prune_fix_item
from workhorse_workflows.coder.shared.dev import branch_code_repos, resolve_impl_context

BULLET = "widget-pagination"
TEXT = "the widget list does not paginate"
#: `_fix_slug` kebabs the bullet *text*, so the story folder is named after the sentence.
SLUG = "the-widget-list-does-not-paginate"
#: The bucket is self-created by `seed_fix_story`, and ostler numbers epic directories in
#: creation order — in a fresh docs tree the `fixes` bucket is the first, hence `0001-`.
STORY_REL = f"docs/epics/0001-fixes/stories/{SLUG}"

BACKLOG = f"""# Backlog

## Filed by coder

- [{BULLET}] {TEXT}
"""

#: The one service the plan turn declares. It lives *outside* the docs worktree, which is
#: the multi-repo shape — and therefore the `semantic` route through the `docs` sub-flow.
API_SERVICE: dict[str, Any] = {
    "repo": "api",
    "path": ".",
    "type": "go",
    "plan_file": "plan-api.md",
    "skills": [],
}

#: A second service, to drive the divergence the module docstring records: the YAML wires
#: `implement_fix` straight to `check_fix`, so only the first of these is ever implemented.
WEB_SERVICE: dict[str, Any] = {
    "repo": "web",
    "path": ".",
    "type": "react-router",
    "plan_file": "plan-web.md",
    "skills": [],
}


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def docs(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """The docs repo, carrying a backlog with one drainable item and nothing else.

    Deliberately no epic and no story: the drain creates both. `seed_fix_story` self-creates
    the `fixes` bucket the first time it needs one, and a fixture that pre-made it would hide
    whether that path runs.
    """
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


# --------------------------------------------------------------------------- the agent


class _Agent:
    """The flow's four prompts plus the `docs` sub-flow's two, scripted on the flow's arms.

    `plan_blocked` blocks the first N planning turns, `qa_fails` fails the first N QA turns
    — one is the retry, two is the give-up — and `services` is what the plan declares.
    `explode` raises on a named prompt, which is a run killed mid-turn.
    """

    def __init__(
        self,
        workspace: dict[str, Path],
        *,
        services: list[dict[str, Any]] | None = None,
        plan_blocked: int = 0,
        qa_fails: int = 0,
        review_blocks: bool = False,
        explode: set[str] | None = None,
    ) -> None:
        self.workspace = workspace
        self.services = services if services is not None else [API_SERVICE]
        self.plan_blocked = plan_blocked
        self.qa_fails = qa_fails
        self.review_blocks = review_blocks
        self.explode = explode or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    # -- the seam ---------------------------------------------------------

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

    # -- the fix flow's four ----------------------------------------------

    def _plan_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Write the spec dir the planner is told to write, then report on it.

        The plan is written even on the blocked pass, exactly as a real planner's partial
        work would be: the flow's `blocked` arm has to be what stops the run, not the
        absence of a file downstream states would have tripped over anyway.
        """
        spec = Path(data["spec_dir"])
        spec.mkdir(parents=True, exist_ok=True)
        for svc in self.services:
            (spec / svc["plan_file"]).write_text(f"# Plan for {svc['repo']}\n", encoding="utf-8")
        (spec / "plan-context.json").write_text(
            json.dumps(
                {
                    "story": SLUG,
                    "services": self.services,
                    "implementation_order": [f"{s['repo']}::{s['path']}" for s in self.services],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if nth <= self.plan_blocked:
            return {"status": "blocked", "summary": "the pagination contract is undecided"}
        return {"status": "done", "summary": f"plan {nth}"}

    def _implement_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Write the change, so the commit at the end of the iteration has something to find."""
        repo = self.workspace[Path(data["plan_file"]).stem.removeprefix("plan-")]
        (repo / "pagination.go").write_text(f"// pass {nth}\n", encoding="utf-8")
        return {"status": "done", "notes": f"implemented {data['service_path']}"}

    def _qa_fix_item(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.qa_fails:
            return {"status": "failed", "notes": f"page two is still empty (check {nth})"}
        return {"status": "passed", "notes": "pagination works"}

    def _apply_qa_fixes(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": "fixed", "notes": "widened the page window"}

    # -- the `docs` sub-flow's two ----------------------------------------

    def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {
            "status": "documented",
            "nodes": ["docs/features/widget.md"],
            "notes": f"documented on pass {nth}",
        }

    def _review_story_documentation(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.review_blocks:
            return {"status": "blocked", "notes": "this change cannot be described as built"}
        return {"status": "approved", "notes": "reads as built"}


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


def _branch_of(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


# --------------------------------------------------------------------------- happy path


def test_one_item_is_seeded_planned_implemented_checked_pruned_and_committed(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A whole iteration, and the second draw that ends the run.

    Every claim the flow makes about a drained item is checked against the file it changed:
    the story exists and carries the bullet as its single AC, the bullet is gone from the
    backlog, and the code repo has a commit naming the story.
    """
    agent = _Agent(workspace)
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    # The run ends on a dry draw, and the terminal carries the reason it was dry.
    assert result.has_fix is False, result
    assert "no drainable bullet" in result.reason, result

    assert agent.counts() == {
        "plan-story": 1,
        "implement-plan": 1,
        "qa-fix-item": 1,
        "document-story": 1,
        "review-story-documentation": 1,
    }, agent.counts()

    # `seed_fix_story` authored the story rather than merely scaffolding it: the bullet is
    # the single acceptance criterion, which is the flow's "one fix, one AC" rule on disk.
    story = (docs / STORY_REL / "story.md").read_text(encoding="utf-8")
    assert f"- {TEXT}" in story, story
    assert BULLET in story, story

    # The item left the backlog, and the section it left is still there.
    assert BULLET not in _backlog(docs), _backlog(docs)
    assert "## Filed by coder" in _backlog(docs)

    # And the change was committed in the repo the plan named, with no push and no PR — as a
    # Conventional Commit `fix` scoped to that repo, because release-please reads the subject.
    assert _log_of(workspace["api"])[0] == f"fix(api): {SLUG}"
    assert (workspace["api"] / "pagination.go").is_file()


def test_the_drain_keeps_going_until_the_section_is_empty(
    docs: Path,
    workspace: dict[str, Path],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`commit_fix_item.next` is the draw, so two items are two full iterations in one run.

    The commit-per-item rule is what this asserts: two drained items are two commits, not one
    squashed at the end. That is the whole difference between this flow and the main graph's
    nested drain, which lets its changes ride the story's own commit.
    """
    write(
        docs / "docs" / "backlog.md",
        BACKLOG + "- [mobile-pagination] the mobile widget list does not paginate\n",
    )
    agent = _Agent(workspace)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["plan-story"] == 2, agent.counts()
    assert agent.counts()["qa-fix-item"] == 2, agent.counts()
    assert "widget-pagination" not in _backlog(docs), _backlog(docs)
    assert "mobile-pagination" not in _backlog(docs), _backlog(docs)
    assert len([line for line in _log_of(workspace["api"]) if line.startswith("fix(api):")]) == 2


# --------------------------------------------------------------------------- the two flags


def test_a_blocked_plan_flags_the_bullet_without_spending_an_implement_turn(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The first of the two ways an item is flagged, and the cheapest.

    A blocked plan skips implementation and QA entirely — and the annotated bullet is what
    stops the very next draw from picking it up again, which is what keeps a permanently
    stuck item from spinning the loop.
    """
    agent = _Agent(workspace, plan_blocked=1)
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    assert result.has_fix is False, result
    assert "implement-plan" not in agent.counts(), agent.counts()
    assert "qa-fix-item" not in agent.counts(), agent.counts()
    assert agent.counts()["plan-story"] == 1, agent.counts()

    line = next(ln for ln in _backlog(docs).splitlines() if BULLET in ln)
    assert "(blocked" in line, line
    assert "plan blocked" in line, line
    assert _output(run_env, mark_fix_blocked)["marked"] is True


def test_qa_gets_exactly_one_retry_and_the_fixer_is_handed_the_first_verdict(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`check → apply once → recheck`, and the notes that cross between the three.

    `qa_notes` was `get_node_output('check_fix','qa_result').notes` in the YAML. Agent turns
    are not nodes here, so it is threaded as a state argument — this is the assertion that
    says the value still arrives.
    """
    agent = _Agent(workspace, qa_fails=1)
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    assert result.has_fix is False, result
    assert agent.counts()["qa-fix-item"] == 2, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
    assert agent.args_for("apply-qa-fixes")[0]["qa_notes"] == "page two is still empty (check 1)"

    # The recheck passed, so the item shipped.
    assert BULLET not in _backlog(docs), _backlog(docs)
    assert _output(run_env, prune_fix_item)["pruned"] is True


def test_a_second_failing_check_flags_rather_than_retrying_again(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The retry is one, not a loop — the drain never escalates and never spins."""
    agent = _Agent(workspace, qa_fails=2)
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    assert result.has_fix is False, result
    assert agent.counts()["qa-fix-item"] == 2, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()

    line = next(ln for ln in _backlog(docs).splitlines() if BULLET in ln)
    assert "(blocked" in line, line
    assert "QA still failing after one retry" in line, line
    # Flagged, not deleted: a human still sees it.
    assert BULLET in _backlog(docs)


# ------------------------------------------------------------------- dispatch and layers


def test_only_the_first_service_layer_is_implemented(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The YAML's `implement_fix.next: check_fix`, preserved — and pinned here.

    `flows.dev` loops back to its layer selector; this flow does not, so a plan dispatching
    two services gets one of them implemented and is then QA'd as a whole. It reads far more
    like an omission than a decision, which is exactly why it is a test: the behavior is
    recorded rather than quietly repaired, and a later decision to loop will fail here.
    """
    agent = _Agent(workspace, services=[API_SERVICE, WEB_SERVICE])
    run_env = env()

    drive_flow(Fix(), run_env, agent)

    assert agent.counts()["implement-plan"] == 1, agent.counts()
    assert agent.args_for("implement-plan")[0]["plan_file"] == "plan-api.md"
    # Both layers were dispatched; only the first was implemented.
    assert len(_output(run_env, resolve_impl_context)["dispatch_list"]) == 2


def test_a_plan_that_dispatches_no_layer_is_still_checked(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`decide_fix_layer`'s `"no"` arm: a fix that changes only documents is legitimate."""
    agent = _Agent(workspace, services=[])
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    assert result.has_fix is False, result
    assert "implement-plan" not in agent.counts(), agent.counts()
    assert agent.counts()["qa-fix-item"] == 1, agent.counts()
    assert BULLET not in _backlog(docs), _backlog(docs)


def test_the_implement_turn_is_handed_the_three_values_its_prompt_reads(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`implement-plan.md` reads three values this YAML node never passed.

    Same divergence `flows.dev` records and for the same reason: under the YAML engine
    `resolve_fix_impl_context`'s declared outputs landed in the run context and the prompt
    rendered against the whole of it. `Engine.agent` renders against `args` alone.
    """
    agent = _Agent(workspace)
    run_env = env()

    drive_flow(Fix(), run_env, agent)

    first = agent.args_for("implement-plan")[0]
    impl = _output(run_env, resolve_impl_context)
    assert first["qa_run_plan"] == impl["qa_run_plan"]
    assert first["impl_instruction_paths"] == impl["impl_instruction_paths"]
    assert first["qa_stack"] == impl["qa_stack"]


def test_the_repos_are_branched_onto_the_current_branch_not_a_fix_branch(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`branch_fix_code_repos` is called with `spec_dir` alone — the recorded divergence.

    `flows.dev` passes the story branch; this node's YAML argument list is one entry long, so
    the branch defaults to the docs repo's *current* branch. The repos stay on `main` and the
    commits land there, which is what "commit this one drained item onto the CURRENT branch"
    meant. Passing `self.docs_path` or a derived branch here would change that silently.
    """
    agent = _Agent(workspace)
    run_env = env()

    drive_flow(Fix(), run_env, agent)

    outcome = _output(run_env, branch_code_repos)
    assert outcome["branched"] == [], outcome
    assert outcome["already_on_branch"] == ["api"], outcome
    assert _branch_of(workspace["api"]) == "main"


# --------------------------------------------------------------------------- documentation


def test_the_docs_sub_flow_runs_for_real_and_its_verdict_gates_the_commit(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`document_fix_item` is a `type: flow`, so the whole `docs` flow runs per drained item.

    This is the handoff under test rather than stubbed: the sub-flow's own OKF pre-gate finds
    the `docs/epics` tree the seeder just created, takes the `semantic` route because the code
    repo is outside the docs worktree, and spends its two turns. Both are counted here, on the
    same scripted agent — a handoff shares the environment, only the writer is subscoped.
    """
    agent = _Agent(workspace)
    run_env = env()

    drive_flow(Fix(), run_env, agent)

    assert agent.counts()["document-story"] == 1, agent.counts()
    assert agent.counts()["review-story-documentation"] == 1, agent.counts()
    # The sub-flow was handed this iteration's story and its self-created bucket.
    assert agent.args_for("document-story")[0]["story_path"].endswith("story.md")
    # And the commit is downstream of it: documentation gates the commit, not the reverse.
    assert _log_of(workspace["api"])[0] == f"fix(api): {SLUG}"


def test_documentation_that_cannot_converge_fails_the_run_before_the_commit(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`fix_documentation_failed` was a `type: fail`, and this is the arm that reaches it.

    A blocked reviewer is the sub-flow saying the story cannot be documented as it stands.
    That failure crosses the handoff boundary — `Engine.handoff` does not catch it — and the
    fix flow does not swallow it either: nothing is committed and the drain stops here rather
    than moving on to the next bullet.

    It also pins the ordering, which is not free: the prune runs *before* the documentation,
    so a run that dies here has already taken the bullet off the backlog while leaving the
    work uncommitted. That is the YAML's wiring (`prune_fix_item.next: document_fix_item`)
    and it is preserved, but it means the failed item is not re-drawn on the next run.
    """
    agent = _Agent(workspace, review_blocks=True)

    with pytest.raises(WorkflowFailed):
        drive_flow(Fix(), env(), agent)

    assert "fix(api):" not in "".join(_log_of(workspace["api"]))
    assert BULLET not in _backlog(docs), _backlog(docs)


# --------------------------------------------------------------------------- resume


def test_a_run_killed_mid_check_resumes_at_the_check(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The checkpoint is written before a state runs, so the drawn item survives the kill.

    This is the resume shape the port has to match: the state, the flow name, and inputs that
    reconstruct the workflow. The resumed run re-enters on `check` — it does not re-draw a
    different item, it does not re-plan, and it does not implement a second time.
    """
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
    assert "plan-story" not in agent.counts(), agent.counts()
    assert "implement-plan" not in agent.counts(), agent.counts()
    assert agent.counts()["qa-fix-item"] == 1, agent.counts()
    assert BULLET not in _backlog(docs), _backlog(docs)
