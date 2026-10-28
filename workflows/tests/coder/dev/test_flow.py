"""End-to-end tests for the `dev` flow: its plan, build and review turns, then the plan, gate and answer checks."""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
import itertools
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

import pytest
from ostler import Ostler
from workhorse._vendor.stablemate_core import config as core_config
from _fakes import StubRunner
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.runner.backends.delegates import Delegate
from workhorse.runner.backends.null import NullBackend

from workhorse_workflows.coder.dev.flow import Dev
from workhorse_workflows.coder.shared.owner import MAX_LAPS
from workhorse_workflows.coder.shared import commits, work
from workhorse_workflows.coder.shared.review import ANSWERS_FILE
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
services: [api, web]
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
        follow_ups: tuple[dict[str, Any], ...] = (),
        outside: dict[str, str] | None = None,
        walk: tuple[int, ...] = (1,),
        failed: tuple[str, ...] = (),
        repo: str = "api",
        blocked_in: str = "review",
        departures: tuple[str, ...] = (),
        advise_from: int = 1,
        consult_from: int = 1,
        session: Callable[[int], str] | None = None,
    ) -> None:
        self.blocked_in = blocked_in
        self.departures = departures
        self.advise_from = advise_from
        self.consult_from = consult_from
        self.session = session
        self.workspace = workspace
        self.repo = repo
        self.outside = dict(outside or {})
        self.failed = failed
        self.walk = walk
        self.follow_ups = follow_ups
        self.also_fixed = also_fixed
        self.blocked = blocked
        self.red = red
        self.unanswered = unanswered
        self.stray = stray
        self.prefix = ""
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.powers: list[tuple[str, str | None]] = []
        self.rebriefs: list[Callable[[], str] | None] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        self.powers.append((stem, node.power))
        self.rebriefs.append(kwargs.get("rebrief"))
        if self.session is not None and len(args) > 1:
            chain = Path(args[1])
            chain.parent.mkdir(parents=True, exist_ok=True)
            chain.write_text(self.session(len(self.calls)), encoding="utf-8")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def rebriefs_for(self, stem: str) -> list[Callable[[], str] | None]:
        return [r for s, r in zip(self.calls, self.rebriefs, strict=True) if s == stem]

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def _dev_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The plan phase: ready, or blocked while `blocked` counts it down."""
        if self.blocked_in == "plan" and nth <= self.blocked:
            return {"status": "blocked", "notes": BLOCK_NOTE}
        return {"status": "ready", "notes": "planned"}

    def _dev_build(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The build phase: ready with its departures, advised from the `advise_from`th turn on."""
        if self.blocked_in == "build" and nth <= self.blocked:
            return {"status": "blocked", "notes": BLOCK_NOTE}
        advice = "keep it" if nth >= self.advise_from else ""
        return {
            "status": "ready",
            "notes": "built",
            "departures": [
                {"change": change, "reason": "the plan fails a gate", "advice": advice}
                for change in self.departures
            ],
        }

    def _dev_follow_up(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """A later turn of a phase: what the phase's own turn would answer."""
        phase = str(data["phase"])
        handler = getattr(self, f"_dev_{phase}")
        spec = Path(str(data["spec_dir"]))
        carried = {**data, "answers_file": str(spec / ANSWERS_FILE), "review_prefix": self.prefix}
        return handler(carried, self.counts()[f"dev-{phase}"] + nth)

    def _dev_review(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Build, commit, write the plan and the answers, and report the review's findings once."""
        if self.blocked_in == "review" and nth <= self.blocked:
            return {"status": "blocked", "notes": BLOCK_NOTE}
        spec = Path(str(data["spec_dir"]))
        spec.mkdir(parents=True, exist_ok=True)
        entries = "".join(f"\n### AC {n}: criterion {n}\n\n- **Met by**: {self.repo}/links.go:3\n" for n in self.walk)
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
        (spec / f"plan-{self.repo}.md").write_text(
            f"# Plan: {self.repo}\n\nValidate in links.go.\n", encoding="utf-8"
        )
        repo = self.workspace[self.repo]
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
                f"- path: {self.repo}/links.go\n"
                f"- test: {TEST_NAME}\n\n"
                f"## {self.prefix}2: declined\n"
                "Reason: coincidence: the story's technical notes keep the validator free of new imports; the url package parses another grammar.\n"
                + "".join(
                    f"\n## {item}: fixed\n- commit: {sha}\n- path: {self.repo}/links.go\n- test: {TEST_NAME}\n"
                    for item in self.also_fixed
                ),
                encoding="utf-8",
            )
        return {
            "status": "ready",
            "summary": "reject relative link destinations in the api",
            "notes": f"built and reviewed on pass {nth}",
            "services": [{**API_SERVICE, "repo": self.repo, "plan_file": f"plan-{self.repo}.md"}],
            "findings": [{**f, "target": f["target"].replace("api/", f"{self.repo}/", 1)} for f in FINDINGS] if first else [],
            "follow_ups": list(self.follow_ups) if first else [],
            "consults": [
                {"finding": f"{self.prefix}2", "question": "is the decline right?", "advice": "yes"}
            ]
            if nth >= self.consult_from
            else [],
        }

    def _judge(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The judge's ruling: each scope subject its title names in `outside`, the rest at its default."""
        if data["kind"] == "scope":
            subjects: dict[str, str] = json.loads(str(data["subjects"]))
            return {"answers": {
                rid: kind for rid, text in subjects.items()
                for title, kind in self.outside.items() if text.startswith(f"{title}:")
            }}
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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 1}, agent.counts()
    assert git(docs, "status", "--porcelain").stdout == "", git(docs, "status", "--porcelain").stdout

    (first,) = agent.args_for("dev-review")
    assert str(first["review_prefix"]).endswith("/review-1."), first
    assert first["review_prefix"] == f"{STORY}/review-1.", first
    assert first["report"] == "", first
    assert first["operator_context"] == "", first
    assert first["story_services"] == ["api", "web"], first


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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 2}, agent.counts()

    first, second = agent.args_for("dev-review")
    assert first["report"] == "", first
    report = str(second["report"])
    assert report.startswith("Gate: "), report
    assert "lint" in report, report
    assert "undefined: allowList" in report, report


def test_a_copy_the_story_added_comes_back_as_a_copies_failure_before_any_service_gate(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    copies: Any,
) -> None:
    """The lap names the copy to the review turn, and the service gates wait for the lap that has none."""
    agent = _Agent(workspace, red=2)
    copies.finds("api/links.go:1-9", str(workspace["api"]))

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    two = agent.args_for("dev-review")[1]
    report = str(two["report"])
    assert "copies" in report, report
    assert "api/links.go:1-9" in report, report
    assert "undefined: allowList" not in report, report
    assert "undefined: allowList" in str(agent.args_for("dev-review")[2]["report"])


def test_the_clone_check_is_not_consulted_when_the_story_status_check_fails(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    copies: Any,
) -> None:
    """A story stamped finished is the first failure, so the clone check has not run in that lap."""
    story = docs / "docs" / "epics" / EPIC / "stories" / STORY / "story.md"

    class Stamping(_Agent):
        def _dev_review(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            story.write_text(
                STORY_MD.replace("Not started", "Done") if nth == 1 else STORY_MD,
                encoding="utf-8",
            )
            return super()._dev_review(data, nth)

    agent = Stamping(workspace)

    drive_flow(_dev(docs), env(), agent)

    first_report = str(agent.args_for("dev-review")[1]["report"])
    assert "Status" in first_report, first_report
    assert len(copies.calls) == len(agent.args_for("dev-review")) - 1, copies.calls


def test_the_clone_check_receives_the_dispatch_repos_and_the_story_identity(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    copies: Any,
) -> None:
    """The docs entry never reaches the check, and the story's id and slug do."""
    agent = _Agent(workspace)

    drive_flow(_dev(docs), env(), agent)

    (call,) = copies.calls
    assert call["roots"] == [str(workspace["api"])], call
    assert call["story_id"] == STORY, call
    assert call["story_slug"], call


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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 2}, agent.counts()

    second = agent.args_for("dev-review")[1]
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
    """QA files its findings in the calling run's worklist, and the rework turn is shown them and settles them."""
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

    counts = agent.counts()
    assert (counts["dev-plan"], counts["dev-build"], counts["dev-review"]) == (0, 0, 1), counts
    (first,) = agent.args_for("dev-review")
    assert f"{STORY}/qa-1.1" in str(first["qa_findings"]), first
    assert "the empty state still shows the report tabs" in str(first["qa_findings"]), first
    assert first["findings"] == "", first
    assert first["worklist_path"] == str(work.worklist_path(parent)), first
    assert f"{STORY}/qa-1.1" in result.settled, result
    assert work.open_findings(work.worklist(parent), STORY) == [], work.worklist(parent).items()


def _run_with_story(tmp_path: Path) -> Path:
    """A run whose worklist holds the story alone."""
    run = tmp_path / "parent-run"
    work.file(work.worklist(run), work.story_items([{"slug": STORY, "epic": EPIC, "id": STORY}]), by="launch")
    return run


def _follow_up(title: str, reason: str, **over: Any) -> dict[str, Any]:
    """A follow-up as the dev turn reports it, with the area and pattern the register keys on."""
    return {"title": title, "reason": reason, "area": "audit", "pattern": "paginate-list", **over}


def _register(docs: Path) -> list[str]:
    """The register's listing lines, read the way `ostler backlog list` prints them."""
    return Ostler(docs).record_listing()


def test_a_story_turn_s_follow_up_goes_to_the_register_not_the_worklist(
    tmp_path: Path,
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A follow-up the story turn reports lands as a record and adds no follow-up item to the run."""
    run = _run_with_story(tmp_path)
    agent = _Agent(workspace, follow_ups=(_follow_up("Paginate the audit log", "it loads every row"),))

    drive_flow(Dev(story=STORY, epic=EPIC, worklist_dir=str(run)), env(), agent)

    (record,) = Ostler(docs).records().records
    assert (record.summary, record.body, record.repo, record.area) == (
        "Paginate the audit log", "it loads every row", "api", "audit"
    )
    assert record.filed_by == "coder" and record.source_story == STORY
    assert not (docs / "docs" / "backlog.md").exists()
    assert work.worklist(run).items(work.FOLLOW_UP) == []


@pytest.mark.parametrize(
    ("entry", "kind"),
    [
        (
            _follow_up(
                "Declare verify: checks for #loaded and #banks-open states",
                "the book warnings on this page are pre-existing and unrelated to this change",
            ),
            "pre-existing",
        ),
        (
            _follow_up("Reconcile story.md Implementation Status", "the status table lags"),
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
    entry: dict[str, Any],
    kind: str,
) -> None:
    """The judge reads the follow-up's own reason, and one it calls no product work never reaches the register."""
    run = _run_with_story(tmp_path)
    product = _follow_up("Paginate the audit log", "it loads every row")
    agent = _Agent(workspace, follow_ups=(entry, product), outside={entry["title"]: kind})
    dev = Dev(story=STORY, epic=EPIC, worklist_dir=str(run))

    with caplog.at_level("INFO"):
        drive_flow(dev, env(), agent)

    assert [r.summary for r in Ostler(docs).records().records] == [product["title"]]
    assert work.worklist(run).items(work.FOLLOW_UP) == []
    (scope,) = [a for a in agent.args_for("judge") if a["kind"] == "scope"]
    assert entry["reason"] in str(scope["subjects"])
    assert any(
        r.getMessage().startswith(f"[{kind}] ") and entry["title"] in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


def _file_open(docs: Path, summary: str, record_id: str, filed_by: Literal["coder", "qa"] = "coder") -> None:
    filing = Ostler(docs).file_record(
        repo="api", area="audit", pattern="clear-cache", summary=summary, filed_by=filed_by,
        record_id=record_id,
    )
    assert filing.ok, filing


SNAPSHOTS = "Sign-out leaves the saved report snapshots in the browser."


def test_a_follow_up_that_cites_an_open_record_files_no_record(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A follow-up whose reason cites an open record by id adds nothing to the register."""
    _file_open(docs, SNAPSHOTS, "clear-report-snapshots")
    before = _register(docs)
    agent = _Agent(
        workspace,
        follow_ups=(_follow_up(
            "Drop cached snapshots when the user logs out", "see [clear-report-snapshots]"
        ),),
    )

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert [a["kind"] for a in agent.args_for("judge")] == ["scope"], agent.counts()
    assert _register(docs) == before


def test_a_follow_up_no_open_record_holds_is_filed_beside_the_qa_ones(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A new follow-up adds one coder record, and the open record QA filed keeps its line."""
    _file_open(docs, SNAPSHOTS, "clear-report-snapshots", filed_by="qa")
    agent = _Agent(workspace, follow_ups=(_follow_up("Paginate the audit log", "it loads every row"),))

    drive_flow(_dev(docs), env(), agent)

    by_origin = {r.filed_by: r.summary for r in Ostler(docs).records().records}
    assert by_origin == {"qa": SNAPSHOTS, "coder": "Paginate the audit log"}


@pytest.fixture
def two_repo_workspace(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    name_workspace: Callable[[dict[str, Path]], None],
) -> dict[str, Path]:
    """Two real code repos, `api-service` and `web-app`, named by the workspace."""
    repos = {name: tmp_path / "ws" / name for name in ("api-service", "web-app")}
    for name, path in repos.items():
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")
        write(path / "README.md", f"# {name}\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", "Initial commit")
    name_workspace(repos)
    return repos


def _commit_count(root: Path) -> int:
    done = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--count", "HEAD"], capture_output=True, text=True
    )
    return int(done.stdout) if done.returncode == 0 else 0


def test_two_follow_ups_of_a_workspace_run_land_as_records_in_one_artifacts_commit(
    docs: Path,
    two_repo_workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The register keys each follow-up by repository and area, commits once, and files a repeated title never again."""
    artifacts = core_config.ensure_artifacts_repo()
    subprocess.run(["git", "-C", str(artifacts), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    followed = (
        _follow_up("Paginate the audit log", "it loads every row", repo="api-service", symbols=["audit/log.go"]),
        _follow_up("Cache the rate card", "it is read on every call", repo="api-service", area="pricing", pattern="add-cache"),
    )
    code_heads = {name: _head(path) for name, path in two_repo_workspace.items()}

    drive_flow(_dev(docs), env(), _Agent(two_repo_workspace, follow_ups=followed, repo="api-service"))

    folders = sorted(p.parent.relative_to(artifacts / "backlog").parts[:2] for p in (artifacts / "backlog").glob("*/*/*/record.md"))
    assert folders == [("api-service", "audit"), ("api-service", "pricing")]
    assert _commit_count(artifacts) == 2
    assert subprocess.run(
        ["git", "-C", str(artifacts), "log", "-1", "--format=%s"], capture_output=True, text=True, check=True
    ).stdout.strip() == f"chore(api-service): file the deferred follow-ups of {STORY}"
    lines = _register(docs)
    assert len(lines) == 2
    assert all("api-service" in line for line in lines)
    assert any("audit" in line and "paginate-list" in line and "Paginate the audit log" in line for line in lines)
    assert any("pricing" in line and "add-cache" in line and "Cache the rate card" in line for line in lines)
    assert not (two_repo_workspace["web-app"] / "backlog").exists()
    assert _head(two_repo_workspace["web-app"]) == code_heads["web-app"]
    assert not list(two_repo_workspace["api-service"].rglob("record.md"))

    drive_flow(_dev(docs), env(name="coder-again"), _Agent(two_repo_workspace, follow_ups=followed, repo="api-service"))

    assert _register(docs) == lines
    assert len(list((artifacts / "backlog").glob("*/*/*/record.md"))) == 2
    assert _commit_count(artifacts) == 2


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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 2}, agent.counts()

    first, second = agent.args_for("dev-review")
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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": MAX_LAPS + 2, "resolve-operator": 1}, agent.counts()

    (gate,) = seen
    assert f"The checks still fail after {MAX_LAPS} repair turn(s)." in gate, gate
    assert "undefined: allowList" in gate, gate

    turns = agent.args_for("dev-review")
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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 2}, agent.counts()
    report = str(agent.args_for("dev-review")[1]["report"])
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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 1}, agent.counts()
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
        def _dev_review(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            self.walk = (1, 3) if nth == 1 else (1, 2, 3)
            return super()._dev_review(data, nth)

    agent = Walks(workspace)

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 2}, agent.counts()
    report = str(agent.args_for("dev-review")[1]["report"])
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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 1}, agent.counts()


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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 1}, agent.counts()


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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 1}, agent.counts()
    assert stack.only == ["scenario-a", "scenario-b"], stack.only
    assert stack.calls == ["stack_target", "ensure_stack", "run_qa_plan", "release_copy"], stack.calls


def test_a_scenario_that_still_fails_goes_back_to_review(
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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 2}, agent.counts()
    first, second = agent.args_for("dev-review")
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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 1}, agent.counts()
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
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 2}, agent.counts()
    assert stack.calls.count("run_qa_plan") == 2, stack.calls
    assert stack.calls.count("release_copy") == 2, stack.calls
    assert "scenario-a" in str(agent.args_for("dev-review")[1]["report"])
    assert any(
        "self-check: 1 scenario(s) still fail after one bounce, QA owns them now: scenario-a"
        in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


PHASE_TURNS = ("dev-plan", "dev-build", "dev-review")


class _SubagentBackend(NullBackend):
    supports_subagents = True


@pytest.fixture
def drive_advised(
    ambient: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Any]:
    """`drive_flow` on a CLI that takes subagents and a profile that names an advisor."""
    advisor = Delegate("advisor", "big", None, "second opinion", "answer one question", True)
    monkeypatch.setattr(
        "workhorse.pyflow.engine.resolve_delegates_for", lambda *a, **k: (advisor,)
    )

    def _drive(flow: Dev, run_env: RunEnv, agent: Any) -> Any:
        for field, value in ambient.items():
            if field in type(flow).model_fields and not getattr(flow, field):
                setattr(flow, field, value)
        runner = StubRunner(agent, backend=_SubagentBackend())
        return drive(flow, replace(run_env, agent_runner=runner), None)

    return _drive


def test_a_fresh_story_runs_plan_build_and_review_in_that_order(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(workspace)

    drive_flow(_dev(docs), env(), agent)

    assert [c for c in agent.calls if c in PHASE_TURNS] == list(PHASE_TURNS), agent.calls


def test_a_failed_check_reenters_review_and_not_build(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, red=1)

    drive_flow(_dev(docs), env(), agent)

    turns = [c for c in agent.calls if c in PHASE_TURNS]
    assert turns == ["dev-plan", "dev-build", "dev-review", "dev-review"], agent.calls


def test_an_operator_answer_on_a_build_block_returns_to_build(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, blocked=1, blocked_in="build")
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(_dev(docs, operator_mode="human"), env(), agent)

    assert result.status == "ready", result
    turns = [c for c in agent.calls if c in PHASE_TURNS]
    assert turns == ["dev-plan", "dev-build", "dev-build", "dev-review"], agent.calls
    first, second = agent.args_for("dev-build")
    assert first["operator_context"] == "", first
    assert OPERATOR_ANSWER in str(second["operator_context"]), second


def test_a_departure_without_advice_sends_the_build_back_when_an_advisor_is_offered(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_advised: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, departures=("swap the parser",), advise_from=2)

    result = drive_advised(_dev(docs), env(), agent)

    assert result.status == "ready", result
    turns = [c for c in agent.calls if c in PHASE_TURNS]
    assert turns == ["dev-plan", "dev-build", "dev-build", "dev-review"], agent.calls
    first, second = agent.args_for("dev-build")
    assert first["advisor"] is True, first
    assert first["report"] == "", first
    assert "swap the parser" in str(second["report"]), second
    assert [p for p in agent.powers if p[0] in PHASE_TURNS] == [
        ("dev-plan", "max"),
        ("dev-build", "high"),
        ("dev-build", "high"),
        ("dev-review", "high"),
    ], agent.powers


def test_without_an_advisor_a_departure_passes_and_every_phase_runs_at_max(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, departures=("swap the parser",), advise_from=9)

    drive_flow(_dev(docs), env(), agent)

    assert agent.counts()["dev-build"] == 1, agent.counts()
    assert [p for p in agent.powers if p[0] in PHASE_TURNS] == [
        ("dev-plan", "max"),
        ("dev-build", "max"),
        ("dev-review", "max"),
    ], agent.powers


def test_a_decline_with_no_consult_is_reopened_and_named_when_an_advisor_is_offered(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_advised: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, consult_from=2)

    result = drive_advised(_dev(docs), env(), agent)

    assert agent.counts()["dev-review"] == 2, agent.counts()
    report = str(agent.args_for("dev-review")[1]["report"])
    assert f"`{STORY}/review-1.2`" in report, report
    assert "advisor" in report, report
    assert result.declined == [f"{STORY}/review-1.2"], result


def test_a_decline_with_a_consult_on_file_stays_declined(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_advised: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, consult_from=1)

    result = drive_advised(_dev(docs), env(), agent)

    assert agent.counts()["dev-review"] == 1, agent.counts()
    assert result.declined == [f"{STORY}/review-1.2"], result


def test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, red=1, session=lambda n: "sess-1")
    run_env = env()

    drive_flow(_dev(docs), run_env, agent)

    turns = [c for c in agent.calls if c in (*PHASE_TURNS, "dev-follow-up")]
    assert turns == ["dev-plan", "dev-build", "dev-review", "dev-follow-up"], agent.calls
    (note,) = agent.args_for("dev-follow-up")
    assert note["phase"] == "review", note
    assert str(note["report"]).startswith("Gate: "), note
    assert Path(str(note["brief_path"])).is_file(), note
    review_brief = agent.args_for("dev-review")[0]["brief_path"]
    assert note["brief_path"] == review_brief, note


def test_a_conversation_other_than_the_briefed_one_opens_with_the_full_brief_again(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = itertools.count()
    monkeypatch.setattr(Dev, "chain_session", lambda self, key: f"conversation-{next(reads)}")
    agent = _Agent(workspace, red=1, session=lambda n: "sess-1")

    drive_flow(_dev(docs), env(), agent)

    turns = [c for c in agent.calls if c in (*PHASE_TURNS, "dev-follow-up")]
    assert turns == ["dev-plan", "dev-build", "dev-review", "dev-review"], agent.calls


def test_the_plan_turn_on_a_fresh_conversation_carries_the_full_rules(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, session=lambda n: "sess-1")

    drive_flow(_dev(docs), env(), agent)

    (plan,) = agent.args_for("dev-plan")
    assert plan["opening_brief"] == "", plan
    text = Path(str(plan["brief_path"])).read_text(encoding="utf-8")
    assert "## Story Status" in text, text
    assert "## Commit Identity" in text, text


def test_the_opening_brief_leaves_the_book_merge_to_the_docs_phase(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, session=lambda n: "sess-1")

    drive_flow(_dev(docs), env(), agent)

    (plan,) = agent.args_for("dev-plan")
    text = Path(str(plan["brief_path"])).read_text(encoding="utf-8")
    assert "## The book" in text, text
    assert "write, stamp and doctor nothing under `docs/services/`" in " ".join(text.split()), text


def test_the_build_turn_on_the_plans_conversation_points_at_the_opening_brief(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, session=lambda n: "sess-1")

    drive_flow(_dev(docs), env(), agent)

    (plan,) = agent.args_for("dev-plan")
    (build,) = agent.args_for("dev-build")
    opening = Path(str(plan["brief_path"]))
    assert opening.name == "plan.md", opening
    assert build["opening_brief"] == str(opening), build
    assert Path(str(build["brief_path"])).parent == opening.parent, build
    text = Path(str(build["brief_path"])).read_text(encoding="utf-8")
    assert "## Story Status" not in text, text
    assert "Scope" not in text, text
    assert str(opening) in text, text


def test_a_rebrief_renders_the_full_rules_and_rewrites_the_brief_on_disk(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(workspace, session=lambda n: "sess-1")

    drive_flow(_dev(docs), env(), agent)

    (build,) = agent.args_for("dev-build")
    (rebrief,) = agent.rebriefs_for("dev-build")
    assert rebrief is not None
    brief = Path(str(build["brief_path"]))
    assert "## Story Status" not in brief.read_text(encoding="utf-8")

    text = rebrief()

    assert "## Story Status" in text, text
    assert brief.read_text(encoding="utf-8") == text


def test_the_first_review_turn_writes_the_reviewer_files_beside_its_brief(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(workspace)

    drive_flow(_dev(docs), env(), agent)

    (review,) = agent.args_for("dev-review")
    folder = Path(str(review["brief_path"])).parent
    reviewer = folder / "dev-reviewer.md"
    answer = folder / "dev-answer-file.md"
    assert reviewer.is_file(), sorted(folder.iterdir())
    assert answer.is_file(), sorted(folder.iterdir())
    assert review["reviewer_brief"] == str(reviewer), review
    assert review["answer_format"] == str(answer), review
    text = Path(str(review["brief_path"])).read_text(encoding="utf-8")
    assert str(reviewer) in text, text
    assert str(answer) in text, text
