"""End-to-end tests for the `fix_ci` flow — the two loops, and where each one stops."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.fix_ci.flow import FixCi
from workhorse_workflows.coder.shared import ci as ci_nodes
from workhorse_workflows.coder.shared.ci import push_ci_fix, select_ci_repo

EPIC = "EPIC-1"
BRANCH = f"feat/{EPIC}"

RED = (1, 0, 1, "build#7(failure)")
GREEN = (1, 0, 0, "")




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
    """The scripted fixer turn."""

    def __init__(self, status: str = "fixed") -> None:
        self.status = status
        self.calls: list[dict[str, Any]] = []
        self.nodes: list[Any] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(ctx.as_dict())
        self.nodes.append(node)
        return f"(scripted) {node.prompt}", {
            "status": self.status,
            "notes": "narrowed the test",
        }


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
    assert turn.calls == [], "an unavailable verdict must never reach the fixer"


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
    """`poll → fix → push → poll`, once, and then the outer loop resumes."""
    github = _GitHub(monkeypatch, runs=[RED, GREEN])
    run_env = env()
    turn = _Turn()

    result = drive_flow(
        FixCi(repo="api", branch=BRANCH), run_env, turn
    )

    assert github.polls == 2, "the push must be followed by a fresh poll"
    assert github.pushes == [("api", BRANCH)]
    assert github.pr_refs == [BRANCH, BRANCH], "no pr_number given — both polls resolve by branch"
    assert result.status == "passed", result

    assert len(turn.calls) == 1, turn.calls
    rendered = turn.calls[0].pop("result_schema", None)
    assert rendered is not None and "fixed" in rendered, rendered
    assert turn.calls[0] == {
        "ci_branch": BRANCH,
        "ci_epic": EPIC,
        "ci_summary": "build#7(failure)",
    }, "the branch is the ref to check out; the epic is what the commit trailer names"
    node = turn.nodes[0]
    assert node.cwd == str(workspace["api"])
    assert node.add_dirs == [
        str(workspace["docs"]), str(workspace["api"]), str(workspace["web"])
    ], "the docs root is prepended to the workspace repos"


def test_the_fix_budget_is_spent_and_the_loop_reports_the_branch_still_red(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three fixes, four polls, and then `poll` gives up rather than cycling forever."""
    github = _GitHub(monkeypatch, runs=[RED])
    run_env = env()
    turn = _Turn()

    result = drive_flow(FixCi(repo="api", branch=BRANCH), run_env, turn)

    assert len(turn.calls) == FixCi.MAX_ATTEMPTS, turn.calls
    assert github.polls == FixCi.MAX_ATTEMPTS + 1
    assert result.status == "failed", result
    assert result.summary == (
        f"CI still red for {BRANCH} in api after 3 attempt(s): build#7(failure)"
    )


def test_a_fixer_that_says_it_cannot_stops_the_laps_instead_of_re_asking_it(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`blocked` spends one attempt, not three, and never reaches the push."""
    github = _GitHub(monkeypatch, runs=[RED])
    run_env = env()
    turn = _Turn(status="blocked")

    result = drive_flow(FixCi(repo="api", branch=BRANCH), run_env, turn)

    assert len(turn.calls) == 1, "a blocked turn must not be asked the same question twice"
    assert github.polls == 1, "and the loop must not poll a branch nobody pushed to"
    assert github.pushes == []
    assert result.status == "failed", result
    assert result.summary == (
        f"the CI fixer reported it cannot make {BRANCH} green in api: narrowed the test"
    )


def test_a_push_that_does_not_land_ends_the_loop_instead_of_spending_an_attempt(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fix that cannot reach the remote can never turn CI green."""
    github = _GitHub(monkeypatch, runs=[RED], push_ok=False)
    run_env = env()
    turn = _Turn()

    result = drive_flow(FixCi(repo="api", branch=BRANCH), run_env, turn)

    assert len(turn.calls) == 1, turn.calls
    assert github.polls == 1, "the loop must not poll again after a push that did not land"
    assert result.status == "failed", result
    assert result.summary == f"could not push the fix for {BRANCH} in api"


def test_the_attempt_budget_is_shared_across_repos_not_reset_per_repo(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second repo inherits what the first spent — the YAML's behavior, not its comment."""
    _GitHub(monkeypatch, runs=[RED, GREEN, RED, RED, RED])
    run_env = env()
    turn = _Turn()

    result = drive_flow(FixCi(branch=BRANCH), run_env, turn)

    assert _walk(run_env) == ["api", "web"]
    assert len(turn.calls) == 3, "1 for api + 2 for web, not 1 + 3"
    assert result.summary == (
        f"CI still red for {BRANCH} in web after 3 attempt(s): build#7(failure)"
    )




def test_a_run_killed_in_the_fixer_resumes_on_that_turn_alone(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`fix` holds nothing but the agent turn, so a resume re-runs the model call and no poll."""
    github = _GitHub(monkeypatch, runs=[RED, GREEN])
    run_env = env()
    run_dir = run_env.writer.run_dir

    class _Killed(_Turn):
        def __call__(self, node: Any, ctx: Any, *a: Any, **kw: Any) -> Any:
            super().__call__(node, ctx, *a, **kw)
            raise RuntimeError("killed while fixing")

    with pytest.raises(RuntimeError, match="killed while fixing"):
        drive_flow(FixCi(repo="api", branch=BRANCH), run_env, _Killed())

    assert github.polls == 1

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "fix", resume
    assert resume.flow == "FixCi", resume
    assert resume.params == {
        "loop": {
            "repo": "api",
            "repo_dir": str(workspace["api"]),
            "processed": ["api"],
            "attempts": 0,
            "unread": [],
        },
        "summary": "build#7(failure)",
    }, resume.params

    turn = _Turn()
    result = drive_flow(FixCi(**resume.inputs), env(run_dir=run_dir), turn, resume)

    assert len(turn.calls) == 1, turn.calls
    assert github.polls == 2, "the resumed run re-enters on the fixer, not on the poll"
    assert result.status == "passed", result
