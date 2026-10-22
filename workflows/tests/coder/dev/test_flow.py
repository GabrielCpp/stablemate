"""End-to-end tests for the `dev` flow: one dev turn, then the plan, gate and answer checks."""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

import pytest
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.dev.flow import Dev
from workhorse_workflows.coder.shared.owner import MAX_LAPS
from workhorse_workflows.coder.shared import commits, work
from workhorse_workflows.coder.shared.schemas.dev_story import DevOutcome
from workhorse_workflows.coder.shared.schemas.qa import StackStatus
from workhorse_workflows.kit.qa import runner as qa_runner
from workhorse_workflows.kit.qa.runner import copy_lease
from workhorse_workflows.kit.qa.schemas import QaPlanRun
from workhorse_workflows.kit.git import commit_all

EPIC = "EPIC-1"
STORY = "STORY-1"

INDEX = f"""# Epics

The epic queue, front first.

- [{EPIC}]({EPIC}/epic.md) — Epic One
"""

STORY_MD = """---
id: STORY-1
type: story
---

# Story STORY-1

## Dependencies

(none)

## Fixtures

(none)

## Context

Users need links that only point inside the site.

## Acceptance Criteria

- a relative link destination is rejected

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- the check lives in the api's link validator

## Implementation Status

- **Status**: Not started
"""

RED_MAKEFILE = "lint:\n\t@echo 'links.go:1: undefined: allowList'; exit 1\n"

TEST_NAME = "TestRejectsRelativeDestination"

BLOCK_NOTE = "nobody has said whether a protocol-relative link counts as relative"

OPERATOR_ANSWER = "A protocol-relative link counts as external, so reject it."

API_SERVICE: dict[str, Any] = {
    "repo": "api",
    "path": ".",
    "type": "go",
    "plan_file": "plan-api.md",
}

FINDINGS: list[dict[str, Any]] = [
    {
        "target": "api/links.go:3",
        "issue": "a destination starting with `//` passes as internal",
        "repair": "treat a protocol-relative destination as external",
        "category": "Bug",
        "score": 90,
    },
    {
        "target": "api/links.go:1",
        "issue": "the validator could reuse the url package's parser",
        "repair": "parse with net/url",
        "category": "Reuse",
        "score": 40,
    },
]


@pytest.fixture
def docs(
    repo: Path,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> Path:
    """The docs repo, carrying one epic with one story, committed so the tree starts clean."""
    write(
        repo / "docs" / "epics" / EPIC / "epic.md",
        f"---\ntitle: Epic One\nstatus: active\n---\n\n# Epic One\n\n## Stories\n\n"
        f"### {STORY}\n\n- title: Story {STORY}\n",
    )
    write(repo / "docs" / "epics" / EPIC / "stories" / STORY / "story.md", STORY_MD)
    write(repo / "docs" / "epics" / "index.md", INDEX)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Queue one epic")
    return repo


@pytest.fixture
def workspace(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    name_workspace: Callable[[dict[str, Path]], None],
) -> dict[str, Path]:
    """One real code repo and the named workspace that lists it, outside the docs tree."""
    root = tmp_path / "ws"
    api = root / "api"
    api.mkdir(parents=True)
    git(api, "init", "-q", "-b", "main")
    write(api / "README.md", "# api\n")
    git(api, "add", "-A")
    git(api, "commit", "-qm", "Initial commit")
    name_workspace({"api": api})
    return {"api": api}


class _Agent:
    """The dev turn and the resolver, scripted on the flow's arms."""

    def __init__(
        self,
        workspace: dict[str, Path],
        *,
        blocked: int = 0,
        red: int = 0,
        unanswered: int = 0,
        stray: int = 0,
        also_fixed: tuple[str, ...] = (),
        follow_ups: tuple[dict[str, str], ...] = (),
        escapes_to: str = "",
        same_as: str = "",
        outside: dict[str, str] | None = None,
        walk: tuple[int, ...] = (1,),
        failed: tuple[str, ...] = (),
    ) -> None:
        self.workspace = workspace
        self.same_as = same_as
        self.outside = dict(outside or {})
        self.failed = failed
        self.walk = walk
        self.follow_ups = follow_ups
        self.escapes_to = escapes_to
        self.also_fixed = also_fixed
        self.blocked = blocked
        self.red = red
        self.unanswered = unanswered
        self.stray = stray
        self.prefix = ""
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def _dev_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Build, commit, write the plan and the answers, and report the review's findings once."""
        if nth <= self.blocked:
            return {"status": "blocked", "notes": BLOCK_NOTE}
        spec = Path(str(data["spec_dir"]))
        spec.mkdir(parents=True, exist_ok=True)
        entries = "".join(f"\n### AC {n}: criterion {n}\n\n- **Met by**: api/links.go:3\n" for n in self.walk)
        (spec / "plan.md").write_text(
            f"# Plan\n\nReject relative links in the api.\n\n## Acceptance Walk\n{entries}",
            encoding="utf-8",
        )
        if self.failed:
            log = spec / "qa" / "qa-run.ndjson"
            log.parent.mkdir(parents=True, exist_ok=True)
            rows: list[dict[str, Any]] = [{"kind": "session_start", "run_id": "qa-run-1"}]
            rows += [{"kind": "assert", "scenario": sid, "action": 1, "result": "FAIL"} for sid in self.failed]
            rows += [{"kind": "assert", "scenario": "scenario-ok", "action": 1, "result": "PASS"}]
            log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        (spec / "plan-api.md").write_text("# Plan: api\n\nValidate in links.go.\n", encoding="utf-8")
        repo = self.workspace["api"]
        (repo / "links.go").write_text(f"package links\n\n// pass {nth}\n", encoding="utf-8")
        (repo / "links_test.go").write_text(
            f"package links\n\nfunc {TEST_NAME}(t *testing.T) {{}}\n", encoding="utf-8"
        )
        makefile = repo / "Makefile"
        if nth <= self.red:
            makefile.write_text(RED_MAKEFILE, encoding="utf-8")
        elif makefile.exists():
            makefile.unlink()
        message = commits.message(
            "feat",
            commits.scope(repo.name),
            "reject relative link destinations",
            epic=str(data["epic"]),
            story=str(data["story_id"]),
        )
        commit_all(repo, message)
        if nth <= self.stray:
            (repo / "scratch.go").write_text("package links\n", encoding="utf-8")
        first = not self.prefix
        if first:
            self.prefix = str(data["review_prefix"])
        if nth > self.unanswered:
            sha = _head(repo)
            Path(str(data["answers_file"])).write_text(
                f"## {self.prefix}1: fixed\n"
                f"- commit: {sha}\n"
                "- path: api/links.go\n"
                f"- test: {TEST_NAME}\n\n"
                f"## {self.prefix}2: declined\n"
                "Reason: the story's technical notes keep the validator free of new imports.\n"
                + "".join(
                    f"\n## {item}: fixed\n- commit: {sha}\n- path: api/links.go\n- test: {TEST_NAME}\n"
                    for item in self.also_fixed
                ),
                encoding="utf-8",
            )
        return {
            "status": "ready",
            "summary": "reject relative link destinations in the api",
            "notes": f"built and reviewed on pass {nth}",
            "services": [API_SERVICE],
            "findings": FINDINGS if first else [],
            "follow_ups": list(self.follow_ups) if first else [],
        }

    def _judge(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The judge's ruling: every escape subject to `escapes_to`, every cause subject to `same_as`, each scope subject its title names in `outside`, the rest at its default."""
        if data["kind"] == "scope":
            subjects: dict[str, str] = json.loads(str(data["subjects"]))
            return {"answers": {
                rid: kind for rid, text in subjects.items()
                for title, kind in self.outside.items() if text.startswith(f"{title}:")
            }}
        if data["kind"] == "escape" and self.escapes_to:
            return {"answers": dict.fromkeys(json.loads(str(data["subjects"])), self.escapes_to)}
        if data["kind"] == "cause" and self.same_as in json.loads(str(data["context"])):
            return {"answers": dict.fromkeys(json.loads(str(data["subjects"])), self.same_as)}
        return {"answers": {}}

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The resolver's say on a block, which this fake declines to give."""
        return {"decision": "escalated", "summary": "only the operator can decide this"}


def _answers(seen: list[str]) -> Callable[..., None]:
    """A stand-in for the human the `Await` is waiting on."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(f"STATUS: ANSWERED\n\n{OPERATOR_ANSWER}\n", encoding="utf-8")

    return answered


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _dev(docs: Path, operator_mode: str = "auto") -> Dev:
    return Dev(story=STORY, epic=EPIC, operator_mode=operator_mode)


def test_a_clean_pass_settles_the_fix_and_records_the_decline(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """One ready turn with a fixed and a declined answer finishes the run on its first check."""
    agent = _Agent(workspace)

    result = drive_flow(_dev(docs), env(), agent)

    assert isinstance(result, DevOutcome), result
    assert result.status == "ready", result
    assert result.settled == [f"{STORY}/review-1.1"], result
    assert result.declined == [f"{STORY}/review-1.2"], result
    assert agent.counts() == {"dev-story": 1}, agent.counts()
    assert git(docs, "status", "--porcelain").stdout == "", git(docs, "status", "--porcelain").stdout

    (first,) = agent.args_for("dev-story")
    assert str(first["review_prefix"]).endswith("/review-1."), first
    assert first["review_prefix"] == f"{STORY}/review-1.", first
    assert first["report"] == "", first
    assert first["operator_context"] == "", first


def test_a_red_gate_sends_its_output_back_and_a_green_turn_finishes(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The check's failure is the next turn's report, and the run ends once the gates pass."""
    agent = _Agent(workspace, red=1)

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert result.settled == [f"{STORY}/review-1.1"], result
    assert result.declined == [f"{STORY}/review-1.2"], result
    assert agent.counts() == {"dev-story": 2}, agent.counts()

    first, second = agent.args_for("dev-story")
    assert first["report"] == "", first
    report = str(second["report"])
    assert report.startswith("Gate: "), report
    assert "lint" in report, report
    assert "undefined: allowList" in report, report


def test_an_unanswered_finding_comes_back_named_in_the_report(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A finding with no section in the answer file stays open and buys another turn."""
    agent = _Agent(workspace, unanswered=1)

    result = drive_flow(_dev(docs), env(), agent)

    assert result.settled == [f"{STORY}/review-1.1"], result
    assert result.declined == [f"{STORY}/review-1.2"], result
    assert agent.counts() == {"dev-story": 2}, agent.counts()

    second = agent.args_for("dev-story")[1]
    report = str(second["report"])
    assert "Answers: 2 finding(s) are still open." in report, report
    assert f"`{STORY}/review-1.1`" in report, report
    assert f"`{STORY}/review-1.2`" in report, report
    assert f"{STORY}/review-1.1" in str(second["findings"]), second


def test_a_finding_qa_filed_in_the_parent_run_reaches_the_dev_turn(
    tmp_path: Path,
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """QA files its findings in the calling run's worklist, and the dev turn is shown them and settles them."""
    parent = tmp_path / "parent-run"
    qa = {
        "target": "web/app/routes/reports.tsx:516",
        "issue": "the empty state still shows the report tabs",
        "repair": "hide the tabs when no report is calculable",
        "category": "Bug",
        "score": 80,
    }
    work.file(work.worklist(parent), work.finding_items(STORY, "qa", 1, [qa]), by="qa")
    agent = _Agent(workspace, also_fixed=(f"{STORY}/qa-1.1",))
    dev = Dev(story=STORY, epic=EPIC, worklist_dir=str(parent))

    result = drive_flow(dev, env(), agent)

    (first,) = agent.args_for("dev-story")
    assert f"{STORY}/qa-1.1" in str(first["findings"]), first
    assert "the empty state still shows the report tabs" in str(first["findings"]), first
    assert first["worklist_path"] == str(work.worklist_path(parent)), first
    assert f"{STORY}/qa-1.1" in result.settled, result
    assert work.open_findings(work.worklist(parent), STORY) == [], work.worklist(parent).items()


def _filed_run(tmp_path: Path, docs: Path, titles: tuple[str, ...]) -> Path:
    """A run whose worklist holds the story, a finished sibling and the story's open follow-ups."""
    run = tmp_path / "parent-run"
    w = work.worklist(run)
    entries = [{"slug": slug, "epic": EPIC, "id": slug} for slug in ("STORY-0", STORY)]
    work.file(w, work.story_items(entries), by="launch")
    w.settle(["STORY-0"], work.DONE, work.STORY)
    story = work.find(w, STORY)
    assert story is not None
    for title in titles:
        work.file(w, work.follow_up_items(w, story, [{"title": title, "reason": "first"}]), by="dev")
    sibling = docs / "docs" / "epics" / EPIC / "stories" / "STORY-0"
    sibling.mkdir(parents=True)
    (sibling / "story.md").write_text(
        STORY_MD.replace("STORY-1", "STORY-0"), encoding="utf-8"
    )
    return run


def test_a_follow_up_the_story_already_holds_is_not_filed_again_and_a_new_one_names_its_escape(
    tmp_path: Path,
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Known titles file nothing under a new reason, and a new one is filed once, tagged with the story it escaped."""
    known = (
        "Hide tabs/download when calculation yields zero stages",
        "Guarantee unique report-panel names",
    )
    run = _filed_run(tmp_path, docs, known)
    agent = _Agent(
        workspace,
        follow_ups=(
            {"title": "Hide tabs and download when calculation yields zero stages", "reason": "again"},
            {"title": "Guarantee unique report panel names", "reason": "reworded"},
            {"title": "Paginate the audit log", "reason": "new"},
        ),
        escapes_to="STORY-0",
    )
    dev = Dev(story=STORY, epic=EPIC, worklist_dir=str(run))

    drive_flow(dev, env(), agent)

    filed = work.worklist(run).items(work.FOLLOW_UP)
    assert len(filed) == 3, [it.payload["title"] for it in filed]
    (fresh,) = [it for it in filed if it.payload["title"].startswith("Paginate")]
    assert fresh.payload["escaped_from"] == "STORY-0", fresh
    assert [it.id for it in work.escapes(work.worklist(run), "STORY-0")] == [fresh.id]


def test_a_follow_up_the_story_already_did_is_dropped_and_logged_as_done(
    tmp_path: Path,
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A follow-up that restates one the story already finished is not filed a second time."""
    run = _filed_run(tmp_path, docs, ("Guarantee unique report-panel names",))
    (done,) = work.worklist(run).items(work.FOLLOW_UP)
    work.worklist(run).settle([done.id], work.DONE, work.FOLLOW_UP)
    agent = _Agent(
        workspace,
        follow_ups=({"title": "Guarantee unique report panel names", "reason": "reworded"},),
    )
    dev = Dev(story=STORY, epic=EPIC, worklist_dir=str(run))

    with caplog.at_level("INFO"):
        drive_flow(dev, env(), agent)

    assert [it.id for it in work.worklist(run).items(work.FOLLOW_UP)] == [done.id]
    assert any(f"already done as {done.id}" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]


@pytest.mark.parametrize(
    ("entry", "kind"),
    [
        (
            {
                "title": "Declare verify: checks for #loaded and #banks-open states",
                "reason": "the book warnings on this page are pre-existing and unrelated to this change",
            },
            "pre-existing",
        ),
        (
            {"title": "Reconcile story.md Implementation Status", "reason": "the status table lags"},
            "bookkeeping",
        ),
    ],
)
def test_a_follow_up_that_is_no_product_work_is_not_filed(
    tmp_path: Path,
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    caplog: pytest.LogCaptureFixture,
    entry: dict[str, str],
    kind: str,
) -> None:
    """The judge reads the follow-up's own reason, and one it calls no product work never reaches the worklist."""
    run = _filed_run(tmp_path, docs, ())
    product = {"title": "Paginate the audit log", "reason": "it loads every row"}
    agent = _Agent(workspace, follow_ups=(entry, product), outside={entry["title"]: kind})
    dev = Dev(story=STORY, epic=EPIC, worklist_dir=str(run))

    with caplog.at_level("INFO"):
        drive_flow(dev, env(), agent)

    filed = work.worklist(run).items(work.FOLLOW_UP)
    assert [it.payload["title"] for it in filed] == [product["title"]]
    (scope,) = [a for a in agent.args_for("judge") if a["kind"] == "scope"]
    assert entry["reason"] in str(scope["subjects"])
    assert any(
        r.getMessage().startswith(f"[{kind}] ") and entry["title"] in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


FILED_BACKLOG = (
    "# Backlog\n\n## Filed by coder\n\n"
    "- [clear-report-snapshots] Sign-out leaves the saved report snapshots in the browser.\n"
)


def test_a_follow_up_that_restates_an_open_backlog_bullet_files_no_line(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """A follow-up the judge reads as an open bullet under a new title adds nothing to the backlog."""
    backlog = write(docs / "docs" / "backlog.md", FILED_BACKLOG)
    git(docs, "add", "docs/backlog.md")
    git(docs, "commit", "-qm", "seed the backlog")
    agent = _Agent(
        workspace,
        follow_ups=({"title": "Drop cached snapshots when the user logs out", "reason": "privacy"},),
        same_as="clear-report-snapshots",
    )

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert [a["kind"] for a in agent.args_for("judge")] == ["scope", "cause"], agent.counts()
    assert backlog.read_text(encoding="utf-8") == FILED_BACKLOG


def test_a_follow_up_no_open_bullet_holds_is_filed(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """A follow-up the judge reads as new lands under `Filed by coder` beside the open bullet."""
    backlog = write(docs / "docs" / "backlog.md", FILED_BACKLOG)
    git(docs, "add", "docs/backlog.md")
    git(docs, "commit", "-qm", "seed the backlog")
    agent = _Agent(
        workspace, follow_ups=({"title": "Paginate the audit log", "reason": "it loads every row"},)
    )

    drive_flow(_dev(docs), env(), agent)

    assert "Paginate the audit log: it loads every row" in backlog.read_text(encoding="utf-8")


def test_a_blocked_turn_in_human_mode_parks_and_resumes_with_the_answer(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A human operator is asked directly, and the answer reaches the next dev turn."""
    agent = _Agent(workspace, blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(_dev(docs, operator_mode="human"), env(), agent)

    assert result.status == "ready", result
    (gate,) = seen
    assert BLOCK_NOTE in gate, gate
    assert agent.counts() == {"dev-story": 2}, agent.counts()

    first, second = agent.args_for("dev-story")
    assert first["operator_context"] == "", first
    assert OPERATOR_ANSWER in str(second["operator_context"]), second


def test_checks_that_stay_red_past_the_lap_budget_park_instead_of_failing(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A spent repair budget is a block: the resolver escalates, and the answer resumes the dev owner."""
    agent = _Agent(workspace, red=MAX_LAPS + 1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": MAX_LAPS + 2, "resolve-operator": 1}, agent.counts()

    (gate,) = seen
    assert f"The checks still fail after {MAX_LAPS} repair turn(s)." in gate, gate
    assert "undefined: allowList" in gate, gate

    turns = agent.args_for("dev-story")
    assert all(t["report"] for t in turns[1 : MAX_LAPS + 1]), turns
    assert OPERATOR_ANSWER in str(turns[-1]["operator_context"]), turns[-1]


def test_work_the_turn_left_uncommitted_comes_back_named_in_the_report(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A path the story wrote and did not commit fails the check, so the owner records it."""
    agent = _Agent(workspace, stray=1)

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 2}, agent.counts()
    report = str(agent.args_for("dev-story")[1]["report"])
    assert "Uncommitted work" in report, report
    assert "scratch.go" in report, report
    assert subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace["api"], check=True, capture_output=True, text=True,
    ).stdout == ""


def test_a_path_dirty_before_the_story_began_is_not_the_story_s_to_commit(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`preexisting` is subtracted, so the operator's own edit costs the owner no turn."""
    mine = workspace["api"] / "notes.go"
    mine.write_text("package links\n", encoding="utf-8")
    entry = f"notes.go\0{hashlib.sha256(mine.read_bytes()).hexdigest()}"
    agent = _Agent(workspace)
    dev = _dev(docs).model_copy(update={"preexisting": (entry,)})

    result = drive_flow(dev, env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 1}, agent.counts()
    assert mine.exists()


THREE_CRITERIA = STORY_MD.replace(
    "- a relative link destination is rejected\n",
    "- a relative link destination is rejected\n  and the form says why\n"
    "- a protocol-relative link is rejected\n- an absolute link on the site's host is kept\n",
)


def _three_criteria(docs: Path, git: Callable[..., subprocess.CompletedProcess]) -> None:
    story = docs / "docs" / "epics" / EPIC / "stories" / STORY / "story.md"
    story.write_text(THREE_CRITERIA, encoding="utf-8")
    git(docs, "add", "-A")
    git(docs, "commit", "-qm", "Three criteria")


def test_a_plan_that_skips_a_criterion_goes_back_naming_it(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """The walk check names the criterion the plan left out, and the next turn's full walk finishes."""
    _three_criteria(docs, git)

    class Walks(_Agent):
        def _dev_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            self.walk = (1, 3) if nth == 1 else (1, 2, 3)
            return super()._dev_story(data, nth)

    agent = Walks(workspace)

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 2}, agent.counts()
    report = str(agent.args_for("dev-story")[1]["report"])
    assert "AC 2" in report, report
    assert "AC 1" not in report and "AC 3" not in report, report
    assert "Acceptance Walk" in report, report


def test_a_full_walk_proceeds(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """A plan that walks all three criteria costs no repair turn."""
    _three_criteria(docs, git)
    agent = _Agent(workspace, walk=(1, 2, 3))

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 1}, agent.counts()


def test_a_follow_up_turn_needs_no_walk(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """A follow-up item skips the walk check, whatever the plan holds."""
    _three_criteria(docs, git)
    agent = _Agent(workspace, walk=())
    dev = Dev(story=STORY, epic=EPIC, follow_up_title="Tidy the validator")

    result = drive_flow(dev, env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 1}, agent.counts()


class _Stack:
    """The stack nodes, scripted: what the scoped rerun returns, and every call the flow made."""

    def __init__(
        self,
        status: Literal["passed", "failed", "invalid"] = "passed",
        ready: Literal["yes", "no", "none", "unneeded"] = "yes",
        failed: tuple[str, ...] = (),
        red: int = 0,
    ) -> None:
        self.status: Literal["passed", "failed", "invalid"] = status
        self.red = red
        self.ready: Literal["yes", "no", "none", "unneeded"] = ready
        self.failed = failed
        self.calls: list[str] = []
        self.leases: list[str] = []
        self.only: list[str] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(qa_runner, "story_near", lambda _graph, _story: "book")
        monkeypatch.setattr(qa_runner, "stack_env", self.env)
        monkeypatch.setattr(qa_runner, "ensure_stack", self.ensure)
        monkeypatch.setattr(qa_runner, "run_qa_plan", self.run)
        monkeypatch.setattr(qa_runner, "release_copy", self.release)

    def env(self, _log: Any, _graph: Any, near: str = "", lease: str = "") -> dict[str, str]:
        self.calls.append("stack_target")
        self.leases.append(lease)
        return {}

    def ensure(self, _log: Any, **_k: Any) -> StackStatus:
        self.calls.append("ensure_stack")
        return StackStatus(ready=self.ready)

    def run(self, _log: Any, only: list[str] | None = None, **_k: Any) -> QaPlanRun:
        self.calls.append("run_qa_plan")
        self.only = list(only or [])
        reruns = self.calls.count("run_qa_plan")
        status: Literal["passed", "failed", "invalid"] = "failed" if reruns <= self.red else self.status
        scenarios = {sid: {"status": "failed"} for sid in self.failed} if status == "failed" else {}
        return QaPlanRun(status=status, ostler={"scenarios": scenarios})

    def release(self, _log: Any, **_k: Any) -> None:
        self.calls.append("release_copy")
        return None


def test_no_failed_record_touches_no_stack(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A story QA never failed finishes without a stack node running."""
    stack = _Stack()
    stack.install(monkeypatch)

    result = drive_flow(_dev(docs), env(), _Agent(workspace))

    assert result.status == "ready", result
    assert stack.calls == [], stack.calls


def test_failed_scenarios_that_now_pass_finish(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scoped rerun runs only the failed ids, and a pass lets the item leave dev."""
    stack = _Stack()
    stack.install(monkeypatch)
    agent = _Agent(workspace, failed=("scenario-b", "scenario-a"))

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 1}, agent.counts()
    assert stack.only == ["scenario-a", "scenario-b"], stack.only
    assert stack.calls == ["stack_target", "ensure_stack", "run_qa_plan", "release_copy"], stack.calls


def test_a_scenario_that_still_fails_goes_back_to_build(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A red rerun is the next turn's report, names the ids, and spends one repair lap."""
    stack = _Stack(failed=("scenario-a",), red=1)
    stack.install(monkeypatch)
    agent = _Agent(workspace, failed=("scenario-a",))

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 2}, agent.counts()
    first, second = agent.args_for("dev-story")
    assert first["report"] == "", first
    assert "scenario-a" in str(second["report"]), second
    assert stack.calls.count("release_copy") == stack.calls.count("run_qa_plan") == 2, stack.calls


def test_a_scoped_run_that_does_not_finish_lets_the_item_leave(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unfinished or unreachable rerun is QA's to own, and the copy is still released."""
    stack = _Stack(status="invalid")
    stack.install(monkeypatch)
    agent = _Agent(workspace, failed=("scenario-a",))

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 1}, agent.counts()
    assert stack.calls[-1] == "release_copy", stack.calls


def test_a_stack_that_will_not_come_up_is_skipped_and_released(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No stack means no rerun and no repair turn, and the lease is still released."""
    stack = _Stack(ready="no")
    stack.install(monkeypatch)
    agent = _Agent(workspace, failed=("scenario-a",))

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert stack.calls == ["stack_target", "ensure_stack", "release_copy"], stack.calls


def test_the_dev_lease_is_not_the_qa_lease(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dev's copy of the stack carries its own name, so it never collides with QA's."""
    stack = _Stack()
    stack.install(monkeypatch)
    run_env = env()

    drive_flow(_dev(docs), run_env, _Agent(workspace, failed=("scenario-a",)))

    (lease,) = stack.leases
    assert lease != copy_lease(STORY, "t"), lease
    assert lease.endswith("-dev"), lease


def test_a_second_failing_self_check_hands_the_item_to_qa(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The self-check bounces dev once, and a still-red rerun then finishes the item and says QA owns it."""
    stack = _Stack(failed=("scenario-a",), red=5)
    stack.install(monkeypatch)
    agent = _Agent(workspace, failed=("scenario-a",))

    with caplog.at_level("INFO"):
        result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 2}, agent.counts()
    assert stack.calls.count("run_qa_plan") == 2, stack.calls
    assert stack.calls.count("release_copy") == 2, stack.calls
    assert "scenario-a" in str(agent.args_for("dev-story")[1]["report"])
    assert any(
        "self-check: 1 scenario(s) still fail after one bounce, QA owns them now: scenario-a"
        in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]
