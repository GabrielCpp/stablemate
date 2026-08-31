"""End-to-end tests for the `fix` flow — the standalone backlog drain.

Twenty-four YAML nodes became eight states around one loop that re-enters at the draw. What
is worth testing is what each iteration does to the backlog file, because that file *is* the
worklist: a shipped item leaves it, a stuck item stays with a `(blocked` marker every later
draw skips, and an empty section is what ends the run. So the tests are organised by what
the bullet looks like afterwards.

**There are no seams here beyond the agent turn.** `select_fix_item` really parses a real
`docs/backlog.md`, `seed_fix_story` really creates the `fixes` bucket and really authors the
story ostler then loads back, the gates really shell out to the repo's own Makefile,
`commit_story` really commits, and the `docs` handoff really runs the whole `docs` flow —
its OKF pre-gate, its grounding gate and its reviewer — against a real graph. That last one
is the point of the handoff test: the sub-flow is not stubbed, so what crosses the boundary
is what would cross it in a run.

The scripted agent dispatches on the prompt's filename, the same key the engine derives its
node id from, and every handler leaves behind the artifacts its reply claims — the fix turn
writes the code change the gates then judge and the commit then finds. A handler that only
returned a status would be testing the state machine against a fiction.

**One turn per item** is the shape under test. There is no plan turn and no dispatch list:
`fix-item.md` plans and writes the repair in one session, the gates that judge it are
Python's, and the repositories they run in are the ones git says the turn changed.
"""
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
#: `_fix_slug` kebabs the bullet *text*, so the story folder is named after the sentence.
SLUG = "the-widget-list-does-not-paginate"
#: The bucket is self-created by `seed_fix_story`, and ostler numbers epic directories in
#: creation order — in a fresh docs tree the `fixes` bucket is the first, hence `0001-`.
STORY_REL = f"docs/epics/0001-fixes/stories/{SLUG}"

BACKLOG = f"""# Backlog

## Filed by coder

- [{BULLET}] {TEXT}
"""

#: A `lint` target `make -n` accepts and `make` fails, so the repo's own gate goes red on
#: exactly the pass that installs it. The gates resolve `make <gate>` by convention when a
#: service declares nothing, which is the whole check for a repo-wide repair.
RED_MAKEFILE = "lint:\n\t@echo 'pagination.go:1: undefined: pageSize'; exit 1\n"


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
    """Two real code repos and the workspace file that names them, outside the docs tree.

    Two rather than one because the lane's targets are git-derived now: the second repo is
    what proves an untouched checkout is neither gated nor committed.
    """
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
    """The flow's three prompts plus the `docs` sub-flow's three, scripted on the flow's arms.

    `impl_blocked` blocks the first N fix turns, `gate_red` leaves a failing gate behind on
    the first N of them, `qa_fails` fails the first N QA turns — one is the retry, two is the
    flag — and `apply_blocked` blocks the retry itself. `explode` raises on a named prompt,
    which is a run killed mid-turn.
    """

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

    # -- the fix flow's three ---------------------------------------------

    def _fix_item(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Write the change, so the gates and the commit have something to find.

        `impl_blocked` blocks the first N turns and — the part that matters — writes
        *nothing* while doing so, which is the state the drain used to QA as if it were a
        fix. `gate_red` writes a Makefile whose `lint` target fails, and stops writing it
        once the budget is spent, so a repair lap is something the run can come back from.
        """
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
        """The repair lap: the same writer, counted as one pass further on.

        Two prompts, one worker — the flow dispatches a different file for a red gate, and
        what the scripted agent does about it is what it did before: write the next pass,
        and stop leaving a red Makefile behind once the `gate_red` budget is spent.
        """
        return self._fix_item(data, nth + self.counts()["fix-item"])

    def _qa_fix_item(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.qa_fails:
            return {"status": "failed", "notes": f"page two is still empty (check {nth})"}
        return {"status": "passed", "notes": "pagination works"}

    def _apply_qa_fixes(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.apply_blocked:
            return {"status": "blocked", "notes": "QA wants a page size nobody has picked"}
        return {"status": "passed", "notes": "widened the page window"}

    # -- the `docs` sub-flow's three --------------------------------------

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
        """The author's say on a documentation block, which this fake declines to give.

        `docs` puts every block to the author before ending its flow, so this turn is on the
        blocked path whether the test asked for it or not. Escalating keeps the verdict the
        reviewer's — the branch this file is actually about.
        """
        return {"decision": "escalated", "summary": "no answer to give"}

    def _review_story_documentation(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.review_blocks:
            return {"status": "blocked", "notes": "this change cannot be described as built"}
        return {"status": "approved", "notes": "reads as built"}


def _answers(seen: list[str]) -> Callable[..., None]:
    """A stand-in for the human the `Await` is waiting on.

    Patched over `wait_for_answer`, so it runs where the operator's edit would land: the
    questions are already in the file by then, which is what `seen` records, and writing the
    answer over them is what a person answering in place does.
    """

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
    assert subject.endswith(f" [{story_id}]")


def _branch_of(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


# --------------------------------------------------------------------------- happy path


def test_one_item_is_seeded_fixed_checked_pruned_and_committed(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A whole iteration, and the second draw that ends the run.

    Every claim the flow makes about a drained item is checked against the file it changed:
    the story exists and carries the bullet as its single AC, the bullet is gone from the
    backlog, and the code repo has a commit naming the story.

    The count is the one-turn shape on the outside: one `fix-item`, not a plan turn and an
    implement turn.
    """
    agent = _Agent(workspace)
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    # The run ends on a dry draw, and the terminal carries the reason it was dry.
    assert result.has_fix is False, result
    assert "no drainable bullet" in result.reason, result

    assert agent.counts() == {
        "fix-item": 1,
        "qa-fix-item": 1,
        "document-story": 1,
        "review-story-documentation": 1,
    }, agent.counts()

    # `seed_fix_story` authored the story rather than merely scaffolding it: the bullet is
    # the single acceptance criterion, which is the flow's "one fix, one AC" rule on disk.
    story = (docs / STORY_REL / "story.md").read_text(encoding="utf-8")
    assert f"- {TEXT}" in story, story
    assert BULLET in story, story
    assert "## Non-Functional Acceptance Criteria\n\n(none)" in story, story
    assert (
        "## Technical Notes\n\nNo prior implementation reference exists." in story
    ), story

    # The item left the backlog, and the section it left is still there.
    assert BULLET not in _backlog(docs), _backlog(docs)
    assert "## Filed by coder" in _backlog(docs)

    # And the change was committed in the repo git says it landed in, with no push and no
    # PR — a Conventional Commit `fix` scoped to that repo, because release-please reads it.
    story_id = str(agent.args_for("fix-item")[0]["story_id"])
    subject = _log_of(workspace["api"])[0]
    assert subject.startswith("fix(api): ")
    assert subject.endswith(f" [{story_id}]")
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
    """`fix-item.md` is the first-lap prompt, and a first lap has no gate to report.

    The two arrivals used to share one file, which is why the turn was handed a literal
    saying no gate had run and a paragraph teaching it to tell the two apart from that
    string. The flow knows which lap it is dispatching, so it names the prompt — and an
    argument the first-lap template never reads is not passed to it either.
    """
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
    """`commit`'s next is the draw, so two items are two full iterations in one run.

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
    assert agent.counts()["fix-item"] == 2, agent.counts()
    assert agent.counts()["qa-fix-item"] == 2, agent.counts()
    assert "widget-pagination" not in _backlog(docs), _backlog(docs)
    assert "mobile-pagination" not in _backlog(docs), _backlog(docs)
    assert len([line for line in _log_of(workspace["api"]) if line.startswith("fix(api):")]) == 2


# --------------------------------------------------------------------------- the gates


def test_a_red_gate_buys_a_repair_lap_and_hands_the_turn_its_output(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The deterministic half of the collapsed split: git names the repos, `make` judges them.

    The turn is re-entered rather than a fresh one dispatched — same session, same story —
    and what it is handed is the gate's own output, not a summary of it.
    """
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

    # The lap converged, so the item shipped like any other.
    assert BULLET not in _backlog(docs), _backlog(docs)


def test_a_gate_still_red_when_the_laps_run_out_parks_rather_than_giving_up(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A spent repair budget is a block, not a `WorkflowFailed` — AGENTS.md's rule, here.

    The escalation publishes the gate's own output so whoever answers is not re-deriving it,
    and the answered run comes back into the same turn and finishes the item.
    """
    agent = _Agent(workspace, gate_red=MAX_FIX_LAPS)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result

    (gate,) = seen
    assert "lint gate on the fix-drain item" in gate, gate
    assert f"after {MAX_FIX_LAPS} repair lap(s)" in gate, gate
    assert "undefined: pageSize" in gate, gate

    # Three laps inside the budget, then the turn the operator's answer re-enters. The first
    # is the first-pass prompt and every one after it is the repair prompt — the answer is
    # ground truth added to a lap, not a third arrival with a file of its own.
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
    """The targets are git's account of the change, not the workspace manifest's list.

    `web` is in the manifest and reachable by every turn, and the item never touched it: its
    gates are not run and it gets no empty commit. A repo the manifest merely *lists* is not
    a repo this item changed.
    """
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

    # The red gate in `web` was never run: it is not this item's repo.
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
    """No story branch, no fix branch — "commit this one drained item onto the CURRENT branch".

    The lane branched nothing before and branches nothing now; what changed is that the call
    claiming to is gone. It resolved its repos from plan context, and with the plan turn
    deleted it would have branched an empty list under a name that said otherwise.
    """
    agent = _Agent(workspace)

    drive_flow(Fix(), env(), agent)

    assert _branch_of(workspace["api"]) == "main"
    assert _branch_of(docs) == "main"
    _assert_agent_story_commit(workspace["api"], agent)


# --------------------------------------------------------------------------- the QA tail


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
    """The retry is one, not a loop — a QA verdict the drain believes never escalates."""
    agent = _Agent(workspace, qa_fails=2)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["qa-fix-item"] == 2, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()

    line = next(ln for ln in _backlog(docs).splitlines() if BULLET in ln)
    assert "(blocked" in line, line
    assert "QA still failing after one retry" in line, line
    # Flagged, not deleted: a human still sees it.
    assert BULLET in _backlog(docs)


def test_a_retry_that_says_it_cannot_parks_instead_of_rechecking_nothing(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`apply_once`'s verdict was parsed and dropped, so a blocked fixer was rechecked anyway.

    The recheck then failed — over an unchanged worktree — and the bullet was flagged as if
    QA had failed twice, which is a false answer to a question nobody asked. It parks now,
    and the answer re-enters the fix turn with the operator's words in the prompt.
    """
    agent = _Agent(workspace, qa_fails=1, apply_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result

    (gate,) = seen
    assert "QA wants a page size nobody has picked" in gate, gate

    # One retry, no second one, and no recheck over the empty worktree.
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
    """The fifth lane's copy of the dropped-verdict bug, from the outside.

    The implementation verdict was discarded, so a turn reporting it could not write the fix
    went straight to QA over an unchanged worktree — and the QA verdict that followed flagged
    the *bullet* as unfixable. The block now parks on the drained story's own `context.md`,
    and the answer re-enters the same state with the operator's words in the prompt.
    """
    agent = _Agent(workspace, impl_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result

    # The gate is beside the drained item, and it publishes what the turn actually said.
    (gate,) = seen
    assert "the page size is a product decision nobody has made" in gate, gate
    assert "implementation stage, the fix-drain implementation turn" in gate, gate
    assert SLUG in gate, gate

    # No QA turn was spent on the empty worktree: the second fix turn is what the first
    # check sees, and it carries the answer.
    assert agent.counts()["fix-item"] == 2, agent.counts()
    assert agent.counts()["qa-fix-item"] == 1, agent.counts()
    retried = agent.args_for("fix-item")[1]
    assert "Twenty per page" in retried["operator_context"], retried

    # And the iteration finishes as any other: the bullet is drained, not flagged.
    assert BULLET not in _backlog(docs), _backlog(docs)
    _assert_agent_story_commit(workspace["api"], agent)


def test_a_blocked_item_is_flagged_and_the_next_draw_skips_it(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The annotated bullet is what stops the very next draw from picking it up again.

    Without it the loop re-draws the item it just failed on, forever. This is the property
    the flag exists for, and it is what keeps a permanently stuck item from spinning the
    drain.
    """
    agent = _Agent(workspace, qa_fails=2)
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    assert result.has_fix is False, result
    assert agent.counts()["fix-item"] == 1, agent.counts()
    assert _output(run_env, mark_fix_blocked)["marked"] is True


# --------------------------------------------------------------------------- documentation


def test_the_docs_sub_flow_runs_for_real_and_its_verdict_gates_the_commit(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`document` is a handoff, so the whole `docs` flow runs per drained item.

    This is the handoff under test rather than stubbed: the sub-flow's own OKF pre-gate finds
    the `docs/epics` tree the seeder just created, takes the `semantic` route because the code
    repo is outside the docs worktree, and spends its two turns. Both are counted here, on the
    same scripted agent — a handoff shares the environment, only the writer is subscoped.
    """
    agent = _Agent(workspace)

    drive_flow(Fix(), env(), agent)

    assert agent.counts()["document-story"] == 1, agent.counts()
    assert agent.counts()["review-story-documentation"] == 1, agent.counts()
    # The sub-flow was handed this iteration's story and its self-created bucket.
    assert agent.args_for("document-story")[0]["story_path"].endswith("story.md")
    # The agent's source commit is what gives documentation exact provenance to inspect.
    _assert_agent_story_commit(workspace["api"], agent)


def test_documentation_that_cannot_converge_preserves_the_agent_commit(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blocked reviewer is the sub-flow saying the story cannot be documented as it stands.

    That failure crosses the handoff boundary — `Engine.handoff` does not catch it — and the
    fix flow does not swallow it either. The agent's attributed source commit remains as
    evidence, while the drain stops rather than moving on to the next bullet.

    It also pins the ordering, which is not free: the prune runs *before* documentation, so
    a run that dies here has taken the bullet off the backlog while preserving the attributed
    source commit. That is the wiring, and it means the failed item is not re-drawn.
    """
    agent = _Agent(workspace, review_blocks=True)

    with pytest.raises(WorkflowFailed):
        drive_flow(Fix(), env(), agent)

    _assert_agent_story_commit(workspace["api"], agent)
    assert BULLET not in _backlog(docs), _backlog(docs)


# --------------------------------------------------------------------------- resume


def test_a_run_killed_mid_check_resumes_at_the_check(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The checkpoint is written before a state runs, so the drawn item survives the kill.

    This is what the expensive turn being a state of its own buys: the resumed run re-enters
    on `check`. It does not re-draw a different item, and it does not write the fix twice.
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
    assert "fix-item" not in agent.counts(), agent.counts()
    assert agent.counts()["qa-fix-item"] == 1, agent.counts()
    assert BULLET not in _backlog(docs), _backlog(docs)
