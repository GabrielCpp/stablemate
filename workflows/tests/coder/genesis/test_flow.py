"""End-to-end drives of the genesis flow (`coder/genesis/flow.py`).

Genesis is the flow with the least to stub: `resolve_genesis_target`, `genesis_git_init`,
`write_agents_yml`, `init_skeleton` and `validate_genesis` all run for real against a temp
directory, and the skeleton step runs a real shell command. The one seam is
`nodes.genesis._run` — the `farrier` CLI, which is not installed in a test — and the fake
below does what farrier does rather than only reporting success: `install` writes
`.agents/agents-context.json`, and each scaffold seeds the directory it names. Everything
`validate_genesis` then asserts is a file some step actually produced.

Genesis is pure bootstrapping — there is no agent turn anywhere in the flow, and `_NoAgent`
below is the proof: any call into it fails the test loudly rather than a scripted reply
silently standing in for a turn that should not exist.

What is under test that the port could get wrong:

* the two skip-ahead branches at the front, which are the whole of `decide_target` and
  `decide_skeleton` — and they must be separate, because an established repo is exactly
  where a new service gets added;
* an invalid target fails the run directly, with no repair turn to mask it;
* the state named `verify`, which is the name collision the port hit — a state called
  `validate` is silently not a state, so a run that reaches this terminal at all is the
  regression test for it;
* resume, re-entering on whichever state the run was killed in.
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
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.genesis.flow import Genesis
from workhorse_workflows.coder.genesis import nodes as genesis_nodes
from workhorse_workflows.coder.shared.schemas.genesis import GenesisReport

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


class _NoAgent:
    """Genesis is pure bootstrapping — any call into this fails the test.

    Standing in for the scripted `_Turn` fakes other flows use: there is nothing left to
    script, and a test that drives genesis into an agent call has regressed the "at most
    name attribution, and nothing has needed even that yet" boundary this flow keeps.
    """

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"genesis must never call an agent, but reached {node.id!r}")


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
    target: Path,
    **overrides: Any,
) -> Any:
    return drive_flow(
        Genesis(target=str(target), **{**PARAMS, **overrides}), run_env, _NoAgent()
    )


# ------------------------------------------------------------------- the happy path


def test_a_bare_directory_becomes_a_repo_the_main_loop_will_accept(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], farrier: _Farrier, target: Path
) -> None:
    """One pass through every state, ending on a validator that has nothing to report.

    The postconditions asserted here are not this flow's invention: `validate_genesis`
    shares `contract.service_problems` with the main graph's `record_plan`, so
    the terminal being `valid` is the same claim the planner makes when it accepts a
    service.
    """
    run_env = env()
    result = _run(drive_flow, run_env, target)

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


def test_agents_yml_carries_the_workspace_block_the_planner_reads(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], farrier: _Farrier, target: Path
) -> None:
    """`workspace:` is what makes the service targetable at all, and `scaffolds:` is what
    lets `farrier scaffold` render anything — the CLI refuses an id the file has not
    enabled, so a port that wrote it after the farrier step would render nothing."""
    _run(drive_flow, env(), target)

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
    result = _run(drive_flow, run_env, existing)

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
    service whose marker is already there routes straight to the farrier refresh."""
    (existing / "api").mkdir()
    (existing / "api" / "go.mod").write_text("module example.com/api\n")
    run_env = env()

    result = _run(drive_flow, run_env, existing, init_cmd="exit 17")

    assert result.valid is True, result.errors
    assert not ran(run_env, genesis_nodes.init_skeleton), "the skeleton ran over a live service"


def test_a_blank_target_fails_before_anything_mutates(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], farrier: _Farrier
) -> None:
    """The YAML let a blank target run the whole flow: every script no-opped with a note
    and the run still reached the conventions agent, burning a model call to discover
    there was nothing there. The failure carries the script's own remediation sentence."""
    with pytest.raises(WorkflowFailed, match="no target directory was provided"):
        drive_flow(Genesis(**PARAMS), env(), _NoAgent())

    assert farrier.calls == [], farrier.calls


# ------------------------------------------------------------- invalid targets fail


def test_an_invalid_repo_fails_the_run_with_no_repair_turn(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Genesis is pure bootstrapping: an invalid target fails the run directly, carrying
    the validator's own words, rather than handing the errors to a repair turn that could
    only guess at a tooling failure the tool itself already reported."""
    monkeypatch.setattr(genesis_nodes, "_run", _Farrier(seed_docs=False))

    with pytest.raises(WorkflowFailed) as exc:
        _run(drive_flow, env(), target)

    assert "genesis target is invalid" in str(exc.value), exc.value
    assert "docs/backlog.md" in str(exc.value), exc.value


def test_a_failed_farrier_install_still_fails_at_verify(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed install leaves no skills and no docs tree — the flow routes straight to
    the validator, which reports the missing context file as an error."""
    monkeypatch.setattr(genesis_nodes, "_run", _Farrier(install_ok=False))

    with pytest.raises(WorkflowFailed) as exc:
        _run(drive_flow, env(), target)

    assert "agents-context.json" in str(exc.value), exc.value


# ------------------------------------------------------------------------- resume


def test_a_run_killed_in_the_farrier_step_resumes_on_that_state_alone(
    env: Callable[..., RunEnv], drive_flow: Callable[..., Any], target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The checkpoint is written before a state runs, so a resume re-runs only the state
    it was killed in, not the build beneath it."""
    real_farrier = _Farrier()

    class _Killed:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, *a: Any, **kw: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("killed while running farrier")
            return real_farrier(*a, **kw)

    monkeypatch.setattr(genesis_nodes, "_run", _Killed())

    run_env = env()
    run_dir = run_env.writer.run_dir
    with pytest.raises(RuntimeError, match="killed while running farrier"):
        drive_flow(Genesis(target=str(target), **PARAMS), run_env, _NoAgent())

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "farrier", resume
    assert resume.flow == "Genesis", resume

    monkeypatch.setattr(genesis_nodes, "_run", real_farrier)
    result = drive_flow(
        Genesis(**resume.inputs), env(run_dir=run_dir), _NoAgent(), resume
    )

    assert result.valid is True, result.errors
