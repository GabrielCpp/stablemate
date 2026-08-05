"""Workflow discovery: what this machine can run, read out of `pipx list --json`.

A workflow is a distribution binding a `workhorse-<name>` console script. There is
no registry to query and no selection list to consult — the installed set IS the
answer, which is what keeps it from drifting.

Two things are being pinned. First, the classification: a PyPI install needs nothing
mounted, a local one needs its directory bound into the container, so telling them
apart is the substantive output. Second, the tolerance: this parses another tool's
JSON from inside a Makefile, where a pipx upgrade that renames a key must cost a
missing workflow rather than a traceback in the middle of `make`.

The fixtures below are the real shape, taken from an actual `pipx list --json`.

    ./.venv/bin/python -m pytest tests/test_pipx.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from farrier import pipx


def _venv(apps: list[str], origin: str, *, pip_args: list[str] | None = None,
          package: str = "workhorse-workflows", version: str = "0.1.0") -> dict:
    return {
        "metadata": {
            "main_package": {
                "package": package,
                "package_or_url": origin,
                "pip_args": pip_args if pip_args is not None else [],
                "package_version": version,
                "apps": apps,
                "include_apps": True,
            }
        }
    }


def _payload(**venvs: dict) -> dict:
    return {"pipx_spec_version": "0.1", "venvs": venvs}


# --------------------------------------------------------------------------- #
# What counts as a workflow
# --------------------------------------------------------------------------- #


def test_a_workflow_is_a_workhorse_prefixed_console_script():
    found = pipx.parse(
        _payload(
            **{
                "workhorse-workflows": _venv(
                    ["workhorse-coder", "workhorse-author", "workhorse-okf-builder"],
                    "workhorse-workflows",
                )
            }
        )
    )
    assert [d.workflows for d in found] == [("author", "coder", "okf-builder")]


def test_venvs_that_provide_no_workflow_are_not_reported():
    """The base library installs as a pipx venv with no apps at all; unrelated tools
    have apps that are not workflows. Neither is a workflow provider."""
    found = pipx.parse(
        _payload(
            **{
                "stablemate-library": _venv([], "/home/dev/stablemate/base-library",
                                            pip_args=["--editable"]),
                "cline": _venv(["cline"], "cline"),
            }
        )
    )
    assert found == []


def test_the_bare_prefix_and_the_libraries_themselves_are_not_workflows():
    """`workhorse-agent` is the engine and `workhorse-workflows` the distribution;
    neither names a workflow you can run, even though both match the prefix."""
    found = pipx.parse(
        _payload(
            wf=_venv(["workhorse-agent", "workhorse-workflows", "workhorse-", "workhorse-coder"],
                     "workhorse-workflows")
        )
    )
    assert found[0].workflows == ("coder",)


def test_a_name_is_reported_once_even_from_two_distributions():
    """A fork installed alongside the original. Which script wins is pipx's PATH
    order to settle, not this module's."""
    found = pipx.parse(
        _payload(
            a=_venv(["workhorse-coder"], "workhorse-workflows", package="workhorse-workflows"),
            b=_venv(["workhorse-coder", "workhorse-extra"], "acme-workflows", package="acme-workflows"),
        )
    )
    assert pipx.names(found) == ["coder", "extra"]


# --------------------------------------------------------------------------- #
# PyPI vs local — the distinction the container cares about
# --------------------------------------------------------------------------- #


def test_a_pypi_install_has_no_local_path_to_mount():
    (dist,) = pipx.parse(_payload(wf=_venv(["workhorse-coder"], "workhorse-workflows")))
    assert dist.local_path is None
    assert not dist.missing
    assert dist.version == "0.1.0"


def test_a_vcs_install_has_no_local_path_either():
    (dist,) = pipx.parse(
        _payload(wf=_venv(["workhorse-coder"], "git+https://example.com/acme/workflows.git"))
    )
    assert dist.local_path is None


def test_a_local_install_reports_the_directory_the_container_must_bind(tmp_path: Path):
    src = tmp_path / "workflows"
    src.mkdir()
    (dist,) = pipx.parse(
        _payload(wf=_venv(["workhorse-coder"], str(src), pip_args=["--editable"]))
    )
    assert dist.local_path == src
    assert dist.editable
    assert not dist.missing


def test_an_editable_install_whose_source_is_gone_is_flagged(tmp_path: Path):
    """It still runs here — the venv holds a built copy — so nothing else reports it
    until a container tries to bind the path and the error names a mount instead."""
    (dist,) = pipx.parse(
        _payload(
            wf=_venv(["workhorse-coder"], str(tmp_path / "deleted"), pip_args=["--editable"])
        )
    )
    assert dist.local_path == tmp_path / "deleted"
    assert dist.missing


def test_a_deleted_path_is_not_silently_reclassified_as_a_pypi_name(tmp_path: Path):
    """Classification is by shape, not by existence. Otherwise a local install whose
    directory vanished would look like a PyPI package of the same name and the
    container would try to `pip install /home/dev/gone`."""
    (dist,) = pipx.parse(_payload(wf=_venv(["workhorse-coder"], str(tmp_path / "gone"))))
    assert dist.local_path is not None


def test_a_home_relative_path_is_expanded():
    (dist,) = pipx.parse(_payload(wf=_venv(["workhorse-coder"], "~/src/workflows")))
    assert dist.local_path == Path("~/src/workflows").expanduser()


# --------------------------------------------------------------------------- #
# Tolerance — this runs inside a Makefile
# --------------------------------------------------------------------------- #


def test_an_unrecognisable_payload_costs_workflows_not_a_traceback():
    for junk in (None, [], "nope", {}, {"venvs": "nope"}, {"venvs": {"a": "nope"}}):
        assert pipx.parse(junk) == []


def test_a_venv_missing_the_metadata_pipx_used_to_write_is_skipped():
    assert pipx.parse({"venvs": {"wf": {"metadata": {}}}}) == []
    assert pipx.parse({"venvs": {"wf": {}}}) == []


def test_pipx_not_installed_means_no_workflows_not_a_broken_build(monkeypatch):
    def missing(cmd):
        raise OSError("no pipx")

    monkeypatch.setattr(pipx, "_run", missing)
    assert pipx.discover() == []


def test_pipx_failing_or_emitting_junk_means_no_workflows(monkeypatch):
    monkeypatch.setattr(
        pipx, "_run", lambda cmd: subprocess.CompletedProcess(cmd, 1, "", "boom")
    )
    assert pipx.discover() == []

    monkeypatch.setattr(
        pipx, "_run", lambda cmd: subprocess.CompletedProcess(cmd, 0, "not json", "")
    )
    assert pipx.discover() == []


def test_discover_reads_the_json_pipx_actually_emits(monkeypatch):
    payload = _payload(wf=_venv(["workhorse-coder", "workhorse-author"], "workhorse-workflows"))
    monkeypatch.setattr(
        pipx,
        "_run",
        lambda cmd: subprocess.CompletedProcess(cmd, 0, json.dumps(payload), ""),
    )
    assert pipx.names(pipx.discover()) == ["author", "coder"]
