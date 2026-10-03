"""`workhorse-new`: the files it writes, and the workflow those files run."""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from _fakes import StubRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv, stub_nodes

from workhorse_workflows.new import scaffold

WORKFLOWS_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

CHECK = (
    f'"{sys.executable}" -c "import pathlib, sys; '
    f"fixed = pathlib.Path('fixed').exists(); "
    f"print('still broken', file=sys.stderr) if not fixed else None; "
    f'sys.exit(0 if fixed else 3)"'
)


class _Agent:
    """An agent turn that writes `fixed` into the repo on the turn numbered `fixes_on`."""

    def __init__(self, repo: Path, fixes_on: int | None) -> None:
        self.repo = repo
        self.fixes_on = fixes_on
        self.args: list[dict[str, Any]] = []

    def __call__(self, node: Any, ctx: Any, *_args: Any, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
        assert node.id == "fix", node.id
        self.args.append(ctx.as_dict())
        if len(self.args) == self.fixes_on:
            (self.repo / "fixed").write_text("yes\n")
        return "(scripted)", {"summary": f"turn {len(self.args)}"}


def _workhorse_agent_floor() -> str:
    data = tomllib.loads(WORKFLOWS_PYPROJECT.read_text(encoding="utf-8"))
    return next(dep for dep in data["project"]["dependencies"] if dep.startswith("workhorse-agent"))


@pytest.fixture
def generated(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[tuple[Path, ModuleType]]:
    """A scaffolded workflow, named for the test, with its `workflow` module imported."""
    name = "scaffolded-" + request.node.name.removeprefix("test_").replace("_", "-")
    package = scaffold.package_name(name)
    target = scaffold.scaffold(name, CHECK, tmp_path)
    sys.path.insert(0, str(target / "src"))
    importlib.invalidate_caches()
    try:
        yield target, importlib.import_module(f"{package}.workflow")
    finally:
        sys.path.remove(str(target / "src"))
        for module in [m for m in sys.modules if m == package or m.startswith(f"{package}.")]:
            del sys.modules[module]


def _env(module: ModuleType, root: Path, agent: Any, *, dry_run: bool = False) -> RunEnv:
    registry = module.workflow
    writer = ArtifactWriter(registry.name, root / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(module.__file__ or "").parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        agent_runner=StubRunner(agent),
        nodes=stub_nodes(registry.nodes) if dry_run else registry.nodes,
        dry_run=dry_run,
        agent_stubs=registry.agent_stubs if dry_run else None,
    )


def _repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    return repo


def test_scaffold_writes_a_standalone_distribution(tmp_path: Path) -> None:
    target = scaffold.scaffold("fix-tests", "pytest -q", tmp_path)

    assert target == tmp_path / "fix-tests"
    files = sorted(str(p.relative_to(target)) for p in target.rglob("*") if p.is_file())
    assert files == [
        "README.md",
        "pyproject.toml",
        "src/fix_tests/__init__.py",
        "src/fix_tests/prompts/fix.md",
        "src/fix_tests/workflow.py",
    ]
    project = tomllib.loads((target / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "fix-tests"
    assert project["dependencies"] == [_workhorse_agent_floor()]
    assert project["scripts"] == {"workhorse-fix-tests": "fix_tests.workflow:main"}
    workflow = (target / "src/fix_tests/workflow.py").read_text(encoding="utf-8")
    assert 'check: str = "pytest -q"' in workflow
    assert 'Registry("fix-tests", package=__package__)' in workflow
    assert "__" + "CHECK__" not in workflow
    assert "`pytest -q`" in (target / "README.md").read_text(encoding="utf-8")


def test_scaffold_quotes_a_check_with_quotes_in_it(tmp_path: Path) -> None:
    target = scaffold.scaffold("quoted", 'pytest -k "not slow" && echo \\done', tmp_path)

    source = (target / "src/quoted/workflow.py").read_text(encoding="utf-8")
    compile(source, "workflow.py", "exec")
    assert 'check: str = "pytest -k \\"not slow\\" && echo \\\\done"' in source


def test_scaffold_refuses_an_existing_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "fix-tests").mkdir()

    code = scaffold.main(["fix-tests", "--check", "pytest", "--into", str(tmp_path)])

    assert code == 1
    assert "already exists" in capsys.readouterr().err
    assert list((tmp_path / "fix-tests").iterdir()) == []


def test_the_install_hint_names_a_path_not_a_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    code = scaffold.main(["fix-tests", "--check", "pytest"])

    assert code == 0
    assert "uv tool install ./fix-tests\n" in capsys.readouterr().out
    assert (tmp_path / "fix-tests" / "pyproject.toml").is_file()


@pytest.mark.parametrize("name", ["Fix", "fix_tests", "-fix", "fix--tests", "9fix"])
def test_scaffold_refuses_a_name_that_is_not_a_command(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="not a workflow name"):
        scaffold.scaffold(name, "pytest", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_check_that_fails_once_loops_back_exactly_once(
    tmp_path: Path, generated: tuple[Path, ModuleType]
) -> None:
    _, module = generated
    repo = _repo(tmp_path)
    agent = _Agent(repo, fixes_on=2)

    result = drive(module.CheckLoop(repo_dir=str(repo)), _env(module, tmp_path, agent))

    assert result.passed
    assert len(agent.args) == 2
    first, second = agent.args
    assert first["failure"] == ""
    assert first["attempt"] == 1
    assert "still broken" in second["failure"]
    assert second["attempt"] == 2


def test_the_round_bound_fails_the_run(tmp_path: Path, generated: tuple[Path, ModuleType]) -> None:
    _, module = generated
    repo = _repo(tmp_path)
    agent = _Agent(repo, fixes_on=None)

    with pytest.raises(WorkflowFailed, match="after 3 rounds") as failed:
        drive(module.CheckLoop(repo_dir=str(repo), max_rounds=3), _env(module, tmp_path, agent))

    assert len(agent.args) == 3
    assert "still broken" in str(failed.value)


def test_the_check_output_is_cut_to_its_tail(generated: tuple[Path, ModuleType]) -> None:
    _, module = generated

    cut = module.truncated("a" * 50 + "the end", limit=7)

    assert cut == "[50 earlier characters cut]\nthe end"
    assert module.truncated("short", limit=7) == "short"


def test_the_dry_run_completes_with_no_agent(tmp_path: Path, generated: tuple[Path, ModuleType]) -> None:
    _, module = generated

    def no_agent(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a dry run must not reach the agent")

    result = drive(
        module.CheckLoop(repo_dir=str(_repo(tmp_path))),
        _env(module, tmp_path, no_agent, dry_run=True),
    )

    assert result.passed


def test_the_command_dry_runs(tmp_path: Path, generated: tuple[Path, ModuleType]) -> None:
    target, module = generated
    repo = _repo(tmp_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(target / "src")
    env.pop("AGENT_REPO_DIR", None)
    script = f"import sys; from {module.__package__}.workflow import main; sys.exit(main())"

    done = subprocess.run(
        [sys.executable, "-c", script, "run", "--dry-run"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "dry-run ok" in done.stdout + done.stderr
