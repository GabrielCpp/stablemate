"""Workflows that arrive as an installed distribution.

This is now the *only* way a workflow reaches workhorse, which is why the error paths
below get as much attention as the happy one: with the library layers gone there is no
second mechanism for a failed resolution to fall through to.

Three properties, each of which fails silently or late if left untested:

1. A name registered in the ``workhorse.workflows`` entry-point group resolves to that
   package's directory — the whole point of the mechanism.
2. A package that is not a real directory on disk (a zip import) is refused **at
   resolution**, with an explanation. Left alone this surfaces as a ``TemplateNotFound``
   deep inside a run, because the prompt renderer is a filesystem template loader.
3. ``workhorse run <name> <flow> …`` and ``workhorse-<name> run <flow> …`` go through
   one parser with the name bound differently. Two commands with two parsers is the
   failure this shape invites, so the test compares what the driver actually receives.

Standalone and dependency-free: the distributions here are written into tmp_path and put
on ``sys.path``, so nothing is installed and no network is touched.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
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


# --------------------------------------------------------------------------------
# fixtures: a real distribution on sys.path, and a zip-imported one
# --------------------------------------------------------------------------------


def _write_dist_info(site: Path, dist_name: str, entry_points: dict[str, str]) -> None:
    """Write the .dist-info importlib.metadata reads entry points out of."""
    info = site / f"{dist_name.replace('-', '_')}-0.1.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {dist_name}\nVersion: 0.1.0\n"
    )
    lines = [f"[{packaged.ENTRY_POINT_GROUP}]"]
    lines += [f"{name} = {value}" for name, value in entry_points.items()]
    (info / "entry_points.txt").write_text("\n".join(lines) + "\n")


#: A ``demo_flows.demo.workflow`` module holding a real `Registry`, which is what an
#: entry point must point at. Written as source rather than built in-process because
#: the whole mechanism under test is "import the module the metadata names".
_WORKFLOW_MODULE = '''
from workhorse.pyflow import Done, Registry, Workflow


class Demo(Workflow):
    def start(self):
        return Done(None)


workflow = Registry("demo")
main = workflow.main(Demo)
'''


def _write_package(site: Path, module_source: str = _WORKFLOW_MODULE) -> None:
    """A minimal ``demo_flows.demo`` workflow package."""
    pkg = site / "demo_flows" / "demo"
    pkg.mkdir(parents=True)
    (site / "demo_flows" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "workflow.py").write_text(module_source)


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
        for name in [n for n in sys.modules if n.split(".")[0] in ("demo_flows", "zipped_flows", "workhorse_workflows")]:
            del sys.modules[name]
        importlib.invalidate_caches()


# --------------------------------------------------------------------------------
# 1. an entry point resolves to the package directory
# --------------------------------------------------------------------------------


def test_entry_point_resolves_to_package_directory(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    _write_package(site)
    _write_dist_info(site, "demo-flows", {"demo": "demo_flows.demo.workflow:workflow"})

    with _OnPath(site):
        found = packaged.find_packaged_workflow("demo")
        assert found is not None
        assert found.value == "demo_flows.demo.workflow:workflow"
        assert found.distribution == "demo-flows"
        # The workflow dir is the package the entry-point MODULE lives in, not the
        # module itself: prompts/ sits beside workflow.py.
        assert found.workflow_dir() == site / "demo_flows" / "demo"
        assert found.load() is not None


def test_unregistered_name_is_not_found(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    _write_package(site)
    _write_dist_info(site, "demo-flows", {"demo": "demo_flows.demo.workflow:workflow"})

    with _OnPath(site):
        assert packaged.find_packaged_workflow("nobody") is None


def test_two_distributions_claiming_one_name_raise(tmp_path: Path) -> None:
    entries = [
        importlib.metadata.EntryPoint(
            name="demo", value="one.demo.workflow:workflow", group=packaged.ENTRY_POINT_GROUP
        ),
        importlib.metadata.EntryPoint(
            name="demo", value="two.demo.workflow:workflow", group=packaged.ENTRY_POINT_GROUP
        ),
    ]
    with patch.object(packaged, "_entry_points", lambda: entries):
        with pytest.raises(packaged.PackagedWorkflowError) as excinfo:
            packaged.iter_packaged_workflows()
    assert "registered twice" in str(excinfo.value)

    # The same distribution seen twice on sys.path is a path quirk, not an ambiguity.
    with patch.object(packaged, "_entry_points", lambda: [entries[0], entries[0]]):
        assert len(packaged.iter_packaged_workflows()) == 1


def test_top_level_module_entry_point_is_rejected() -> None:
    """There is no package directory to be the workflow directory."""
    workflow = packaged.PackagedWorkflow(name="demo", value="demo:workflow")
    with pytest.raises(packaged.PackagedWorkflowError) as excinfo:
        workflow.workflow_dir()
    assert "top-level module" in str(excinfo.value)


# --------------------------------------------------------------------------------
# 2. a zip-imported package fails loudly, at resolution
# --------------------------------------------------------------------------------


def _write_zipped_package(tmp_path: Path) -> Path:
    archive = tmp_path / "zipped_flows.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("zipped_flows/__init__.py", "")
        zf.writestr("zipped_flows/demo/__init__.py", "")
        zf.writestr(
            "zipped_flows/demo/workflow.py", _WORKFLOW_MODULE.replace('"demo"', '"zipped"')
        )
    return archive


def test_zip_imported_package_fails_at_resolution(tmp_path: Path) -> None:
    """Not at TemplateNotFound time, three nodes into a run."""
    archive = _write_zipped_package(tmp_path)
    site = tmp_path / "site"
    site.mkdir()
    _write_dist_info(
        site, "zipped-flows", {"zipped": "zipped_flows.demo.workflow:workflow"}
    )

    with _OnPath(site, archive):
        found = packaged.find_packaged_workflow("zipped")
        assert found is not None
        # The module imports fine — which is exactly why the failure would otherwise
        # be deferred to the first template read.
        assert found.load() is not None
        with pytest.raises(packaged.PackagedWorkflowError) as excinfo:
            found.workflow_dir()

    message = str(excinfo.value)
    assert "not a real directory on disk" in message
    assert "zipped" in message  # names the workflow, not just the package


def test_cli_reports_the_zip_failure_and_exits(tmp_path: Path, capsys) -> None:
    """`packaged_registry` asks for the directory while it still owns the error
    channel, rather than leaving the zip to blow up mid-run as a missing template."""
    archive = _write_zipped_package(tmp_path)
    site = tmp_path / "site"
    site.mkdir()
    _write_dist_info(
        site, "zipped-flows", {"zipped": "zipped_flows.demo.workflow:workflow"}
    )

    with _OnPath(site, archive):
        with pytest.raises(SystemExit) as excinfo:
            run_cmd.packaged_registry("zipped")
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "not a real directory on disk" in err


def test_an_entry_point_that_is_not_a_registry_is_a_clear_error(
    tmp_path: Path, capsys
) -> None:
    """The group's contract is `Registry`, and a distribution can get that wrong —
    pointing at the `Workflow` subclass, or at the `main` callable beside it."""
    site = tmp_path / "site"
    site.mkdir()
    _write_package(site, module_source="workflow = object()\n")
    _write_dist_info(site, "demo-flows", {"demo": "demo_flows.demo.workflow:workflow"})

    with _OnPath(site):
        with pytest.raises(SystemExit) as excinfo:
            run_cmd.packaged_registry("demo")
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "not a `Registry`" in err
    assert "demo_flows.demo.workflow:workflow" in err


def test_an_unknown_name_lists_what_is_installed(tmp_path: Path, capsys) -> None:
    """The only resolution mechanism left is the entry-point group, so the error has
    to be the whole answer: there is no library layer to go looking in next."""
    site = tmp_path / "site"
    site.mkdir()
    _write_package(site)
    _write_dist_info(site, "demo-flows", {"demo": "demo_flows.demo.workflow:workflow"})

    with _OnPath(site):
        with pytest.raises(SystemExit) as excinfo:
            run_cmd.packaged_registry("nobody")
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "no workflow named 'nobody' is installed" in err
    assert "demo" in err


# --------------------------------------------------------------------------------
# 3. one parser, two front doors
# --------------------------------------------------------------------------------


class _StubRegistry:
    """Stands in for the resolved Registry: the CLI only passes it through."""

    name = "demo"


def _capture_run_call(argv: list[str], *, workflow: str | None) -> dict:
    """Drive main() to the driver boundary and return what run_pyflow was handed."""
    seen: dict = {}

    def fake_run_pyflow(invocation):
        seen.update(
            registry_name=invocation.registry.name,
            run_id=invocation.run_id,
            params=invocation.params,
            flow=invocation.flow,
            no_cache=invocation.no_cache,
            dry_run=invocation.dry_run,
        )
        return 0

    with (
        patch.object(run_cmd, "packaged_registry", lambda spec: _StubRegistry()),
        patch.object(run_cmd, "run_pyflow", fake_run_pyflow),
        patch.object(run_cmd, "_load_context_manifest", lambda *a, **k: ManifestContext()),
    ):
        with pytest.raises(SystemExit) as excinfo:
            cli_mod.main(argv, workflow=workflow)
    assert excinfo.value.code == 0, "the run itself should have succeeded"
    return seen


def test_both_front_doors_reach_the_engine_identically(tmp_path: Path) -> None:
    params = json.dumps({"story": "AUTH-12"})

    through_workhorse = _capture_run_call(
        ["run", "demo", "qa", "--run-id=test123", "--params", params, "--dry-run"],
        workflow=None,
    )
    through_script = _capture_run_call(
        ["run", "qa", "--run-id=test123", "--params", params, "--dry-run"],
        workflow="demo",
    )

    assert through_workhorse == through_script
    assert through_script["flow"] == "qa"
    assert through_script["run_id"] == "test123"
    assert through_script["params"] == {"story": "AUTH-12"}
    # Every flag the parser grows has to reach the engine through both doors, or the
    # bound form quietly becomes a second, poorer CLI — which is the whole point here.
    assert through_script["dry_run"] is True


def test_the_console_script_binds_the_name_and_nothing_else(tmp_path: Path) -> None:
    """console_script returns the callable; it does not run at build time."""
    entry = cli_mod.console_script("demo")
    assert callable(entry)

    seen: dict = {}
    with (
        patch.object(run_cmd, "packaged_registry", lambda spec: _StubRegistry()),
        patch.object(
            run_cmd, "run_pyflow", lambda invocation: seen.update(flow=invocation.flow) or 0
        ),
        patch.object(run_cmd, "_load_context_manifest", lambda *a, **k: ManifestContext()),
    ):
        with pytest.raises(SystemExit):
            entry(["run", "qa"])
    assert seen == {"flow": "qa"}


def test_the_two_commands_share_one_argument_definition() -> None:
    """Same options, same defaults — because they come from one `run.add_arguments`."""
    plain = parser_mod.build_parser()
    bound = parser_mod.build_parser("workhorse-demo")

    def run_options(parser):
        sub = next(
            a for a in parser._actions if isinstance(a, __import__("argparse")._SubParsersAction)
        )
        run_parser = sub.choices["run"]
        return {tuple(a.option_strings) or (a.dest,): a.default for a in run_parser._actions}

    assert run_options(plain) == run_options(bound)
    assert plain.prog == "workhorse"
    assert bound.prog == "workhorse-demo"


def test_bound_name_rejects_a_contradicting_workflow_flag(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["run", "--workflow", "other"], workflow="demo")
    assert excinfo.value.code == 2
    assert "--workflow is not accepted here" in capsys.readouterr().err


def test_bound_name_rejects_a_stray_second_positional() -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["run", "qa", "extra"], workflow="demo")
    assert excinfo.value.code == 2


def test_bound_name_refuses_other_subcommands(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(["dot", "--workflow", "x"], workflow="demo")
    assert excinfo.value.code == 2
    assert "workhorse dot" in capsys.readouterr().err


def test_run_is_injected_for_the_bound_form_too(tmp_path: Path) -> None:
    """`workhorse-demo qa` is `workhorse-demo run qa`, same as the unbound rule."""
    seen = _capture_run_call(["qa"], workflow="demo")
    assert seen["flow"] == "qa"


# --------------------------------------------------------------------------------
# the packaging tables the distribution declares
# --------------------------------------------------------------------------------


def test_the_workflows_distribution_declares_both_tables() -> None:
    """Skeleton or not, the tables must exist and be spelled right."""
    pyproject = Path(__file__).resolve().parents[2] / "workflows" / "pyproject.toml"
    if not pyproject.is_file():  # workhorse is installable standalone
        pytest.skip("workflows/ not present beside workhorse/")
    text = pyproject.read_text()
    assert f'[project.entry-points."{packaged.ENTRY_POINT_GROUP}"]' in text
    assert "[project.scripts]" in text
    assert 'name = "workhorse-workflows"' in text


def test_the_package_is_importable_from_a_directory() -> None:
    """The src layout resolves as a real directory, which is the whole constraint."""
    src = Path(__file__).resolve().parents[2] / "workflows" / "src"
    if not src.is_dir():
        pytest.skip("workflows/ not present beside workhorse/")
    with _OnPath(src):
        root = packaged.package_dir("workhorse_workflows")
    assert root.is_dir()
    assert (root / "__init__.py").is_file()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
