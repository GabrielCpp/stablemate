"""The command line a workflow binds for itself — the only one workhorse ships.

Workhorse resolves no workflow by name: a distribution declares
``main = console_script(workflow.entry_point(Coder))`` and points ``[project.scripts]``
at it, so the object reaches the CLI directly and nothing is looked up. What is left to
test is the wiring itself, and the two properties that fail silently or late without it:

1. The script binds the workflow it was built from — every flag reaches the driver, the
   registry travels through untouched, and a bare argv means `run`.
2. A package that is not a real directory on disk (a zip import) is refused **at
   startup**, with an explanation. Left alone this surfaces as a ``TemplateNotFound``
   deep inside a run, because the prompt renderer is a filesystem template loader.

Standalone and dependency-free: the packages here are written into tmp_path and put on
``sys.path``, so nothing is installed and no network is touched.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

packaged = importlib.import_module("workhorse.packaged")
ManifestContext = importlib.import_module("workhorse.manifest").ManifestContext
cli_mod = importlib.import_module("workhorse.cli")
parser_mod = importlib.import_module("workhorse.cli.parser")
run_cmd = importlib.import_module("workhorse.cli.run")
Registry = importlib.import_module("workhorse.pyflow").Registry


#: A ``demo_flows.demo.workflow`` module holding a real `Registry` bound to a console
#: script — the shape every workflow distribution has. Written as source rather than
#: built in-process because the constraint under test is where the package lands on disk.
_WORKFLOW_MODULE = '''
from workhorse.cli import console_script
from workhorse.pyflow import Done, Registry, Workflow


class Demo(Workflow):
    def start(self):
        return Done(None)


workflow = Registry("demo")
main = console_script(workflow.entry_point(Demo))
'''


def _write_package(site: Path, module_source: str = _WORKFLOW_MODULE) -> None:
    """A minimal ``demo_flows.demo`` workflow package."""
    pkg = site / "demo_flows" / "demo"
    pkg.mkdir(parents=True)
    (site / "demo_flows" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "workflow.py").write_text(module_source)


def _write_zipped_package(tmp_path: Path) -> Path:
    archive = tmp_path / "zipped_flows.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("zipped_flows/__init__.py", "")
        zf.writestr("zipped_flows/demo/__init__.py", "")
        zf.writestr(
            "zipped_flows/demo/workflow.py", _WORKFLOW_MODULE.replace('"demo"', '"zipped"')
        )
    return archive


class _OnPath:
    """Put a directory on ``sys.path`` and take it back off, imports included."""

    def __init__(self, *paths: Path) -> None:
        self.paths = [str(p) for p in paths]

    def __enter__(self) -> _OnPath:
        for p in reversed(self.paths):
            sys.path.insert(0, p)
        importlib.invalidate_caches()
        return self

    def __exit__(self, *exc: object) -> None:
        for p in self.paths:
            if p in sys.path:
                sys.path.remove(p)
        for name in [
            n
            for n in sys.modules
            if n.split(".")[0] in ("demo_flows", "zipped_flows", "workhorse_workflows")
        ]:
            del sys.modules[name]
        importlib.invalidate_caches()


# --------------------------------------------------------------------------------
# 1. the package a registry was defined in is where its prompts are read from
# --------------------------------------------------------------------------------


def test_a_registry_resolves_to_its_own_package_directory(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    _write_package(site)

    with _OnPath(site):
        module = importlib.import_module("demo_flows.demo.workflow")
        # The workflow dir is the package the entry class's MODULE lives in, not the
        # module itself: prompts/ sits beside workflow.py.
        assert module.workflow.directory() == site / "demo_flows" / "demo"


def test_zip_imported_package_fails_at_startup(tmp_path: Path) -> None:
    """Not at TemplateNotFound time, three nodes into a run."""
    archive = _write_zipped_package(tmp_path)

    with _OnPath(archive):
        module = importlib.import_module("zipped_flows.demo.workflow")
        # The module imports fine — which is exactly why the failure would otherwise
        # be deferred to the first template read.
        with pytest.raises(packaged.PackagedWorkflowError) as excinfo:
            module.workflow.directory()

    message = str(excinfo.value)
    assert "not a real directory on disk" in message
    assert "zipped" in message  # names the workflow, not just the package


def test_the_cli_reports_the_zip_failure_and_exits(tmp_path: Path, capsys) -> None:
    """`run` asks for the directory while it still owns the error channel, rather than
    leaving the zip to blow up mid-run as a missing template."""
    archive = _write_zipped_package(tmp_path)

    with _OnPath(archive):
        module = importlib.import_module("zipped_flows.demo.workflow")
        args = argparse.Namespace(registry=module.workflow)
        with pytest.raises(SystemExit) as excinfo:
            run_cmd.invocation(args)
    assert excinfo.value.code == 1
    assert "not a real directory on disk" in capsys.readouterr().err


def test_the_package_is_importable_from_a_directory() -> None:
    """The src layout resolves as a real directory, which is the whole constraint."""
    src = Path(__file__).resolve().parents[2] / "workflows" / "src"
    if not src.is_dir():
        pytest.skip("workflows/ not present beside workhorse/")
    with _OnPath(src):
        root = packaged.package_dir("workhorse_workflows")
    assert root.is_dir()
    assert (root / "__init__.py").is_file()


# --------------------------------------------------------------------------------
# 2. the script binds one workflow, and every flag reaches the driver
# --------------------------------------------------------------------------------


class _StubRegistry(Registry):
    """Stands in for the bound Registry: the CLI only passes it through (and asks it
    once for its directory, which a real install always has).

    A real `Registry` rather than a look-alike: the CLI's parameter is the type, and
    only the entry point (which these tests never reach) is stubbed out.
    """

    def __init__(self) -> None:
        super().__init__('demo')

    def directory(self) -> Path:
        return Path(__file__).resolve().parent


def _capture_run_call(argv: list[str], repo_dir_env: str | None = None) -> dict:
    """Drive an entry point to the driver boundary and return what it handed over.

    `repo_dir_env` pins `AGENT_REPO_DIR` for the call, and the default of `None` *unsets*
    it rather than inheriting whatever the caller happens to have exported. The CLI's
    `repo_dir` default has two arms — that variable, then the launch cwd — so a test that
    leaves the variable ambient is not testing either arm, it is testing the environment
    it was started in. Every coder run exports `AGENT_REPO_DIR`, which is exactly the
    environment `make test` runs under from inside one.
    """
    seen: dict = {}
    registry = _StubRegistry()

    def fake_run_pyflow(invocation):
        seen.update(
            registry=invocation.registry,
            run_id=invocation.run_id,
            params=invocation.params,
            flow=invocation.flow,
            no_cache=invocation.no_cache,
            dry_run=invocation.dry_run,
        )
        return 0

    environ = {k: v for k, v in os.environ.items() if k != "AGENT_REPO_DIR"}
    if repo_dir_env is not None:
        environ["AGENT_REPO_DIR"] = repo_dir_env

    with (
        patch.dict(os.environ, environ, clear=True),
        patch.object(run_cmd, "run_pyflow", fake_run_pyflow),
        patch.object(run_cmd, "_load_context_manifest", lambda *a, **k: ManifestContext()),
    ):
        with pytest.raises(SystemExit) as excinfo:
            cli_mod.main(argv, workflow="demo", registry=registry)
    assert excinfo.value.code == 0, "the run itself should have succeeded"
    seen["registry_is_the_bound_one"] = seen.pop("registry") is registry
    return seen


def test_every_flag_reaches_the_engine(tmp_path: Path) -> None:
    params = json.dumps({"story": "AUTH-12"})
    seen = _capture_run_call(
        ["run", "qa", "--run-id=test123", "--params", params, "--dry-run"]
    )

    # The registry travels through by identity — the command runs the workflow it *is*,
    # and there is no name in between for it to resolve to something else.
    assert seen["registry_is_the_bound_one"]
    assert seen["flow"] == "qa"
    assert seen["run_id"] == "test123"
    # `repo_dir` is defaulted in by the CLI itself — a run always has a checkout, and
    # every workflow declares it — so it reaches the engine alongside what was passed.
    # With no `AGENT_REPO_DIR` set (the helper unsets it), the default is the launch cwd.
    assert seen["params"] == {"story": "AUTH-12", "repo_dir": str(Path.cwd().resolve())}
    # Every flag the parser grows has to reach the engine, or the command quietly
    # becomes a poorer CLI than the driver it feeds.
    assert seen["dry_run"] is True


def test_an_exported_repo_dir_beats_the_launch_directory() -> None:
    """`AGENT_REPO_DIR` wins over the cwd, and the cwd is not consulted at all.

    This is the arm every real run takes: the launcher pins the worktree and then a
    command may be invoked from a subdirectory of it — `make -C workhorse test` is the
    everyday case. Asserting a value the cwd cannot produce is what makes the two arms
    distinguishable; the same assertion written as `Path.cwd()` passes for the wrong
    reason whenever the two happen to agree.
    """
    seen = _capture_run_call(["run", "qa"], repo_dir_env="/pinned/repo")

    assert seen["params"]["repo_dir"] == "/pinned/repo"


def test_run_is_injected_when_argv_names_no_subcommand() -> None:
    """`workhorse-demo qa` is `workhorse-demo run qa` — running it is what it is for."""
    assert _capture_run_call(["qa"])["flow"] == "qa"


def test_a_bare_argv_starts_the_entry_flow() -> None:
    assert _capture_run_call([])["flow"] is None


def test_console_script_returns_the_callable_without_running_it() -> None:
    """``[project.scripts]`` targets are called after import, so building one must not
    drive anything."""
    registry = Registry("demo")

    class _Demo(importlib.import_module("workhorse.pyflow").Workflow):
        def start(self):
            return importlib.import_module("workhorse.pyflow").Done(None)

    entry = cli_mod.console_script(registry.entry_point(_Demo))
    assert callable(entry)
    assert entry.__name__ == "workhorse_demo"

    seen: dict = {}
    with (
        patch.object(
            run_cmd, "run_pyflow", lambda invocation: seen.update(flow=invocation.flow) or 0
        ),
        patch.object(run_cmd, "_load_context_manifest", lambda *a, **k: ManifestContext()),
        patch.object(type(registry), "directory", lambda self: Path.cwd()),
    ):
        with pytest.raises(SystemExit):
            entry(["run", "qa"])
    assert seen == {"flow": "qa"}


def test_a_bare_name_is_not_enough_to_build_a_script() -> None:
    """The old spelling — `console_script("coder")` — resolved the name through an
    entry-point group that no longer exists, so it has to fail loudly rather than
    resolve to nothing."""
    with pytest.raises(TypeError) as excinfo:
        # The wrong type is the subject of the test, so the checker is told to allow
        # the one call the runtime guard exists to reject.
        cli_mod.console_script("demo")  # ty: ignore[invalid-argument-type]
    assert "Registry" in str(excinfo.value)


def test_the_parser_is_named_after_the_command_and_the_workflow() -> None:
    parser = parser_mod.build_parser(prog="workhorse-demo", workflow="demo")
    assert parser.prog == "workhorse-demo"
    assert "'demo'" in (parser.description or "")


def test_the_command_table_is_run_dot_control_version() -> None:
    """A subcommand earns its place by being something the workflow's author needs."""
    assert [c.name for c in parser_mod.COMMANDS] == ["run", "dot", "control", "version"]


# --------------------------------------------------------------------------------
# the packaging table the distribution declares
# --------------------------------------------------------------------------------


def test_the_workflows_distribution_declares_its_scripts() -> None:
    """`[project.scripts]` is now the only table binding a workflow to a command."""
    pyproject = Path(__file__).resolve().parents[2] / "workflows" / "pyproject.toml"
    if not pyproject.is_file():  # workhorse is installable standalone
        pytest.skip("workflows/ not present beside workhorse/")
    text = pyproject.read_text()
    assert "[project.scripts]" in text
    assert 'name = "workhorse-workflows"' in text
    assert '[project.entry-points."workhorse.workflows"]' not in text, (
        "the entry-point group is gone; a distribution that still declares one is "
        "advertising a lookup nothing performs"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
