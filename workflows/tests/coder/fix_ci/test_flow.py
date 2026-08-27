"""End-to-end tests for the `fix_ci` flow — the two loops, and where each one stops.

Eleven YAML nodes became four states holding two loops that share them: `poll → start` is
the outer one advancing to the next workspace repo, and `push → poll` is the inner one
re-reading CI after a fix. What is worth testing is exactly that — which arm a verdict
takes, and what makes each loop terminate — so the tests are organised by loop rather than
by node.

Two seam levels, deliberately:

* the **outer** loop runs with no seams at all beyond the agent that never gets called. A
  run with no GitHub token reports `unavailable` at the first guard in `poll_pr_checks`,
  which is the pass-through arm, so the whole walk over the workspace happens with the real
  nodes and no network.
* the **inner** loop scripts the four calls that would leave the machine —
  `resolve_github_token`, `origin_url`/`resolve_repo`/`_resolve_pr`, `_poll_runs` and
  `push_branch`. Everything between them is real: the branch guard, `_watch`'s settle loop
  and the summary it builds, `push_epic_branch`'s own `branch_exists` check on a real
  branch in a real repo.

The walk order is read off `select_ci_repo`'s recorded output rather than a spy: its
`processed` accumulator grows by one repo per pass, so the final pick carries the whole
walk. A skipped repo is invisible in the flow's result and visible there.
"""
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

#: One settled Actions run set, as `_poll_runs` reports it: `(total, pending, failed,
#: names)`. `_watch` turns the first into `failed` with the names as its summary — which is
#: the brief the fixer is handed — and the second into `passed`.
RED = (1, 0, 1, "build#7(failure)")
GREEN = (1, 0, 0, "")


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _no_ambient_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """No GitHub token from the developer's own shell.

    `resolve_github_token` falls back to `GH_TOKEN` and `GITHUB_TOKEN` after the env var
    named in `agents.yml`, so a maintainer with either exported would have the outer-loop
    tests reach for the network instead of taking the `unavailable` pass-through they are
    written to exercise.
    """
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
    """Two real repos and the VSCode workspace file that names them, in order.

    `resolve_workspace` reads the file the run's `workspace_file` input names and
    resolves each folder path relative to it, so the paths here are relative as a checked-in
    `.code-workspace` carries them. The `repo` fixture's own checkout stays out of the
    workspace: it is the docs root, and the flow prepends it separately.
    """
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
    """The scripted fixer turn.

    It reports `fixed` by default and nothing in the flow believes it — the next poll is
    what decides. `status="blocked"` is the one claim the flow does act on, because it is
    the one the next poll cannot check.
    """

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
    """The GitHub boundary, scripted at its four exits, and recording what crossed them.

    `runs` is one `_poll_runs` reply per poll; the last repeats, so a loop that polls more
    often than the script anticipated keeps the final verdict rather than running out. The
    settle logic, the summary and the whole guard chain above it stay real.
    """

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


# ------------------------------------------------------------------- the outer loop


def test_every_workspace_repo_is_checked_once_and_the_loop_ends(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
) -> None:
    """No token is not a red branch: every repo is polled, passed over, and not revisited.

    This is the whole outer loop with no seams — `poll_pr_checks` reports `unavailable` at
    its token guard, `poll` routes that with `passed`, and `start` runs out of repos. What
    terminates it is `processed`, which is why the walk is asserted rather than the count.
    """
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
    """A workspace that does not carry the named repo is a configuration difference.

    The run finishes clean and nothing is polled — `unavailable` here means "never got as
    far as looking", which is what `_finish` reports when no poll ever ran.
    """
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
    """Without a branch the poll returns before it looks for a token, and the walk still runs.

    The flow is reachable standalone (`workhorse-coder run fix_ci`), so a missing branch is
    an ordinary input, not a programming error.
    """
    run_env = env()

    result = drive_flow(FixCi(), run_env, _Turn())

    assert _walk(run_env) == ["api", "web"]
    assert ran(run_env, push_ci_fix) is False
    assert result.status == "unavailable", result


# ------------------------------------------------------------------- the inner loop


def test_a_red_branch_is_fixed_pushed_and_re_polled_until_it_is_green(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`poll → fix → push → poll`, once, and then the outer loop resumes.

    Three things the states are responsible for are asserted here rather than in the nodes:
    the fixer runs with the *picked* repo as its cwd (which is what lets workhorse resolve
    `<repo>/.agents/flavors/coder/fix-ci.md`), it may read the whole workspace plus the docs
    root, and the brief it is handed is the summary the poll just produced.
    """
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
    # `result_schema` is the rendered output contract every role turn carries; the three
    # arguments below are this lane's own.
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
    """Three fixes, four polls, and then `poll` gives up rather than cycling forever.

    The guard is on entry to the fixer, so the run ends on a *poll* — the verdict reported
    is one the loop actually read, not the last one it tried to repair.
    """
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
    """`blocked` spends one attempt, not three, and never reaches the push.

    The budget's own exhaustion arm ends the loop on a red branch already; what this adds
    is ending there without first re-asking a turn that has answered. The branch is left
    red for the epic gate above, and the fixer's reason is what the run record carries —
    a summary saying "still red after 3 attempts" would say nothing about why.
    """
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
    """A fix that cannot reach the remote can never turn CI green.

    `push_branch` verifies the remote head, so a `failed` here is "attempted and did not
    land" — polling an unmoved PR head again would only burn the budget.
    """
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
    """The second repo inherits what the first spent — the YAML's behavior, not its comment.

    `api` needs one fix to go green, so `web` reaches its own poll with the counter already
    at 1 and gets two fixes instead of three. The YAML calls `ci_attempts` a per-repo budget
    and never resets it when `select_ci_repo` advances; the pinned behaviour is lifetime,
    and `CiLoop.attempts` says so.
    """
    _GitHub(monkeypatch, runs=[RED, GREEN, RED, RED, RED])
    run_env = env()
    turn = _Turn()

    result = drive_flow(FixCi(branch=BRANCH), run_env, turn)

    assert _walk(run_env) == ["api", "web"]
    assert len(turn.calls) == 3, "1 for api + 2 for web, not 1 + 3"
    assert result.summary == (
        f"CI still red for {BRANCH} in web after 3 attempt(s): build#7(failure)"
    )


# ------------------------------------------------------------------------- resume


def test_a_run_killed_in_the_fixer_resumes_on_that_turn_alone(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`fix` holds nothing but the agent turn, so a resume re-runs the model call and no poll.

    The counters ride on the checkpoint as state parameters, which is what `processed_repos`
    and `ci_attempts` were reaching for as JSON-encoded workflow vars, carried as one
    `CiLoop` value — and `setup`'s
    workspace is carried in the resumed context rather than re-derived.
    """
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
