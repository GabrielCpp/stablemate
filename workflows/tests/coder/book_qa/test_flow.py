"""The book lane: coverage, the seat's turn, the plays of the book tool and where each verdict goes."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

import pytest
from _epics import epics_root
from _books import SHARED_FILES, TODO_BOOK, import_shared, write_todo_book
from _workspace import Workspace, cut_run_worktrees
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.blueprint import NODE_ATTR, node_spec
from workhorse.pyflow.engine import RunEnv
from workhorse.templates import render

from workhorse_workflows.coder.book_qa import flow as book_flow
from workhorse_workflows.coder.book_qa import nodes as book_nodes
from workhorse_workflows.coder.book_qa.flow import BookQa
from workhorse_workflows.coder.shared import qa_owner, roles
from workhorse_workflows.coder.shared.owner import MAX_LAPS
from workhorse_workflows.coder.shared.schemas.qa import StackStatus, StackTarget, StackTornDown
from workhorse_workflows.coder.shared.worktree import digest

STORY = "STORY-1"
EPIC = "EPIC-1"
LEASE = "lease-1"

EPIC_MD = "---\ntitle: Epic One\nstatus: active\n---\n\n# Epic One\n\n## Stories\n\n### STORY-1\n\n- title: Story One\n"

STORY_MD = """---
id: STORY-1
type: story
services: [api]
---

# Story One

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

- **Status**: Done
"""

FINDING: dict[str, str] = {
    "id": "list-drops-token",
    "target": "acme/services/api:1",
    "issue": "the list drops the share token: ListX answered 200 with no token",
    "repair": "keep the token when the list is built",
}

CALLS = [{"service": "api", "calls": ["ListX", "BuildX"]}]


class _Parked(Exception):
    """Raised by the patched `wait_for_answer` to stop a run right at its `Await`."""


def _parked_at(seen: list[str]) -> Callable[..., None]:
    def stop(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        raise _Parked

    return stop


def _spec_dir() -> Path:
    return core_config.resolve_artifacts_dir() / "specs" / STORY


class _Book:
    """`ostler book`, scripted at the process edge: the exit code each verb answers with, in order."""

    def __init__(
        self,
        check: tuple[int, ...] = (0,),
        run: tuple[int, ...] = (0,),
        verified: tuple[int, ...] = (0,),
        changed: dict[str, str] | None = None,
        stamped: tuple[str, ...] = (),
        pending: dict[str, str] | None = None,
        unverified: tuple[str, ...] = (),
    ) -> None:
        self.script = {"check": check, "run": run, "verified": verified}
        self.argv: dict[str, list[list[str]]] = {"check": [], "run": [], "verified": [], "stale": []}
        self.cwds: list[Any] = []
        self.changed = changed or {}
        self.stamped = set(stamped)
        self.pending = pending or {}
        self.unverified = set(unverified)

    def __call__(
        self, argv: list[str], cwd: Any = None, *, check: bool = False, logger: Any = None, env: Any = None
    ) -> subprocess.CompletedProcess[str]:
        verb = argv[argv.index("ostler.book") + 1]
        self.argv[verb].append(argv)
        self.cwds.append(cwd)
        if verb == "stale":
            return self._stale(argv)
        codes = self.script[verb]
        code = codes[min(len(self.argv[verb]), len(codes)) - 1]
        if verb == "verified" and code == 0:
            self.stamped.add(argv[argv.index("verified") + 1])
        return subprocess.CompletedProcess(argv, code, f"{verb} said exit {code}\n", "")

    def _stale(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        module = argv[argv.index("stale") + 1]
        if "--since" in argv:
            report = self.changed.get(module, "")
            code = 1 if report else 0
            return subprocess.CompletedProcess(argv, code, f"since {argv[argv.index('--since') + 1]}, app at head\n{report}", "")
        if module in self.unverified:
            return subprocess.CompletedProcess(argv, 2, "not verified: write the commit with 'verified'\n", "")
        report = "" if module in self.stamped else self.pending.get(module, self.changed.get(module, ""))
        return subprocess.CompletedProcess(argv, 1 if report else 0, f"verified at abc1234, app at def5678\n{report}", "")


class _Stack:
    """The stack nodes, replaced, with the calls each one received."""

    def __init__(self) -> None:
        self.ensured = 0
        self.released = 0
        self.targets = 0
        self.services: list[str] = []
        self.held: list[str] = []
        self.ready: Literal["yes", "no", "unneeded"] = "yes"

    def install(self, monkeypatch: pytest.MonkeyPatch) -> _Stack:
        def stack_target(logger: Any, story: str = "", lease: str = "", repo_dir: str = "", services: list[str] | None = None) -> StackTarget:
            self.targets += 1
            self.services = list(services or [])
            return StackTarget(near="api", lease=lease)

        def ensure_stack(
            logger: Any, repo_dir: str = "", near: str = "", lease: str = ""
        ) -> StackStatus:
            self.ensured += 1
            return StackStatus(ready=self.ready, failed_step="serve")

        def hold_copy(logger: Any, repo_dir: str = "", lease: str = "") -> bool:
            self.held.append(lease)
            return True

        def release_copy(
            logger: Any, repo_dir: str = "", near: str = "", lease: str = ""
        ) -> StackTornDown:
            self.released += 1
            return StackTornDown(torn_down="yes")

        for fn in (stack_target, ensure_stack, hold_copy, release_copy):
            original = getattr(qa_owner, fn.__name__)
            setattr(fn, NODE_ATTR, replace(node_spec(original), fn=fn))
            for module in (book_flow, qa_owner):
                if hasattr(module, fn.__name__):
                    monkeypatch.setattr(module, fn.__name__, fn)
        return self


class _Agent:
    """The book seat's turn, scripted: one reply per turn, and the files it leaves in the repo."""

    def __init__(
        self, repo: Path, *replies: dict[str, Any], stray: str = "", touch: str = "journeys/added.py"
    ) -> None:
        self.repo = repo
        self.touch = touch
        self.replies = replies or ({"status": "passed", "calls": CALLS},)
        self.stray = stray
        self.args: list[dict[str, Any]] = []
        self.calls: list[str] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        self.args.append(ctx.as_dict())
        stem = Path(node.prompt).stem
        assert stem == "qa-book", f"unexpected agent turn: {stem}"
        self.calls.append(stem)
        nth = self.calls.count(stem)
        reply = self.replies[min(nth, len(self.replies)) - 1]
        book = self.repo / "services" / "api" / self.touch
        book.parent.mkdir(parents=True, exist_ok=True)
        book.write_text(f"# turn {nth}\n", encoding="utf-8")
        if self.stray:
            (self.repo / self.stray).write_text("edited\n", encoding="utf-8")
        return f"(scripted) {node.prompt}", {"notes": f"turn {nth}", **reply}

    def counts(self) -> Counter[str]:
        return Counter(self.calls)


@pytest.fixture
def lane(
    repo: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """A repo with one story that lists `api`, and an executable book for `api` committed under `services/`."""
    write(epics_root() / EPIC / "epic.md", EPIC_MD)
    write(epics_root() / EPIC / "stories" / STORY / "story.md", STORY_MD)
    write(_spec_dir() / "plan-context.json", json.dumps({"story": STORY, "services": []}))
    write(repo / "services" / "api" / "service.py", "# the api book\n")
    write(repo / "services" / "api" / "records.py", "# base\n")
    write(repo / "services" / "api" / "journeys" / "existing.py", "# base\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: add the api book")
    return repo


@pytest.fixture
def book(monkeypatch: pytest.MonkeyPatch) -> Callable[..., _Book]:
    def install(**kwargs: Any) -> _Book:
        scripted = _Book(**kwargs)
        monkeypatch.setattr(book_nodes, "run_tool", scripted)
        return scripted

    return install


@pytest.fixture
def stack(monkeypatch: pytest.MonkeyPatch) -> _Stack:
    return _Stack().install(monkeypatch)


def _flow(**kwargs: Any) -> BookQa:
    return BookQa(story=STORY, operator_mode="human", **kwargs)


def _commits(repo: Path, git: Callable[..., subprocess.CompletedProcess[str]]) -> list[str]:
    return git(repo, "log", "--format=%s%n%b%x00").stdout.split("\0")[:-1]


def test_a_story_with_no_covered_service_passes_with_no_seat_and_no_stack(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A service whose `service.py` is absent is not covered, so the lane must cost nothing there."""
    (lane / "services" / "api" / "service.py").unlink()
    git(lane, "commit", "-qam", "chore: drop the api book")
    scripted = book()
    agent = _Agent(lane)

    result = drive_flow(_flow(), env(), agent)

    assert (result.status, result.findings) == ("passed", [])
    assert agent.calls == [], agent.calls
    assert (stack.targets, stack.ensured, stack.released) == (0, 0, 0)
    assert scripted.argv["check"] == [] and scripted.argv["run"] == []


def test_a_green_pass_plays_the_named_calls_records_them_and_lands_the_book(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The judgement plays what the seat named against the run's copy, and the seat's edit is committed under the story's footer."""
    scripted = book()
    agent = _Agent(lane)

    result = drive_flow(_flow(), env(), agent)

    assert (result.status, result.findings) == ("passed", [])
    assert agent.counts() == {"qa-book": 1}, agent.counts()
    [argv] = scripted.argv["run"]
    assert argv[argv.index("--only") + 1] == "ListX,BuildX", argv
    assert argv[argv.index("--copy") + 1] == stack_lease(argv), argv
    assert argv[argv.index("services.api") - 1] == "run", argv
    record = json.loads((_spec_dir() / "book-qa.json").read_text(encoding="utf-8"))
    assert record == {"services": CALLS}, record
    landed = _commits(lane, git)[0]
    assert landed.startswith("test(acme): play ") and "Story: STORY-1" in landed, landed
    assert git(lane, "status", "--porcelain").stdout == ""
    assert stack.released == 1, stack.released
    assert stack.held == [stack_lease(argv)], stack.held


WEB_CHANGED = "## Stale elements\n- Home: web/page.tsx (1 commits: abc1234)\n"

API_CHANGED = "## Changed files no element names\n- src/api.py (1 commits: abc1234)\n"

WEB_BEHIND = WEB_CHANGED + "\n## Changed files no element names\n- web/older.tsx (2 commits: 1111111, 2222222)\n"

BOTH_CALLS = [*CALLS, {"service": "web", "calls": ["ShowHome"]}]


def _add_web_book(lane: Path, git: Callable[..., subprocess.CompletedProcess[str]], write: Callable[[Path, str], Path]) -> None:
    write(lane / "services" / "web" / "service.py", "# the web book\n")
    git(lane, "add", "-A")
    git(lane, "commit", "-qm", "chore: add the web book")


def _module_of(argv: list[str]) -> str:
    return next(arg for arg in argv if arg.startswith("services."))


def test_a_story_that_declares_one_service_and_whose_diff_touches_another_books_source_covers_both(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The story named `api`, its commits changed the source `web`'s book points at, and a book left behind is never verified."""
    _add_web_book(lane, git, write)
    base = git(lane, "rev-parse", "HEAD").stdout.strip()
    scripted = book(changed={"services.web": WEB_CHANGED})
    agent = _Agent(lane, {"status": "passed", "calls": BOTH_CALLS})

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert agent.args[0]["services"] == ["api", "web"], agent.args[0]["services"]
    assert [_module_of(argv) for argv in scripted.argv["check"]] == ["services.api", "services.web"]
    assert {argv[argv.index("--since") + 1] for argv in scripted.argv["stale"] if "--since" in argv} == {base}
    assert stack.services == ["api", "web"], stack.services


def test_a_story_whose_diff_touches_no_book_source_covers_only_its_declared_services_with_a_book(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A book no commit of the story reached stays out of the lane, so it costs no check and no play."""
    _add_web_book(lane, git, write)
    scripted = book()
    agent = _Agent(lane)

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert agent.args[0]["services"] == ["api"], agent.args[0]["services"]
    assert [_module_of(argv) for argv in scripted.argv["check"]] == ["services.api"]


def test_a_declared_service_with_no_book_is_left_out(
    lane: Path,
    book: Callable[..., _Book],
    logger: logging.Logger,
) -> None:
    """The lane cannot judge a service that has no executable book."""
    book()

    covered = book_nodes.covered_services(logger, ["api", "ghost"], repo_dir=str(lane))

    assert covered.services == ["api"], covered


def test_a_book_current_at_the_story_base_is_stamped_verified_after_a_pass(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The story's commits are all that the book awaited, so the judged commit is the one to record."""
    _add_web_book(lane, git, write)
    scripted = book(changed={"services.api": API_CHANGED, "services.web": WEB_CHANGED})
    agent = _Agent(lane, {"status": "passed", "calls": BOTH_CALLS})

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert [_module_of(argv) for argv in scripted.argv["verified"]] == ["services.api", "services.web"]


def test_the_book_lane_stamps_nothing_after_a_red_play(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A stamp over a book that did not pass would hide the next catch-up from what is wrong."""
    scripted = book(run=(1,))
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _parked_at(seen)), pytest.raises(_Parked):
        drive_flow(_flow(), env(), _Agent(lane))

    assert scripted.argv["verified"] == []


def test_the_book_lane_stamps_nothing_while_the_seat_reports_a_finding(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The developer changes the app after a finding, so the commit judged now is not the one to record."""
    scripted = book()
    agent = _Agent(lane, {"status": "findings", "findings": [FINDING], "calls": CALLS})

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "refix", result
    assert scripted.argv["verified"] == []


def test_a_refusal_on_the_storys_own_unnamed_file_goes_back_to_the_seat(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`verified` refuses while a changed file is named by no element, and the seat is the one who names it."""
    scripted = book(verified=(1, 0), changed={"services.api": API_CHANGED})
    agent = _Agent(lane)

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"qa-book": 2}, agent.counts()
    assert "verified said exit 1" in agent.args[1]["report"], agent.args[1]["report"]
    assert len(scripted.argv["verified"]) == 2


def test_a_book_behind_before_the_story_is_not_stamped_and_sends_no_lap(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Changes from other people's commits are the catch-up flow's to judge, so the stamp stays where it was."""
    _add_web_book(lane, git, write)
    scripted = book(
        changed={"services.api": API_CHANGED, "services.web": WEB_CHANGED},
        pending={"services.web": WEB_BEHIND},
    )
    agent = _Agent(lane, {"status": "passed", "calls": BOTH_CALLS})

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"qa-book": 1}, agent.counts()
    assert [_module_of(argv) for argv in scripted.argv["verified"]] == ["services.api"]


def test_a_book_with_no_verified_commit_is_not_stamped(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A first book belongs to the book-writing flow."""
    _add_web_book(lane, git, write)
    scripted = book(
        changed={"services.api": API_CHANGED, "services.web": WEB_CHANGED},
        unverified=("services.web",),
    )
    agent = _Agent(lane, {"status": "passed", "calls": BOTH_CALLS})

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert [_module_of(argv) for argv in scripted.argv["verified"]] == ["services.api"]


def test_a_resumed_lane_that_already_stamped_does_not_stamp_again(
    lane: Path,
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A book current at the app's HEAD owes no second stamp, so the replay lands no second commit for it."""
    write(_spec_dir() / "book-qa.json", json.dumps({"services": CALLS}))
    scripted = book(stamped=("services.api",), changed={"services.api": API_CHANGED})

    result = drive_flow(_flow(), env(), _Agent(lane))

    assert result.status == "passed", result
    assert scripted.argv["verified"] == []


def test_the_claims_the_seat_could_not_state_are_recorded_beside_its_calls(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The scenario lane reads the record to learn which claims the book left to it."""
    book()
    unreached = ["no request reaches the report service"]
    agent = _Agent(lane, {"status": "passed", "calls": CALLS, "unreached": unreached})

    drive_flow(_flow(), env(), agent)

    record = json.loads((_spec_dir() / "book-qa.json").read_text(encoding="utf-8"))
    assert record == {"services": CALLS, "unreached": unreached}, record


def stack_lease(argv: list[str]) -> str:
    return argv[argv.index("--copy") + 1]


def test_a_finding_beside_a_green_run_goes_back_to_the_developer_and_the_book_still_lands(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A declared defect makes the run green by design, so only the finding can stop the story passing."""
    book()
    agent = _Agent(lane, {"status": "findings", "findings": [FINDING], "calls": CALLS})

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "refix", result
    assert [f.id for f in result.findings] == ["list-drops-token"], result.findings
    assert "Story: STORY-1" in _commits(lane, git)[0]
    assert stack.released == 1


def test_a_findings_verdict_that_lists_no_finding_goes_back_to_the_seat(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """An empty list would pass the story over a defect the seat said it found."""
    book()
    agent = _Agent(lane, {"status": "findings", "calls": CALLS}, {"status": "passed", "calls": CALLS})

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert "listed none" in agent.args[1]["report"], agent.args[1]["report"]


def test_a_red_run_with_no_finding_goes_back_to_the_seat_with_the_output(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A disagreement the seat did not turn into a finding is the seat's to repair, never a developer finding."""
    scripted = book(run=(1, 0))
    agent = _Agent(lane)

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"qa-book": 2}, agent.counts()
    assert agent.args[0]["report"] == ""
    assert "run said exit 1" in agent.args[1]["report"], agent.args[1]["report"]
    assert len(scripted.argv["run"]) == 2


def test_a_red_check_goes_back_to_the_seat_before_any_play(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A book that does not build cannot be played, so the run must not reach the stack with it."""
    scripted = book(check=(2, 0))
    agent = _Agent(lane)

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert "check said exit 2" in agent.args[1]["report"], agent.args[1]["report"]
    assert len(scripted.argv["run"]) == 1


def test_a_run_that_stays_red_parks_at_the_operator_after_the_lap_budget(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A workflow never gives up: a spent repair budget is an `Await`, not a failure."""
    book(run=(1,))
    agent = _Agent(lane)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _parked_at(seen)), pytest.raises(_Parked):
        drive_flow(_flow(), env(), agent)

    assert agent.counts() == {"qa-book": MAX_LAPS + 1}, agent.counts()
    assert len(seen) == 1 and "repair turn(s)" in seen[0] and "run said exit 1" in seen[0], seen


def test_a_run_that_could_not_judge_asks_the_operator_and_spends_no_second_turn(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Exit 3 says nothing about the story, so it is never a finding and never a lap."""
    scripted = book(run=(3,))
    agent = _Agent(lane)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _parked_at(seen)), pytest.raises(_Parked):
        drive_flow(_flow(), env(), agent)

    assert agent.counts() == {"qa-book": 1}, agent.counts()
    assert len(scripted.argv["run"]) == 1
    assert len(seen) == 1 and "the QA environment" in seen[0] and "run said exit 3" in seen[0], seen


def test_a_stack_that_did_not_come_up_asks_the_operator_before_the_seat_starts(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The seat cannot repair a stack, so it must not be paid for a turn on one."""
    stack.ready = "no"
    book()
    agent = _Agent(lane)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _parked_at(seen)), pytest.raises(_Parked):
        drive_flow(_flow(), env(), agent)

    assert agent.calls == [], agent.calls
    assert "the QA environment" in seen[0] and "`serve`" in seen[0], seen


def test_the_lane_passes_the_storys_services_to_the_stack_target(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The stack target picks a book by the services the story names, so the lane must hand them over."""
    book()

    drive_flow(_flow(), env(), _Agent(lane))

    assert stack.services == ["api"], stack.services


def test_a_second_visit_replays_the_recorded_calls_with_no_seat(
    lane: Path,
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """After a developer fix the same calls are the exam, and a model turn buys nothing while they pass."""
    write(_spec_dir() / "book-qa.json", json.dumps({"services": CALLS}))
    scripted = book()
    agent = _Agent(lane)

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == [], agent.calls
    [argv] = scripted.argv["run"]
    assert argv[argv.index("--only") + 1] == "ListX,BuildX", argv


def test_a_replay_keeps_the_recorded_unreached_claims(
    lane: Path,
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A replay with no seat turn must not lose the claims the book never stated."""
    unreached = ["no request reaches the report service"]
    write(_spec_dir() / "book-qa.json", json.dumps({"services": CALLS, "unreached": unreached}))
    book()
    agent = _Agent(lane)

    drive_flow(_flow(), env(), agent)

    record = json.loads((_spec_dir() / "book-qa.json").read_text(encoding="utf-8"))
    assert record == {"services": CALLS, "unreached": unreached}, record
    assert agent.calls == [], agent.calls


def test_a_green_replay_over_a_recorded_finding_sends_it_back_again(
    lane: Path,
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The finding's defect is declared known, so the replay stays green while the app is still wrong, and the story must not pass on it."""
    write(_spec_dir() / "book-qa.json", json.dumps({"services": CALLS, "findings": [FINDING]}))
    book()
    agent = _Agent(lane)

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "refix", result
    assert [f.id for f in result.findings] == ["list-drops-token"], result.findings
    assert agent.calls == [], agent.calls


def test_a_red_replay_goes_to_the_seat_with_the_output_as_its_report(
    lane: Path,
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A fix that moved the app's answer leaves the book stale, and the seat is the one who restates it."""
    write(_spec_dir() / "book-qa.json", json.dumps({"services": CALLS}))
    book(run=(1, 0))
    agent = _Agent(lane)

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"qa-book": 1}, agent.counts()
    assert "run said exit 1" in agent.args[0]["report"], agent.args[0]["report"]


def test_a_seat_that_names_no_call_for_a_covered_service_is_sent_back_before_any_play(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """With no calls named the run would judge nothing and pass the story."""
    scripted = book()
    agent = _Agent(lane, {"status": "passed", "calls": []}, {"status": "passed", "calls": CALLS})

    result = drive_flow(_flow(), env(), agent)

    assert result.status == "passed", result
    assert "Name the calls the story touches" in agent.args[1]["report"], agent.args[1]["report"]
    assert "api" in agent.args[1]["report"]
    assert len(scripted.argv["run"]) == 1


def test_a_product_edit_outside_the_book_is_refused_and_sent_back_unlanded(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The seat edits the book only, so a changed product path must not ride into the story's commit."""
    book()
    agent = _Agent(lane, stray="README.md")

    with patch.object(pyflow_park, "wait_for_answer", _parked_at([])), pytest.raises(_Parked):
        drive_flow(_flow(), env(), agent)

    assert "`README.md`" in agent.args[1]["report"], agent.args[1]["report"]
    assert not any("play " in c for c in _commits(lane, git)), _commits(lane, git)
    assert not (_spec_dir() / "book-qa.json").exists()


@pytest.fixture
def workspace_lane(
    workspace: Workspace,
    git: Callable[..., subprocess.CompletedProcess[str]],
    write: Callable[[Path, str], Path],
) -> Workspace:
    """A workspace whose artifacts repo holds one story that lists `api` and the committed book of `api`."""
    write(epics_root() / EPIC / "epic.md", EPIC_MD)
    write(epics_root() / EPIC / "stories" / STORY / "story.md", STORY_MD)
    write(_spec_dir() / "plan-context.json", json.dumps({"story": STORY, "services": []}))
    write(workspace.artifacts / "services" / "api" / "service.py", "# the api book\n")
    write(workspace.artifacts / "services" / "api" / "journeys" / "existing.py", "# base\n")
    git(workspace.artifacts, "add", "-A")
    git(workspace.artifacts, "commit", "-qm", "chore: add the api book")
    return workspace


def test_in_a_workspace_the_lane_finds_the_book_in_the_artifacts_folder(workspace_lane: Workspace) -> None:
    covered = book_nodes.covered_services(
        logging.getLogger("test"), ["api"], repo_dir=str(workspace_lane.api)
    )

    assert covered.services == ["api"]


def test_in_a_workspace_the_book_plays_from_the_artifacts_folder(
    workspace_lane: Workspace,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    scripted = book()

    result = drive_flow(_flow(), env(), _Agent(workspace_lane.artifacts))

    assert result.status == "passed", result
    assert scripted.cwds and {Path(cwd) for cwd in scripted.cwds} == {workspace_lane.artifacts}
    [argv] = scripted.argv["check"][:1]
    assert argv[argv.index("--app") + 1] == str(workspace_lane.api), argv


def test_in_a_workspace_the_book_change_commits_in_the_artifacts_repo(
    workspace_lane: Workspace,
    git: Callable[..., subprocess.CompletedProcess[str]],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    api_head = git(workspace_lane.api, "rev-parse", "HEAD").stdout
    book()

    drive_flow(_flow(), env(), _Agent(workspace_lane.artifacts))

    landed = git(workspace_lane.artifacts, "show", "--name-only", "--format=%s", "HEAD").stdout
    assert landed.startswith("test("), landed
    assert "services/api/journeys/added.py" in landed, landed
    assert git(workspace_lane.api, "rev-parse", "HEAD").stdout == api_head


def test_in_a_workspace_a_code_edit_by_the_book_seat_is_refused(
    workspace_lane: Workspace,
    git: Callable[..., subprocess.CompletedProcess[str]],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    book()
    agent = _Agent(workspace_lane.artifacts, stray=str(workspace_lane.api / "app.py"))

    with patch.object(pyflow_park, "wait_for_answer", _parked_at([])), pytest.raises(_Parked):
        drive_flow(_flow(), env(), agent)

    assert "`app.py`" in agent.args[1]["report"], agent.args[1]["report"]
    assert not any("play " in c for c in _commits(workspace_lane.artifacts, git))


@pytest.fixture
def run_trees(
    workspace_lane: Workspace,
    tmp_path: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> Workspace:
    """The workspace's run worktrees on one branch, with the test standing in the api one."""
    trees = cut_run_worktrees(workspace_lane, tmp_path / "trees", "run/coder-t", git)
    monkeypatch.chdir(trees.api)
    return trees


def test_in_a_worktree_run_the_book_plays_from_the_artifacts_worktree(
    run_trees: Workspace,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    scripted = book()

    result = drive_flow(_flow(), env(), _Agent(run_trees.artifacts))

    assert result.status == "passed", result
    assert scripted.cwds and {Path(cwd) for cwd in scripted.cwds} == {run_trees.artifacts}
    [argv] = scripted.argv["check"][:1]
    assert argv[argv.index("--app") + 1] == str(run_trees.api), argv


def test_in_a_worktree_run_the_book_change_commits_on_the_run_branch_of_the_artifacts_worktree(
    workspace_lane: Workspace,
    run_trees: Workspace,
    git: Callable[..., subprocess.CompletedProcess[str]],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    main_head = git(workspace_lane.artifacts, "rev-parse", "HEAD").stdout
    book()

    drive_flow(_flow(), env(), _Agent(run_trees.artifacts))

    assert git(workspace_lane.artifacts, "rev-parse", "HEAD").stdout == main_head
    landed = git(run_trees.artifacts, "show", "--name-only", "--format=%s", "HEAD").stdout
    assert landed.startswith("test("), landed
    assert "services/api/journeys/added.py" in landed, landed


def test_in_a_worktree_run_a_book_path_outside_the_covered_services_is_not_a_stray_code_edit(
    run_trees: Workspace,
    write: Callable[[Path, str], Path],
) -> None:
    write(run_trees.artifacts / "services" / "other" / "x.py", "x\n")
    write(run_trees.artifacts / "services" / "api" / "journeys" / "added.py", "y\n")

    result = book_nodes.commit_service_book(
        logging.getLogger("test"), ["api"], repo_dir=str(run_trees.api)
    )

    assert result.refused == "", result.refused
    assert result.committed


def test_a_monorepo_book_commit_takes_the_files_it_imports_and_no_compiled_file(
    lane: Path, git: Callable[..., subprocess.CompletedProcess[str]]
) -> None:
    import_shared(lane, "api")

    result = book_nodes.commit_service_book(logging.getLogger("test"), ["api"], repo_dir=str(lane))

    assert result.refused == "", result.refused
    assert result.committed
    landed = git(lane, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert sorted(landed) == sorted([*SHARED_FILES, "services/api/service.py"])
    assert "pyc" not in git(lane, "ls-files").stdout


def test_in_a_workspace_the_book_commit_takes_the_files_it_imports_and_no_compiled_file(
    workspace_lane: Workspace, git: Callable[..., subprocess.CompletedProcess[str]]
) -> None:
    import_shared(workspace_lane.artifacts, "api")

    result = book_nodes.commit_service_book(logging.getLogger("test"), ["api"], repo_dir=str(workspace_lane.api))

    assert result.refused == "", result.refused
    landed = git(workspace_lane.artifacts, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert sorted(landed) == sorted([*SHARED_FILES, "services/api/service.py"])
    assert "pyc" not in git(workspace_lane.artifacts, "ls-files").stdout


def test_an_imported_file_the_commit_leaves_untracked_is_refused_with_its_path(
    workspace_lane: Workspace, git: Callable[..., subprocess.CompletedProcess[str]]
) -> None:
    root = workspace_lane.artifacts
    import_shared(root, "api")
    kept = [f"{rel}\0{digest(root, rel)}" for rel in SHARED_FILES]

    result = book_nodes.commit_service_book(
        logging.getLogger("test"), ["api"], preexisting=kept, repo_dir=str(workspace_lane.api)
    )

    assert result.committed
    for rel in SHARED_FILES:
        assert f"- `{rel}`" in result.refused, result.refused


def test_a_refused_book_commit_is_logged_with_each_path_and_sent_to_the_seat(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    book()
    agent = _Agent(lane, stray="README.md")

    with caplog.at_level(logging.WARNING), patch.object(pyflow_park, "wait_for_answer", _parked_at([])), pytest.raises(_Parked):
        drive_flow(_flow(), env(), agent)

    logged = [record.getMessage() for record in caplog.records if "the book commit was refused" in record.getMessage()]
    assert logged and all("`README.md`" in line for line in logged), caplog.text
    assert "`README.md`" in agent.args[1]["report"], agent.args[1]["report"]


def test_a_book_root_with_no_git_lands_nothing_and_does_not_raise(
    workspace_lane: Workspace, tmp_path: Path
) -> None:
    shutil.rmtree(workspace_lane.artifacts / ".git")
    (workspace_lane.artifacts / "services" / "api" / "journeys" / "added.py").write_text("x\n", encoding="utf-8")

    result = book_nodes.commit_service_book(
        logging.getLogger("test"), ["api"], repo_dir=str(workspace_lane.api)
    )

    assert result.committed is False and result.refused == ""


def test_a_book_pointer_to_a_missing_file_fails_the_check(repo: Path) -> None:
    write_todo_book(repo)

    played = book_nodes.book_check(logging.getLogger("test"), "api", repo_dir=str(repo))

    assert played.exit_code != 0
    assert "does not exist under" in played.output


def test_a_book_pointer_to_a_missing_file_fails_the_spec_gate(repo: Path) -> None:
    write_todo_book(repo)

    gate = book_nodes.verify_book_spec(
        logging.getLogger("test"), ["api"], "documented", repo_dir=str(repo)
    )

    assert gate.status == "invalid"
    assert "does not exist under" in gate.notes


def test_a_book_whose_pointers_exist_passes_the_check(repo: Path) -> None:
    write_todo_book(repo)
    shutil.copy(TODO_BOOK / "app.py", repo / "app.py")

    played = book_nodes.book_check(logging.getLogger("test"), "api", repo_dir=str(repo))

    assert played.exit_code == 0, played.output


def _played_whole(argv: list[str]) -> bool:
    return "--only" not in argv


def test_a_pass_that_changed_only_a_new_journey_and_the_index_plays_the_named_calls(
    lane: Path,
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A new journey states one claim nothing else reads, so the named calls judge it."""
    write(lane / "services" / "api" / "index.tsv", "refreshed\n")
    write(lane / "services" / "api" / "decisions" / "why.md", "why\n")
    scripted = book()

    drive_flow(_flow(), env(), _Agent(lane, touch="journeys/new.py"))

    [argv] = scripted.argv["run"]
    assert argv[argv.index("--only") + 1] == "ListX,BuildX", argv


@pytest.mark.parametrize("touch", ["model/records.py", "journeys/existing.py", "records.py"])
def test_a_pass_that_changed_a_shared_part_plays_the_whole_book(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    touch: str,
) -> None:
    """A model, fixture or existing journey edit can move a call the pass never named."""
    scripted = book()

    result = drive_flow(_flow(), env(), _Agent(lane, touch=touch))

    assert result.status == "passed", result
    [argv] = scripted.argv["run"]
    assert _played_whole(argv), argv
    assert argv[argv.index("--copy") + 1] == stack_lease(argv), argv


def test_a_shared_edit_beside_a_new_journey_still_plays_the_whole_book(
    lane: Path,
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """One shared path decides the scope, whatever else the pass added."""
    write(lane / "services" / "api" / "fixtures.py", "# new\n")
    scripted = book()

    drive_flow(_flow(), env(), _Agent(lane, touch="journeys/new.py"))

    assert _played_whole(scripted.argv["run"][0]), scripted.argv["run"]


def test_the_recorded_replay_stays_targeted_when_nothing_changed(
    lane: Path,
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A replay has no seat turn and no change, so the whole book buys nothing."""
    write(_spec_dir() / "book-qa.json", json.dumps({"services": CALLS}))
    scripted = book()

    drive_flow(_flow(), env(), _Agent(lane))

    assert not _played_whole(scripted.argv["run"][0]), scripted.argv["run"]


def test_the_whole_book_play_registers_the_findings_outside_the_named_calls(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A finding on a field the story never touched is the owner's to answer, so the whole play lists it in the register."""
    scripted = book()

    drive_flow(_flow(), env(), _Agent(lane, touch="records.py"))

    [argv] = scripted.argv["run"]
    assert _played_whole(argv), argv
    assert argv[argv.index("--register-outside") + 1] == "ListX,BuildX", argv
    assert "--register" not in argv, argv


def test_a_play_of_the_named_calls_registers_nothing(
    lane: Path,
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The story's own calls go back to the seat, and a targeted play reaches no others."""
    scripted = book()

    drive_flow(_flow(), env(), _Agent(lane))

    [argv] = scripted.argv["run"]
    assert "--register-outside" not in argv and "--register" not in argv, argv


def test_the_register_is_a_record_no_play_reads_for_scope() -> None:
    assert book_nodes.shared_book_paths("api", {"services/api/UNDERSPECIFIED.md": True}) == []


def test_the_seat_prompt_leaves_the_register_to_the_owner(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    coder = Path(roles.__file__).resolve().parent.parent

    text = render("book_qa/prompts/qa-book.md", {"_node_cwd": str(repo), "services": ["api"]}, coder)

    assert "UNDERSPECIFIED.md" in text
    assert "owner's list" in text


def test_the_shared_rule_names_what_a_play_reads() -> None:
    changed = {
        "services/api/journeys/new.py": True,
        "services/api/journeys/old.py": False,
        "services/api/index.tsv": False,
        "services/api/WALLS.md": True,
        "services/api/DISAGREEMENTS.md": False,
        "services/api/VERIFIED": False,
        "services/api/decisions/a.md": False,
        "services/api/model/records.py": True,
        "services/other/model/records.py": True,
    }

    shared = book_nodes.shared_book_paths("api", changed)

    assert shared == ["services/api/journeys/old.py", "services/api/model/records.py"], shared


def test_the_shared_rule_reads_each_surface_folder_as_a_book_of_its_own() -> None:
    changed = {
        "services/api/web/index.tsv": False,
        "services/api/web/journeys/new.py": True,
        "services/api/http/journeys/old.py": False,
        "services/api/http/service.py": False,
        "services/api/model/records.py": False,
    }

    shared = book_nodes.shared_book_paths("api", changed, frozenset({"http", "web"}))

    assert shared == [
        "services/api/http/journeys/old.py",
        "services/api/http/service.py",
        "services/api/model/records.py",
    ], shared


def _two_surfaces(
    repo: Path, git: Callable[..., subprocess.CompletedProcess[str]], write: Callable[[Path, str], Path]
) -> None:
    (repo / "services" / "api" / "service.py").unlink()
    for surface, kind, call in (("http", "endpoint", "ListX"), ("web", "interaction", "BuildX")):
        write(repo / "services" / "api" / surface / "service.py", f"# the api {surface} surface\n")
        write(repo / "services" / "api" / surface / "index.tsv", f"{kind}\t{call}\tx:{call}\td\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: split the api book by surface")


def test_a_book_with_two_surfaces_checks_each_and_plays_each_its_own_calls(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Each surface is its own module, so a call is played only by the surface whose index lists it."""
    _two_surfaces(lane, git, write)
    scripted = book()

    result = drive_flow(_flow(), env(), _Agent(lane, touch="web/journeys/added.py"))

    assert result.status == "passed", result
    checked = [argv[argv.index("check") + 1] for argv in scripted.argv["check"]]
    assert checked[:2] == ["services.api.http", "services.api.web"], checked
    played = {argv[argv.index("run") + 1]: argv for argv in scripted.argv["run"]}
    assert sorted(played) == ["services.api.http", "services.api.web"], played
    assert played["services.api.http"][played["services.api.http"].index("--only") + 1] == "ListX"
    assert played["services.api.web"][played["services.api.web"].index("--only") + 1] == "BuildX"
    for module, argv in played.items():
        assert argv[argv.index("--out") + 1].endswith(f"/{module}"), argv


def test_a_shared_model_edit_plays_every_surface_whole_and_registers_outside_its_calls(
    lane: Path,
    git: Callable[..., subprocess.CompletedProcess[str]],
    write: Callable[[Path, str], Path],
    book: Callable[..., _Book],
    stack: _Stack,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The model sits under every surface, so an edit there can move a call of any of them."""
    _two_surfaces(lane, git, write)
    scripted = book()

    drive_flow(_flow(), env(), _Agent(lane, touch="model/records.py"))

    played = {argv[argv.index("run") + 1]: argv for argv in scripted.argv["run"]}
    assert sorted(played) == ["services.api.http", "services.api.web"], played
    assert all(_played_whole(argv) for argv in played.values()), played
    assert played["services.api.http"][played["services.api.http"].index("--register-outside") + 1] == "ListX"
    assert played["services.api.web"][played["services.api.web"].index("--register-outside") + 1] == "BuildX"


def test_the_seat_prompt_renders_the_restructure_step_and_the_narrowed_unreached_rule(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    coder = Path(roles.__file__).resolve().parent.parent

    text = render("book_qa/prompts/qa-book.md", {"_node_cwd": str(repo), "services": ["api"]}, coder)

    assert "Restructure when the book's shape is in the way" in text
    assert "not a contract" in text
    assert "`unreached` is only for a claim no call or backstage step can" in text
    assert "is not\n   `unreached`: restructure the book for it" in text
