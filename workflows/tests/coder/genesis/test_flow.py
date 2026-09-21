"""End-to-end drives of the genesis flow (`coder/genesis/flow.py`)."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

import pytest
from ruamel.yaml import YAML
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.genesis.flow import Genesis
from workhorse_workflows.coder.genesis import nodes as genesis_nodes
from workhorse_workflows.coder.shared.schemas.genesis import GenesisReport

class _Params(TypedDict):
    """The shape of `PARAMS`, spelled out so `Genesis(**PARAMS)` is checked key by key."""

    service: str
    service_root: str
    packs: str
    scaffolds: str
    init_cmd: str
    marker: str
    markers: str
    gates: str


PARAMS: _Params = {
    "service": "api",
    "service_root": "api",
    "packs": "go-service",
    "scaffolds": "shared-docs:docs,go-service:api",
    "init_cmd": "printf 'module example.com/api\\n' > go.mod",
    "marker": "go.mod",
    "markers": "go.mod",
    "gates": "lint=golangci-lint run,test=go test ./...",
}




class _Farrier:
    """`farrier`, as the flow uses it: install renders the context, scaffolds seed dirs."""

    def __init__(self, *, install_ok: bool = True, seed_docs: bool = True) -> None:
        self.install_ok = install_ok
        self.seed_docs = seed_docs
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
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


class _NoAgent:
    """Genesis is pure bootstrapping — any call into this fails the test."""

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"genesis must never call an agent, but reached {node.id!r}")


@pytest.fixture
def farrier(monkeypatch: pytest.MonkeyPatch) -> _Farrier:
    fake = _Farrier()
    monkeypatch.setattr(genesis_nodes, "run_tool", fake)
    return fake


@pytest.fixture
def target(tmp_path: Path) -> Path:
    """Where genesis will build."""
    return tmp_path / "greenfield"


@pytest.fixture
def existing(
    tmp_path: Path, git: Callable[..., subprocess.CompletedProcess]
) -> Path:
    """A repo that has already been through genesis once, with a commented `agents.yml`."""
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
    target: Path,
    **overrides: Any,
) -> Any:
    return drive_flow(
        Genesis(target=str(target), **{**PARAMS, **overrides}), run_env, _NoAgent()
    )




def test_a_bare_directory_becomes_a_repo_the_main_loop_will_accept(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], farrier: _Farrier, target: Path
) -> None:
    """One pass through every state, ending on a validator that has nothing to report."""
    run_env = env()
    result = _run(drive_flow, run_env, target)

    assert isinstance(result, GenesisReport), result
    assert result.valid is True, result.errors
    assert "lint" in result.warnings, result.warnings

    assert (target / ".git").is_dir()
    assert (target / "api" / "go.mod").read_text() == "module example.com/api\n"
    assert (target / "docs" / "epics").is_dir()
    assert (target / "docs" / "backlog.md").is_file()
    assert json.loads((target / ".agents" / "agents-context.json").read_text())["instructions"]

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target, capture_output=True,
                          text=True, check=True)
    assert head.stdout.strip()


def test_agents_yml_carries_the_workspace_block_the_planner_reads(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], farrier: _Farrier, target: Path
) -> None:
    """`workspace:` is what makes the service targetable at all, and `scaffolds:` is what lets `farrier scaffold` render anything — the CLI refuses an id the file has not enabled, so a port that wrote it after the farrier step would render nothing."""
    _run(drive_flow, env(), target)

    data = YAML(typ="safe").load(target / "agents.yml")
    assert data["repo"]["name"] == "greenfield", data
    assert data["workspace"]["service_roots"] == ["api"], data
    assert data["workspace"]["service_markers"] == ["go.mod"], data
    assert data["scaffolds"] == ["shared-docs", "go-service"], data
    assert data["packs"] == ["go-service"], data
    assert data["services"] == {
        "api": {"lint": "golangci-lint run", "test": "go test ./..."}
    }, data
    assert data["agents"] == {"claude": True, "codex": False, "copilot": False}, data

    assert [c[1] for c in farrier.calls] == ["install", "scaffold", "scaffold"], farrier.calls




def test_an_existing_repo_skips_git_init_but_still_builds_the_new_service(
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    farrier: _Farrier,
    existing: Path,
    ran: Callable[..., bool],
) -> None:
    """The two decisions are keyed on different things, and this is why."""
    run_env = env()
    result = _run(drive_flow, run_env, existing)

    assert result.valid is True, result.errors
    assert not ran(run_env, genesis_nodes.genesis_git_init), "git_init ran on an existing repo"
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
    """`go mod init` and friends fail or clobber when re-run over a live service, so a service whose marker is already there routes straight to the farrier refresh."""
    (existing / "api").mkdir()
    (existing / "api" / "go.mod").write_text("module example.com/api\n")
    run_env = env()

    result = _run(drive_flow, run_env, existing, init_cmd="exit 17")

    assert result.valid is True, result.errors
    assert not ran(run_env, genesis_nodes.init_skeleton), "the skeleton ran over a live service"


def test_a_blank_target_fails_before_anything_mutates(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], farrier: _Farrier
) -> None:
    """The YAML let a blank target run the whole flow: every script no-opped with a note and the run still reached the conventions agent, burning a model call to discover there was nothing there."""
    with pytest.raises(WorkflowFailed, match="no target directory was provided"):
        drive_flow(Genesis(**PARAMS), env(), _NoAgent())

    assert farrier.calls == [], farrier.calls




def test_an_invalid_repo_fails_the_run_with_no_repair_turn(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Genesis is pure bootstrapping: an invalid target fails the run directly, carrying the validator's own words, rather than handing the errors to a repair turn that could only guess at a tooling failure the tool itself already reported."""
    monkeypatch.setattr(genesis_nodes, "run_tool", _Farrier(seed_docs=False))

    with pytest.raises(WorkflowFailed) as exc:
        _run(drive_flow, env(), target)

    assert "genesis target is invalid" in str(exc.value), exc.value
    assert "docs/backlog.md" in str(exc.value), exc.value


def test_a_failed_farrier_install_still_fails_at_verify(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed install leaves no skills and no docs tree — the flow routes straight to the validator, which reports the missing context file as an error."""
    monkeypatch.setattr(genesis_nodes, "run_tool", _Farrier(install_ok=False))

    with pytest.raises(WorkflowFailed) as exc:
        _run(drive_flow, env(), target)

    assert "agents-context.json" in str(exc.value), exc.value




def test_a_run_killed_in_the_farrier_step_resumes_on_that_state_alone(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The checkpoint is written before a state runs, so a resume re-runs only the state it was killed in, not the build beneath it."""
    real_farrier = _Farrier()

    class _Killed:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, *a: Any, **kw: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("killed while running farrier")
            return real_farrier(*a, **kw)

    monkeypatch.setattr(genesis_nodes, "run_tool", _Killed())

    run_env = env()
    run_dir = run_env.writer.run_dir
    with pytest.raises(RuntimeError, match="killed while running farrier"):
        drive_flow(Genesis(target=str(target), **PARAMS), run_env, _NoAgent())

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "farrier", resume
    assert resume.flow == "Genesis", resume

    monkeypatch.setattr(genesis_nodes, "run_tool", real_farrier)
    result = drive_flow(
        Genesis(**resume.inputs), env(run_dir=run_dir), _NoAgent(), resume
    )

    assert result.valid is True, result.errors
