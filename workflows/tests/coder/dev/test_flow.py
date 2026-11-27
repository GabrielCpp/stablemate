"""End-to-end tests for the `dev` flow: its plan, build and review turns, then the plan, gate and answer checks."""
from __future__ import annotations

import functools
import hashlib
import shutil
import subprocess
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
from workhorse.pyflow.blueprint import NODE_ATTR, node_spec
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.runner.backends.delegates import Delegate
from workhorse.runner.backends.null import NullBackend

from workhorse_workflows.coder.dev import flow as dev_flow
from workhorse_workflows.coder.dev.flow import Dev
from coder.dev.story import EPIC, STORY, STORY_MD, make_dev
from workhorse_workflows.coder.shared.owner import CUT_CONTINUE_NOTE, MAX_LAPS
from workhorse_workflows.coder.shared import work
from workhorse_workflows.coder.shared.schemas.dev import DispatchEntry
from workhorse_workflows.coder.shared.schemas.dev_story import DevOutcome
from _epics import epics_root
from coder.dev.fake_agent import BLOCK_NOTE, OPERATOR_ANSWER, FakeAgent, git_head

def _answers(seen: list[str]) -> Callable[..., None]:
    """A stand-in for the human the `Await` is waiting on."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(f"STATUS: ANSWERED\n\n{OPERATOR_ANSWER}\n", encoding="utf-8")

    return answered



def test_a_clean_pass_settles_the_fix_and_records_the_decline(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """One ready turn with a fixed and a declined answer finishes the run on its first check."""
    agent = FakeAgent(workspace)

    result = drive_flow(make_dev(docs), env(), agent)

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


def test_the_check_hands_the_plan_its_storys_declared_services(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Dev.check` records the plan with the services the story's front matter declares."""
    seen: list[Any] = []
    real = dev_flow.record_plan

    @functools.wraps(real)
    def spy(logger: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs.get("story_services"))
        return real(logger, *args, **kwargs)

    setattr(spy, NODE_ATTR, replace(node_spec(real), fn=spy))
    monkeypatch.setattr(dev_flow, "record_plan", spy)

    drive_flow(make_dev(docs), env(), FakeAgent(workspace))

    assert seen and all(item == ["api", "web"] for item in seen), seen


def test_a_red_gate_sends_its_output_back_and_a_green_turn_finishes(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The check's failure is the next turn's report, and the run ends once the gates pass."""
    agent = FakeAgent(workspace, red=1)

    result = drive_flow(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace, red=2)
    copies.finds("api/links.go:1-9", str(workspace["api"]))

    result = drive_flow(make_dev(docs), env(), agent)

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
    story = epics_root() / EPIC / "stories" / STORY / "story.md"

    class Stamping(FakeAgent):
        def _dev_review(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            story.write_text(
                STORY_MD.replace("Not started", "Done") if nth == 1 else STORY_MD,
                encoding="utf-8",
            )
            return super()._dev_review(data, nth)

    agent = Stamping(workspace)

    drive_flow(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace)

    drive_flow(make_dev(docs), env(), agent)

    (call,) = copies.calls
    assert call["roots"] == [str(workspace["api"])], call
    assert call["story_id"] == STORY, call
    assert call["story_slug"], call


def test_the_lap_gates_a_service_the_check_set_adds_after_the_plan_services(
    tmp_path: Path,
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    check_set: Any,
) -> None:
    """A dependent's dirty gate is the lap's failure, and the lap that finds it clean passes."""
    dependent = tmp_path / "dependent"
    dependent.mkdir()
    makefile = dependent / "Makefile"
    makefile.write_text("lint:\n\t@echo 'dependent gate is red'; exit 1\n", encoding="utf-8")
    check_set.adds(
        DispatchEntry(service="dependent", repo="api", cwd=str(dependent), type="go", label="go")
    )

    class Repairing(FakeAgent):
        def _dev_review(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            if nth > 1:
                makefile.unlink(missing_ok=True)
            return super()._dev_review(data, nth)

    agent = Repairing(workspace)

    result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    first, second = agent.args_for("dev-review")
    assert first["report"] == "", first
    assert "dependent gate is red" in str(second["report"]), second["report"]


def test_the_check_set_receives_the_dispatch_and_the_story_identity(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    check_set: Any,
) -> None:
    """The check set sees the plan's dispatch, docs entry included, and the story's id and slug."""
    agent = FakeAgent(workspace)

    drive_flow(make_dev(docs), env(), agent)

    (call,) = check_set.calls
    assert [e.cwd for e in call["dispatch"] if e.type != "docs"] == [str(workspace["api"])], call
    assert call["story_id"] == STORY, call
    assert call["story_slug"], call


def test_the_check_set_is_not_consulted_when_the_clone_check_finds_a_copy(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    copies: Any,
    check_set: Any,
) -> None:
    """The lap that fails on a copy stops before the check set; the lap after it consults it."""
    agent = FakeAgent(workspace)
    copies.finds("api/links.go:1-9", str(workspace["api"]))

    drive_flow(make_dev(docs), env(), agent)

    assert len(copies.calls) == 2, copies.calls
    assert len(check_set.calls) == 1, check_set.calls


def test_an_unanswered_finding_comes_back_named_in_the_report(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A finding with no section in the answer file stays open and buys another turn."""
    agent = FakeAgent(workspace, unanswered=1)

    result = drive_flow(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace, also_fixed=(f"{STORY}/qa-1.1",))
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
    agent = FakeAgent(workspace, follow_ups=(_follow_up("Paginate the audit log", "it loads every row"),))

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
    agent = FakeAgent(workspace, follow_ups=(entry, product), outside={entry["title"]: kind})
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


def test_a_follow_up_the_judge_reads_as_pre_existing_is_filed_with_that_pattern(
    tmp_path: Path,
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A defect the story did not cause still reaches the register, marked as pre-existing."""
    run = _run_with_story(tmp_path)
    entry = _follow_up(
        "Fix the MySQL error on the audit query",
        "the review hit it and it predates this story",
    )
    agent = FakeAgent(workspace, follow_ups=(entry,), outside={entry["title"]: "pre-existing"})

    drive_flow(Dev(story=STORY, epic=EPIC, worklist_dir=str(run)), env(), agent)

    (record,) = Ostler(docs).records().records
    assert (record.summary, record.pattern) == (entry["title"], "pre-existing")


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
    agent = FakeAgent(
        workspace,
        follow_ups=(_follow_up(
            "Drop cached snapshots when the user logs out", "see [clear-report-snapshots]"
        ),),
    )

    result = drive_flow(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace, follow_ups=(_follow_up("Paginate the audit log", "it loads every row"),))

    drive_flow(make_dev(docs), env(), agent)

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


def test_two_follow_ups_of_a_workspace_run_land_as_records_on_the_untracked_shelf(
    docs: Path,
    two_repo_workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The register keys each follow-up by repository and area, commits nothing, and files a repeated title never again."""
    artifacts = core_config.ensure_artifacts_repo()
    followed = (
        _follow_up("Paginate the audit log", "it loads every row", repo="api-service", symbols=["audit/log.go"]),
        _follow_up("Cache the rate card", "it is read on every call", repo="api-service", area="pricing", pattern="add-cache"),
    )
    code_heads = {name: git_head(path) for name, path in two_repo_workspace.items()}

    drive_flow(make_dev(docs), env(), FakeAgent(two_repo_workspace, follow_ups=followed, repo="api-service"))

    folders = sorted(p.parent.relative_to(artifacts / "backlogs").parts[:2] for p in (artifacts / "backlogs").glob("*/*/*/record.md"))
    assert folders == [("api-service", "audit"), ("api-service", "pricing")]
    assert _commit_count(artifacts) == 1
    lines = _register(docs)
    assert len(lines) == 2
    assert all("api-service" in line for line in lines)
    assert any("audit" in line and "paginate-list" in line and "Paginate the audit log" in line for line in lines)
    assert any("pricing" in line and "add-cache" in line and "Cache the rate card" in line for line in lines)
    assert not (two_repo_workspace["web-app"] / "backlog").exists()
    assert git_head(two_repo_workspace["web-app"]) == code_heads["web-app"]
    assert not list(two_repo_workspace["api-service"].rglob("record.md"))

    drive_flow(make_dev(docs), env(name="coder-again"), FakeAgent(two_repo_workspace, follow_ups=followed, repo="api-service"))

    assert _register(docs) == lines
    assert len(list((artifacts / "backlogs").glob("*/*/*/record.md"))) == 2
    assert _commit_count(artifacts) == 1


def test_a_blocked_turn_in_human_mode_parks_and_resumes_with_the_answer(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A human operator is asked directly, and the answer reaches the next dev turn."""
    agent = FakeAgent(workspace, blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs, operator_mode="human"), env(), agent)

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
    agent = FakeAgent(workspace, red=MAX_LAPS + 1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace, stray=1)

    result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 2}, agent.counts()
    report = str(agent.args_for("dev-review")[1]["report"])
    assert "Uncommitted work" in report, report
    assert "scratch.go" in report, report
    assert subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace["api"], check=True, capture_output=True, text=True,
    ).stdout == ""


def test_a_backlog_record_filed_under_an_artifacts_dir_in_the_repo_is_not_the_owner_s_leftover(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The workflow files the record and the spec dir, so the owner's clean check does not count them."""
    inside = workspace["api"] / "artifacts"
    shutil.move(core_config.resolve_artifacts_dir(), inside)
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(inside))
    agent = FakeAgent(
        workspace, follow_ups=(_follow_up("Paginate the audit log", "it loads every row"),)
    )

    result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["dev-review"] == 1, agent.counts()
    assert list((workspace["api"] / "artifacts" / "backlogs").rglob("record.md"))


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
    agent = FakeAgent(workspace)
    dev = make_dev(docs).model_copy(update={"preexisting": (entry,)})

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
    story = epics_root() / EPIC / "stories" / STORY / "story.md"
    story.write_text(THREE_CRITERIA, encoding="utf-8")
    git(docs, "add", "-A")
    git(docs, "commit", "-q", "--allow-empty", "-m", "Three criteria")


def test_a_plan_that_skips_a_criterion_goes_back_naming_it(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """The walk check names the criterion the plan left out, and the next turn's full walk finishes."""
    _three_criteria(docs, git)

    class Walks(FakeAgent):
        def _dev_review(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            self.walk = (1, 3) if nth == 1 else (1, 2, 3)
            return super()._dev_review(data, nth)

    agent = Walks(workspace)

    result = drive_flow(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace, walk=(1, 2, 3))

    result = drive_flow(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace, walk=())
    dev = Dev(story=STORY, epic=EPIC, follow_up_title="Tidy the validator")

    result = drive_flow(dev, env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 1}, agent.counts()


PHASE_TURNS = ("dev-plan", "dev-build", "dev-review")


class _SubagentBackend(NullBackend):
    @property
    def supports_subagents(self) -> bool:
        return True


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
    agent = FakeAgent(workspace)

    drive_flow(make_dev(docs), env(), agent)

    assert [c for c in agent.calls if c in PHASE_TURNS] == list(PHASE_TURNS), agent.calls


def test_a_failed_check_reenters_review_and_not_build(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, red=1)

    drive_flow(make_dev(docs), env(), agent)

    turns = [c for c in agent.calls if c in PHASE_TURNS]
    assert turns == ["dev-plan", "dev-build", "dev-review", "dev-review"], agent.calls


def test_an_operator_answer_on_a_build_block_returns_to_build(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, blocked=1, blocked_in="build")
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs, operator_mode="human"), env(), agent)

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
    agent = FakeAgent(workspace, departures=("swap the parser",), advise_from=2)

    result = drive_advised(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace, departures=("swap the parser",), advise_from=9)

    drive_flow(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace, consult_from=2)

    result = drive_advised(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace, consult_from=1)

    result = drive_advised(make_dev(docs), env(), agent)

    assert agent.counts()["dev-review"] == 1, agent.counts()
    assert result.declined == [f"{STORY}/review-1.2"], result


def test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, red=1, session=lambda n: "sess-1")
    run_env = env()

    drive_flow(make_dev(docs), run_env, agent)

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
    agent = FakeAgent(workspace, red=1, session=lambda n: "sess-1")

    drive_flow(make_dev(docs), env(), agent)

    turns = [c for c in agent.calls if c in (*PHASE_TURNS, "dev-follow-up")]
    assert turns == ["dev-plan", "dev-build", "dev-review", "dev-review"], agent.calls


def test_the_plan_turn_on_a_fresh_conversation_carries_the_full_rules(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, session=lambda n: "sess-1")

    drive_flow(make_dev(docs), env(), agent)

    (plan,) = agent.args_for("dev-plan")
    assert plan["opening_brief"] == "", plan
    text = Path(str(plan["brief_path"])).read_text(encoding="utf-8")
    assert "## Story Status" in text, text
    assert "## Commit Identity" in text, text


def test_the_opening_brief_records_an_operator_answer_as_a_product_page(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, session=lambda n: "sess-1")

    drive_flow(make_dev(docs), env(), agent)

    (plan,) = agent.args_for("dev-plan")
    product = str(plan["product_dir"])
    assert "decisions_dir" not in plan, plan
    text = Path(str(plan["brief_path"])).read_text(encoding="utf-8")
    assert "ostler decisions add" not in text, text
    assert f"{product}/<slug>.md" in text, text
    assert "code-structure rule 2.13" in " ".join(text.split()), text


def test_the_build_turn_on_the_plans_conversation_points_at_the_opening_brief(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, session=lambda n: "sess-1")

    drive_flow(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace, session=lambda n: "sess-1")

    drive_flow(make_dev(docs), env(), agent)

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
    agent = FakeAgent(workspace)

    drive_flow(make_dev(docs), env(), agent)

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


def test_a_build_turn_cut_twice_at_its_deadline_parks_and_resumes_on_the_same_session(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, cut=("dev-build", "dev-follow-up"), session=lambda n: "sid-1")
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    (gate,) = seen
    assert "was cut after 180 minutes" in gate, gate
    assert "Its session is kept" in gate, gate
    assert "resolve-operator" not in agent.calls, agent.calls
    builds = [i for i, c in enumerate(agent.calls) if c in ("dev-build", "dev-follow-up")]
    first, second = builds[0], builds[-1]
    assert agent.kwargs[first]["session_chain"] == agent.kwargs[second]["session_chain"]
    assert agent.kwargs[second]["resume_session"] is True
    assert OPERATOR_ANSWER in str(agent.args[second]["operator_context"]), agent.args[second]
    assert agent.nodes[first].deadline == agent.nodes[first].timeout == 10800.0


def test_a_first_deadline_cut_of_the_build_continues_without_a_gate(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, cut=("dev-build",), session=lambda n: "sid-1")
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert seen == [], seen
    builds = [i for i, c in enumerate(agent.calls) if c in ("dev-build", "dev-follow-up") and agent.args[i].get("phase", "build") == "build"]
    second = builds[1]
    assert agent.calls[second] == "dev-follow-up", agent.calls
    assert agent.kwargs[second]["resume_session"] is True
    assert CUT_CONTINUE_NOTE in str(agent.args[second]["note"]), agent.args[second]
    assert agent.kwargs[builds[0]]["session_chain"] == agent.kwargs[second]["session_chain"]


def test_a_second_consecutive_cut_of_the_build_gates_the_operator(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, cut=("dev-build", "dev-build"))
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    (gate,) = seen
    assert "was cut after 180 minutes" in gate, gate
    assert "Escalation #1 " in gate, gate


def test_a_silence_cut_of_the_build_gates_on_the_first_cut(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, silent=("dev-build",), session=lambda n: "sid-1")
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    (gate,) = seen
    assert "went quiet" in gate, gate


def test_a_first_deadline_cut_of_the_review_continues_without_a_gate(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, cut=("dev-review",))
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert seen == [], seen
    assert any(CUT_CONTINUE_NOTE in str(a.get("note", "")) for a in agent.args), agent.args


def test_a_second_consecutive_cut_of_the_review_gates_the_operator(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, cut=("dev-review", "dev-review"))
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    (gate,) = seen
    assert "The review turn was cut" in gate, gate


def test_a_first_deadline_cut_of_the_plan_continues_without_a_gate(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, cut=("dev-plan",), session=lambda n: "sid-1")
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert seen == [], seen


def test_a_cut_resolver_turn_lands_on_the_gate(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace, blocked=1, cut=("resolve-operator",))
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    (gate,) = seen
    assert BLOCK_NOTE in gate, gate
    assert "The resolver turn was cut after 180 minutes" in gate, gate
    assert agent.counts()["resolve-operator"] == 1, agent.counts()


def test_turn_minutes_sets_the_owner_deadline(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = FakeAgent(workspace)

    drive_flow(Dev(story=STORY, epic=EPIC, turn_minutes=7), env(), agent)

    assert {n.deadline for n in agent.nodes if "dev" in n.id} == {420.0}
    assert {n.timeout for n in agent.nodes if "dev" in n.id} == {420.0}
