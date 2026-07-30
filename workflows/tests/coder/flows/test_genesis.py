"""End-to-end drives of the genesis flow (`coder/flows/genesis.py`).

Genesis is the flow with the least to stub: `resolve_genesis_target`, `genesis_git_init`,
`write_agents_yml`, `init_skeleton` and `validate_genesis` all run for real against a temp
directory, and the skeleton step runs a real shell command. The one seam is
`nodes.genesis._run` — the `farrier` CLI, which is not installed in a test — and the fake
below does what farrier does rather than only reporting success: `install` writes
`.agents/agents-context.json`, and each scaffold seeds the directory it names. Everything
`validate_genesis` then asserts is a file some step actually produced.

What is under test that the port could get wrong:

* the two skip-ahead branches at the front, which are the whole of `decide_target` and
  `decide_skeleton` — and they must be separate, because an established repo is exactly
  where a new service gets added;
* the bounded repair loop at the back, whose budget is a state parameter now rather than a
  var seeded in `vars:` and a literal re-typed inside the guard;
* the state named `verify`, which is the name collision the port hit — a state called
  `validate` is silently not a state, so a run that reaches this terminal at all is the
  regression test for it;
* resume, which under the YAML re-entered on the node and here re-enters on the state
  holding nothing but the agent turn.
"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.flows.genesis import Genesis
from workhorse_workflows.coder.nodes import genesis as genesis_nodes
from workhorse_workflows.coder.schemas.genesis import GenesisReport

#: The stack-shaped inputs. Genesis carries none of this knowledge itself — every value
#: here is written through verbatim, which is what `scripts/check_public.py` asserts.
PARAMS = {
    "service": "api",
    "service_root": "api",
    "packs": "go-service",
    "scaffolds": "shared-docs:docs,go-service:api",
    # A real command, run for real by `init_skeleton`. Standing in for `go mod init`,
    # which is the one thing about it that would need a toolchain installed.
    "init_cmd": "printf 'module example.com/api\\n' > go.mod",
    "marker": "go.mod",
    "markers": "go.mod",
}


# --------------------------------------------------------------------------- fixtures


class _Farrier:
    """`farrier`, as the flow uses it: install renders the context, scaffolds seed dirs.

    Recording the calls matters as much as faking them — `write_agents_yml` has to have
    declared the scaffold ids before `farrier scaffold` is reached, because the real CLI
    refuses an id that is not enabled in `agents.yml`, and that ordering is invisible in
    the flow's result.
    """

    def __init__(self, *, install_ok: bool = True, seed_docs: bool = True) -> None:
        self.install_ok = install_ok
        self.seed_docs = seed_docs
        self.calls: list[list[str]] = []

    def __call__(
        self, args: list[str], cwd: Path, timeout: int = 300
    ) -> subprocess.CompletedProcess:
        self.calls.append(list(args))
        target = Path(args[args.index("--repo") + 1])
        if args[1] == "install":
            if not self.install_ok:
                return subprocess.CompletedProcess(args, 1, "", "no packs resolved")
            ctx = target / ".agents" / "agents-context.json"
            ctx.parent.mkdir(parents=True, exist_ok=True)
            ctx.write_text(json.dumps({"instructions": {"api": ["go-service.md"]}}))
        else:
            scaffold_id = args[2]
            param = next((a for a in args if a.startswith("dir=")), "dir=.")
            seeded = target / param.removeprefix("dir=")
            seeded.mkdir(parents=True, exist_ok=True)
            (seeded / ".gitignore").write_text("/tmp\n")
            if scaffold_id == "shared-docs" and self.seed_docs:
                (target / "docs" / "epics").mkdir(parents=True, exist_ok=True)
                (target / "docs" / "backlog.md").write_text("# Backlog\n")
        return subprocess.CompletedProcess(args, 0, "", "")


class _Turn:
    """A scripted genesis agent turn: the conventions pass, and the repair pass.

    `repairs` is what a fix turn writes on its Nth call — a mapping of call index to the
    files it lands. That is the honest shape: nothing branches on a fix reply, and only
    the next `verify` decides whether the repair worked.
    """

    def __init__(self, *, repairs: dict[int, dict[str, str]] | None = None) -> None:
        self.repairs = repairs or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.nodes: list[Any] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        data = ctx.as_dict()
        self.calls.append((node.id, data))
        self.nodes.append(node)
        if node.id == "fix-genesis":
            for rel, text in self.repairs.get(self.count("fix-genesis") - 1, {}).items():
                path = Path(data["target_dir"]) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        return f"(scripted) {node.prompt}", {"status": "done", "notes": "ok"}

    def count(self, node_id: str) -> int:
        return sum(1 for name, _ in self.calls if name == node_id)

    def args(self, node_id: str) -> dict[str, Any]:
        return next(data for name, data in self.calls if name == node_id)


@pytest.fixture
def farrier(monkeypatch: pytest.MonkeyPatch) -> _Farrier:
    fake = _Farrier()
    monkeypatch.setattr(genesis_nodes, "_run", fake)
    return fake


@pytest.fixture
def target(tmp_path: Path) -> Path:
    """Where genesis will build. Deliberately absent — that is the `absent` arm."""
    return tmp_path / "greenfield"


@pytest.fixture
def existing(
    tmp_path: Path, git: Callable[..., subprocess.CompletedProcess]
) -> Path:
    """A repo that has already been through genesis once, with a commented `agents.yml`.

    The comment is the assertion: `write_agents_yml` merges through ruamel's round-trip
    mode precisely so a mature repo's rationale survives a config refresh, and a
    safe_load/safe_dump port would pass every other check in this module.
    """
    root = tmp_path / "monorepo"
    root.mkdir()
    (root / "agents.yml").write_text(
        "repo:\n"
        "  name: monorepo\n"
        "# the web service owns 5173; do not add a second one here\n"
        "packs:\n"
        "  - shared-docs\n",
        encoding="utf-8",
    )
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "Initial commit")
    return root


def _run(
    drive_flow: Callable[..., Any],
    run_env: RunEnv,
    turn: _Turn,
    target: Path,
    **overrides: Any,
) -> Any:
    return drive_flow(Genesis(target=str(target), **{**PARAMS, **overrides}), run_env, turn)


# ------------------------------------------------------------------- the happy path


def test_a_bare_directory_becomes_a_repo_the_main_loop_will_accept(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], farrier: _Farrier, target: Path
) -> None:
    """One pass through every state, ending on a validator that has nothing to report.

    The postconditions asserted here are not this flow's invention: `validate_genesis`
    shares `contract.service_problems` with the main graph's `validate_plan_context`, so
    the terminal being `valid` is the same claim the planner makes when it accepts a
    service.
    """
    run_env = env()
    turn = _Turn()
    result = _run(drive_flow, run_env, turn, target)

    assert isinstance(result, GenesisReport), result
    assert result.valid is True, result.errors
    # Advisory only — genesis does not write a Makefile, and the lint gate degrades to a
    # skip rather than a failure without one.
    assert "lint" in result.warnings, result.warnings

    assert (target / ".git").is_dir()
    assert (target / "api" / "go.mod").read_text() == "module example.com/api\n"
    assert (target / "docs" / "epics").is_dir()
    assert (target / "docs" / "backlog.md").is_file()
    assert json.loads((target / ".agents" / "agents-context.json").read_text())["instructions"]

    # `git init` landed a commit, not just a `.git` — an unborn HEAD has nothing for
    # `branch_author` to point a branch at.
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target, capture_output=True,
                          text=True, check=True)
    assert head.stdout.strip()

    # One conventions turn, no repair turn: the repo was valid the first time it was asked.
    assert turn.count("apply-genesis-conventions") == 1, turn.calls
    assert turn.count("fix-genesis") == 0, turn.calls


def test_agents_yml_carries_the_workspace_block_the_planner_reads(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], farrier: _Farrier, target: Path
) -> None:
    """`workspace:` is what makes the service targetable at all, and `scaffolds:` is what
    lets `farrier scaffold` render anything — the CLI refuses an id the file has not
    enabled, so a port that wrote it after the farrier step would render nothing."""
    _run(drive_flow, env(), _Turn(), target)

    data = YAML(typ="safe").load(target / "agents.yml")
    assert data["repo"]["name"] == "greenfield", data
    assert data["workspace"]["service_roots"] == ["api"], data
    assert data["workspace"]["service_markers"] == ["go.mod"], data
    assert data["scaffolds"] == ["shared-docs", "go-service"], data
    assert data["packs"] == ["go-service"], data
    # `farrier install` hard-exits with "No agents selected in config" without this key.
    assert data["agents"] == {"claude": True, "codex": False, "copilot": False}, data

    # And it was written before farrier ran, which is the ordering the CLI requires.
    assert [c[1] for c in farrier.calls] == ["install", "scaffold", "scaffold"], farrier.calls


def test_the_conventions_turn_runs_in_the_new_repo_and_is_told_where_the_marker_is(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], farrier: _Farrier, target: Path
) -> None:
    """`cwd` decides whose `CLAUDE.md` and whose skills the turn sees, and `marker_path`
    is how it finds the service it is making conventional. Both were `args:` on the YAML
    node; a port that dropped `cwd` would run the turn wherever the engine happened to
    be, which for an installed package is the site-packages directory."""
    turn = _Turn()
    _run(drive_flow, env(), turn, target)

    args = turn.args("apply-genesis-conventions")
    assert args["target_dir"] == str(target.resolve()), args
    assert args["service_root"] == "api", args
    assert args["marker_path"] == "api/go.mod", args
    conventions = next(n for n in turn.nodes if n.id == "apply-genesis-conventions")
    assert conventions.cwd == str(target.resolve()), conventions.cwd


# -------------------------------------------------------------------- the two skips


def test_an_existing_repo_skips_git_init_but_still_builds_the_new_service(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    farrier: _Farrier,
    existing: Path,
    ran: Callable[..., bool],
) -> None:
    """The two decisions are keyed on different things, and this is why.

    A monorepo grows one service at a time, so `target_state: existing` must skip only
    `git init` — keying the skeleton step on the repo would mean the second service in a
    monorepo could never be created. `service_state` is what gates the build, and here it
    is `absent` because `api/go.mod` does not exist yet.
    """
    run_env = env()
    result = _run(drive_flow, run_env, _Turn(), existing)

    assert result.valid is True, result.errors
    assert not ran(run_env, genesis_nodes.genesis_git_init), "git_init ran on an existing repo"
    # The service was still built, which is the half that must not be skipped.
    assert (existing / "api" / "go.mod").is_file()

    merged = (existing / "agents.yml").read_text()
    assert "# the web service owns 5173" in merged, merged
    assert "- shared-docs" in merged and "- go-service" in merged, merged


def test_an_existing_service_skips_the_skeleton_and_never_re_runs_the_init_command(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    farrier: _Farrier,
    existing: Path,
    ran: Callable[..., bool],
) -> None:
    """`go mod init` and friends fail or clobber when re-run over a live service, so a
    service whose marker is already there routes straight to the farrier refresh.

    The conventions turn is skipped with it: `_skeleton_ok()` reads a node that never ran
    and returns False, which is the same `default:` arm the YAML's `decide_skeleton_ok`
    took when `skeleton_ok` was undefined. Conventions are not re-applied to a live
    service.
    """
    (existing / "api").mkdir()
    (existing / "api" / "go.mod").write_text("module example.com/api\n")
    run_env = env()
    turn = _Turn()

    result = _run(drive_flow, run_env, turn, existing, init_cmd="exit 17")

    assert result.valid is True, result.errors
    assert not ran(run_env, genesis_nodes.init_skeleton), "the skeleton ran over a live service"
    assert turn.count("apply-genesis-conventions") == 0, turn.calls


def test_a_blank_target_fails_before_anything_mutates(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], farrier: _Farrier
) -> None:
    """The YAML let a blank target run the whole flow: every script no-opped with a note
    and the run still reached the conventions agent, burning a model call to discover
    there was nothing there. The failure carries the script's own remediation sentence."""
    turn = _Turn()

    with pytest.raises(WorkflowFailed, match="no target directory was provided"):
        drive_flow(Genesis(**PARAMS), env(), turn)

    assert turn.calls == [], turn.calls
    assert farrier.calls == [], farrier.calls


# ------------------------------------------------------------- the repair loop


def test_an_invalid_repo_is_repaired_and_re_validated(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fix turn's reply is not branched on — `verify` running again is what decides.

    So a repair that actually lands the missing file ends the loop, and the evidence is
    the second validation passing rather than the agent saying it fixed something.
    """
    monkeypatch.setattr(genesis_nodes, "_run", _Farrier(seed_docs=False))
    turn = _Turn(repairs={0: {"docs/backlog.md": "# Backlog\n", "docs/epics/.keep": ""}})

    result = _run(drive_flow, env(), turn, target)

    assert result.valid is True, result.errors
    assert turn.count("fix-genesis") == 1, turn.calls
    # The repair turn is handed the validator's own words, not a generic "it failed".
    assert "docs/backlog.md" in turn.args("fix-genesis")["genesis_errors"]


def test_a_repo_that_stays_invalid_fails_after_two_repair_rounds(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`MAX_REWORKS` is the literal `"2"` `guard_genesis` compared against, and the
    counter is a state parameter rather than the YAML's seeded var.

    The YAML's `genesis_failed` terminal ended the run with "reached genesis_failed" and
    the reason only in a log line; the raise carries the validator's errors.
    """
    monkeypatch.setattr(genesis_nodes, "_run", _Farrier(seed_docs=False))
    turn = _Turn()

    with pytest.raises(WorkflowFailed) as exc:
        _run(drive_flow, env(), turn, target)

    assert "still invalid after 2 repair round(s)" in str(exc.value), exc.value
    assert "docs/backlog.md" in str(exc.value), exc.value
    assert turn.count("fix-genesis") == 2, turn.calls


def test_a_failed_farrier_install_skips_the_conventions_turn(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """There is nothing for a conventions turn to be conventional *about* without the
    skills farrier installs, so the flow routes straight to the validator — which then
    reports the missing context file as an error rather than the turn inventing one."""
    monkeypatch.setattr(genesis_nodes, "_run", _Farrier(install_ok=False))
    turn = _Turn()

    with pytest.raises(WorkflowFailed) as exc:
        _run(drive_flow, env(), turn, target)

    assert turn.count("apply-genesis-conventions") == 0, turn.calls
    assert "agents-context.json" in str(exc.value), exc.value


# ------------------------------------------------------------------------- resume


def test_a_run_killed_in_the_repair_turn_resumes_on_that_turn_alone(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The checkpoint is written before a state runs, and `fix` holds nothing but the
    agent turn — so a resume re-runs the model call and not the build beneath it.

    `reworks` riding on the checkpoint as a state parameter is what makes the resumed run
    finish the loop with the same budget spent, which is what the YAML's
    `genesis_rework_count` var was reaching for.
    """
    monkeypatch.setattr(genesis_nodes, "_run", _Farrier(seed_docs=False))

    class _Killed(_Turn):
        def __call__(self, node: Any, ctx: Any, *a: Any, **kw: Any) -> Any:
            if node.id == "fix-genesis":
                raise RuntimeError("killed while repairing")
            return super().__call__(node, ctx, *a, **kw)

    run_env = env()
    run_dir = run_env.writer.run_dir
    with pytest.raises(RuntimeError, match="killed while repairing"):
        _run(drive_flow, run_env, _Killed(), target)

    checkpoint = json.loads((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "fix", resume
    assert resume.params == {"reworks": 0}, resume.params
    assert resume.flow == "Genesis", resume

    # Farrier is not re-run: the resume re-enters on `fix`, so `docs/backlog.md` is still
    # missing and the repair turn is the only thing that can land it.
    turn = _Turn(repairs={0: {"docs/backlog.md": "# Backlog\n", "docs/epics/.keep": ""}})
    result = drive_flow(
        Genesis(**resume.inputs), env(run_dir=run_dir), turn, resume
    )

    assert result.valid is True, result.errors
    # The build did not run again: no conventions turn, and only the interrupted repair.
    assert turn.count("apply-genesis-conventions") == 0, turn.calls
    assert turn.count("fix-genesis") == 1, turn.calls
