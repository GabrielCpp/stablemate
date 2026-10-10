"""End-to-end tests for the `fix_ci` flow: the walk, the owner's laps, and where each one parks."""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import Blueprint
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.fix_ci import flow as fix_ci_flow
from workhorse_workflows.coder.fix_ci.flow import FixCi
from workhorse_workflows.coder.shared import ci as ci_nodes
from workhorse_workflows.coder.shared.ci import push_ci_fix, select_ci_repo
from workhorse_workflows.coder.shared.owner import MAX_LAPS
from workhorse_workflows.coder.shared.schemas.pr import MergeOutcome

EPIC = "EPIC-1"
BRANCH = f"feat/{EPIC}"

RED: tuple[int, int, int, str] = (1, 0, 1, "build#7(failure)")
GREEN: tuple[int, int, int, str] = (1, 0, 0, "")

OWNER_NOTE = "the fix needs a secret this token cannot read"
OPERATOR_ANSWER = "The secret is rotated now. Re-run the job."


@pytest.fixture(autouse=True)
def _no_ambient_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """No GitHub token from the developer's own shell."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


@pytest.fixture
def workspace(
    tmp_path: Path,
    repo: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write_json: Callable[[Path, Any], Path],
    ambient: dict[str, str],
) -> dict[str, Path]:
    """Two real repos and the VSCode workspace file that names them, in order."""
    root = tmp_path / "ws"
    root.mkdir()
    paths: dict[str, Path] = {}
    for name in ("api", "web"):
        path = root / name
        path.mkdir()
        git(path, "init", "-q", "-b", "main")
        (path / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        git(path, "add", "-A")
        git(path, "commit", "-qm", "Initial commit")
        git(path, "branch", BRANCH)
        paths[name] = path

    workspace_file = root / "acme.code-workspace"
    write_json(
        workspace_file,
        {"folders": [{"name": "api", "path": "api"}, {"name": "web", "path": "web"}]},
    )
    ambient["workspace_file"] = str(workspace_file)
    return {"docs": repo, **paths}


class _Turn:
    """The scripted agent: the CI owner, and a resolver that always escalates."""

    def __init__(self, *statuses: str) -> None:
        self.statuses = list(statuses) or ["fixed"]
        self.stems: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.nodes: list[Any] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        self.stems.append(stem)
        if stem == "resolve-operator":
            return f"(scripted) {node.prompt}", {
                "decision": "escalated",
                "summary": "only the operator can decide this",
            }
        self.calls.append(ctx.as_dict())
        self.nodes.append(node)
        status = self.statuses[min(len(self.calls), len(self.statuses)) - 1]
        return f"(scripted) {node.prompt}", {"status": status, "notes": OWNER_NOTE}

    def counts(self) -> Counter[str]:
        return Counter(self.stems)


class _GitHub:
    """The GitHub boundary, scripted at its four exits, and recording what crossed them."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        runs: list[tuple[int, int, int, str]],
        push_ok: bool = True,
    ) -> None:
        self.runs = list(runs)
        self.push_ok = push_ok
        self.polls = 0
        self.pr_refs: list[str] = []
        self.pushes: list[tuple[str, str]] = []
        monkeypatch.setattr(ci_nodes, "resolve_github_token", lambda root: "t0ken")
        monkeypatch.setattr(
            ci_nodes, "origin_url", lambda root: f"https://github.com/example-org/{Path(root).name}.git"
        )
        monkeypatch.setattr(
            ci_nodes, "resolve_repo", lambda root, token: (self, f"example-org/{Path(root).name}")
        )
        monkeypatch.setattr(ci_nodes, "_resolve_pr", self._pr)
        monkeypatch.setattr(ci_nodes, "_poll_runs", self._poll)
        monkeypatch.setattr(ci_nodes, "push_branch", self._push)

    def _pr(self, repo: Any, pr_ref: str) -> Any:
        self.pr_refs.append(pr_ref)
        return SimpleNamespace(head=SimpleNamespace(sha="c0ffee1"))

    def _poll(self, repo: Any, head_sha: str) -> tuple[int, int, int, str]:
        reply = self.runs[min(self.polls, len(self.runs) - 1)]
        self.polls += 1
        return reply

    def _push(self, path: Any, token: str, branch: str) -> bool:
        self.pushes.append((Path(path).name, branch))
        return self.push_ok


def _answers(
    seen: list[tuple[Path, str]], then: Callable[[], object] = lambda: None
) -> Callable[..., None]:
    """A stand-in for the human the `Await` is waiting on, who may fix something first."""

    def answered(path: Path, **kwargs: Any) -> None:
        then()
        seen.append((path, path.read_text(encoding="utf-8")))
        path.write_text(f"STATUS: ANSWERED\n\n{OPERATOR_ANSWER}\n", encoding="utf-8")

    return answered


def _walk(run_env: RunEnv) -> list[str]:
    """The repos this run picked, in order — `select_ci_repo`'s last `processed` list."""
    output = run_env.writer.run_dir / "select_ci_repo" / "output.json"
    return json.loads(output.read_text(encoding="utf-8"))["processed"]


def test_every_workspace_repo_is_checked_once_and_the_loop_ends(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
) -> None:
    """No token is not a red branch: every repo is polled, passed over, and not revisited."""
    run_env = env()
    turn = _Turn()

    result = drive_flow(FixCi(branch=BRANCH), run_env, turn)

    assert _walk(run_env) == ["api", "web"]
    assert result.status == "unavailable", result
    assert result.summary == (
        "no workspace repo left to check "
        "(no CI verdict for api: no GitHub token; web: no GitHub token)"
    ), "a repo that was never gated is named, not passed over in silence"
    assert turn.calls == [], "an unavailable verdict must never reach the owner"


def test_a_named_repo_pins_the_loop_to_that_one(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
) -> None:
    """`repo:` picks one repo and then finds it already processed, so the walk is length 1."""
    run_env = env()

    drive_flow(FixCi(repo="web", branch=BRANCH), run_env, _Turn())

    assert _walk(run_env) == ["web"]


def test_a_repo_absent_from_the_workspace_is_a_warning_not_a_failure(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    ran: Callable[..., bool],
) -> None:
    """A workspace that does not carry the named repo is a configuration difference."""
    run_env = env()

    result = drive_flow(FixCi(repo="mobile-app", branch=BRANCH), run_env, _Turn())

    assert _walk(run_env) == []
    assert ran(run_env, select_ci_repo) is True
    assert result.status == "unavailable", result
    assert result.summary == "no workspace repo left to check"


def test_no_branch_is_nothing_to_gate_on(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    ran: Callable[..., bool],
) -> None:
    """Without a branch the poll returns before it looks for a token, and the walk still runs."""
    run_env = env()

    result = drive_flow(FixCi(), run_env, _Turn())

    assert _walk(run_env) == ["api", "web"]
    assert ran(run_env, push_ci_fix) is False
    assert result.status == "unavailable", result


def test_a_red_branch_is_fixed_pushed_and_re_polled_until_it_is_green(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`poll → work → check`, once, and then the walk moves on."""
    github = _GitHub(monkeypatch, runs=[RED, GREEN])
    run_env = env()
    turn = _Turn()

    result = drive_flow(FixCi(repo="api", branch=BRANCH), run_env, turn)

    assert github.polls == 2, "the push must be followed by a fresh poll"
    assert github.pushes == [("api", BRANCH)]
    assert github.pr_refs == [BRANCH, BRANCH], "no pr_number given, both polls resolve by branch"
    assert result.status == "passed", result

    assert turn.counts() == {"fix-ci": 1}, turn.counts()
    rendered = turn.calls[0].pop("result_schema", None)
    assert rendered is not None and "fixed" in rendered, rendered
    assert turn.calls[0] == {
        "ci_branch": BRANCH,
        "ci_epic": EPIC,
        "report": "build#7(failure)",
        "operator_context": "",
    }, "the branch is the ref to check out, the epic is what the commit trailer names"
    node = turn.nodes[0]
    assert node.power == "high"
    assert node.cwd == str(workspace["api"])
    assert node.add_dirs == [
        str(workspace["docs"]), str(workspace["api"]), str(workspace["web"])
    ], "the docs root is prepended to the workspace repos"


def test_checks_that_stay_red_past_the_lap_budget_park_instead_of_failing(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spent budget is a block: the resolver escalates, and the answer resumes the owner."""
    github = _GitHub(monkeypatch, runs=[RED] * (MAX_LAPS + 1) + [GREEN])
    run_env = env()
    turn = _Turn()
    seen: list[tuple[Path, str]] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(FixCi(repo="api", branch=BRANCH), run_env, turn)

    assert result.status == "passed", result
    assert turn.counts() == {"fix-ci": MAX_LAPS + 1, "resolve-operator": 1}, turn.counts()
    assert github.polls == MAX_LAPS + 2

    ((path, gate),) = seen
    assert path == workspace["docs"] / ".agents/operator/ci-fix" / EPIC / "context.md", path
    assert (
        f"CI is still red for {BRANCH} in api after {MAX_LAPS} repair turn(s): build#7(failure)"
        in gate
    ), gate
    assert all(c["report"] == "build#7(failure)" for c in turn.calls[:MAX_LAPS]), turn.calls
    assert "CI is still red" in str(turn.calls[-1]["report"]), turn.calls[-1]
    assert OPERATOR_ANSWER in str(turn.calls[-1]["operator_context"]), turn.calls[-1]


def test_a_blocked_owner_in_human_mode_parks_and_resumes_with_the_answer(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A human operator is asked directly, and nothing is pushed before the answer."""
    github = _GitHub(monkeypatch, runs=[RED, GREEN])
    run_env = env()
    turn = _Turn("blocked", "fixed")
    seen: list[tuple[Path, str]] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(FixCi(repo="api", branch=BRANCH, operator_mode="human"), run_env, turn)

    assert result.status == "passed", result
    assert turn.counts() == {"fix-ci": 2}, "human mode skips the resolver"
    assert github.pushes == [("api", BRANCH)], "only the answered turn's work is pushed"

    ((_, gate),) = seen
    assert OWNER_NOTE in gate, gate
    first, second = turn.calls
    assert first["operator_context"] == "", first
    assert OPERATOR_ANSWER in str(second["operator_context"]), second


def test_a_push_that_does_not_land_parks_instead_of_spending_a_lap(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fix that cannot reach the remote can never turn CI green, so the run asks."""
    github = _GitHub(monkeypatch, runs=[RED, GREEN], push_ok=False)
    run_env = env()
    turn = _Turn()
    seen: list[tuple[Path, str]] = []
    fixed = _answers(seen, then=lambda: setattr(github, "push_ok", True))

    with patch.object(pyflow_park, "wait_for_answer", fixed):
        result = drive_flow(FixCi(repo="api", branch=BRANCH), run_env, turn)

    assert result.status == "passed", result
    assert turn.counts() == {"fix-ci": 2, "resolve-operator": 1}, turn.counts()
    assert github.polls == 2, "the loop must not poll again after a push that did not land"
    ((_, gate),) = seen
    assert f"Could not push the fix for {BRANCH} in api" in gate, gate


def test_each_repo_gets_its_own_lap_budget(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second repo does not inherit what the first spent, so it parks no sooner."""
    _GitHub(monkeypatch, runs=[RED, GREEN, RED, RED, RED, GREEN])
    run_env = env()
    turn = _Turn()

    result = drive_flow(FixCi(branch=BRANCH), run_env, turn)

    assert _walk(run_env) == ["api", "web"]
    assert turn.counts() == {"fix-ci": 4}, "1 for api, 3 for web"
    assert result.status == "passed", result


def test_a_run_killed_in_the_owner_turn_resumes_on_that_turn_alone(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`work` holds nothing but the agent turn, so a resume re-runs the model call and no poll."""
    github = _GitHub(monkeypatch, runs=[RED, GREEN])
    run_env = env()
    run_dir = run_env.writer.run_dir

    class _Killed(_Turn):
        def __call__(self, node: Any, ctx: Any, *a: Any, **kw: Any) -> Any:
            super().__call__(node, ctx, *a, **kw)
            raise RuntimeError("killed in the owner turn")

    with pytest.raises(RuntimeError, match="killed in the owner turn"):
        drive_flow(FixCi(repo="api", branch=BRANCH), run_env, _Killed())

    assert github.polls == 1

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "work", resume
    assert resume.flow == "FixCi", resume
    assert resume.params == {
        "loop": {
            "repo": "api",
            "repo_dir": str(workspace["api"]),
            "processed": ["api"],
            "laps": 0,
            "unread": [],
            "merging": False,
            "merges": 0,
        },
        "report": "build#7(failure)",
        "blocks": 0,
    }, resume.params

    turn = _Turn()
    result = drive_flow(FixCi(**resume.inputs), env(run_dir=run_dir), turn, resume)

    assert len(turn.calls) == 1, turn.calls
    assert github.polls == 2, "the resumed run re-enters on the owner turn, not on the poll"
    assert result.status == "passed", result


def _merging(merges: list[str], landed: dict[str, bool]) -> Any:
    """`merge_pr`, refused until something lands the branch."""

    @Blueprint("merge-test").node
    def merge_pr(
        logger: Any, epic: str = "", base_branch: str = "main", repo_dir: str = ""
    ) -> MergeOutcome:
        merges.append(epic)
        if landed["yes"]:
            return MergeOutcome(merge_status="merged", base_branch=base_branch)
        return MergeOutcome(merge_status="failed", base_branch=base_branch)

    return merge_pr


class _Resolving(_Turn):
    """The merge turn, which lands the branch whenever it reports `fixed`."""

    def __init__(self, landed: dict[str, bool], *statuses: str) -> None:
        super().__init__(*statuses)
        self.landed = landed

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        prompt, reply = super().__call__(node, ctx, *args, **kwargs)
        if reply.get("status") == "fixed":
            self.landed["yes"] = True
        return prompt, reply


def test_without_a_base_the_lane_ends_on_ci_and_merges_nothing(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`fix-ci` on its own is a CI repair, not a ship."""
    merges: list[str] = []
    monkeypatch.setattr(fix_ci_flow, "merge_pr", _merging(merges, {"yes": True}))

    result = drive_flow(FixCi(branch=BRANCH), env(), _Turn())

    assert merges == [], merges
    assert result.status == "unavailable", result


def test_the_ship_lane_merges_once_every_repo_is_read(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean merge ends the lane with no merge turn."""
    merges: list[str] = []
    monkeypatch.setattr(fix_ci_flow, "merge_pr", _merging(merges, {"yes": True}))
    turn = _Turn()

    result = drive_flow(FixCi(branch=BRANCH, base="main"), env(), turn)

    assert merges == [EPIC], merges
    assert turn.calls == [], turn.stems
    assert result.summary.startswith("merge merged"), result


def test_a_refused_merge_gets_a_merge_turn_and_ci_is_read_again_before_the_retry(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The resolution is a new head, so the lane walks every repo again before merging it."""
    merges: list[str] = []
    landed = {"yes": False}
    monkeypatch.setattr(fix_ci_flow, "merge_pr", _merging(merges, landed))
    turn = _Resolving(landed, "fixed")
    run_env = env()

    result = drive_flow(FixCi(branch=BRANCH, base="main"), run_env, turn)

    assert turn.counts()["fix-merge"] == 1, turn.stems
    assert turn.calls[0]["ci_base"] == "main", turn.calls[0]
    assert merges == [EPIC, EPIC], merges
    assert _walk(run_env) == ["api", "web"]
    assert result.summary.startswith("merge merged"), result


def test_a_merge_turn_that_cannot_decide_parks_instead_of_spending_the_budget(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One merge turn, then the operator, whose answer sends the lane back to the merge."""
    merges: list[str] = []
    landed = {"yes": False}
    monkeypatch.setattr(fix_ci_flow, "merge_pr", _merging(merges, landed))
    turn = _Turn("blocked")
    seen: list[tuple[Path, str]] = []

    def land() -> None:
        landed["yes"] = True

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen, land)):
        result = drive_flow(FixCi(branch=BRANCH, base="main"), env(), turn)

    assert turn.counts()["fix-merge"] == 1, turn.stems
    assert merges == [EPIC, EPIC], merges
    assert len(seen) == 1, seen
    assert OWNER_NOTE in seen[0][1], seen[0][1]
    assert result.summary.startswith("merge merged"), result
