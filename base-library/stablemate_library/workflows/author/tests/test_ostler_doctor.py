"""Tests for ostler-doctor.py — the referential-integrity gate node.

The script computes graph facts in-process via ``ostler.doctor()`` (no CLI shell-out); these
tests build a real Markdown OKF fixture with :func:`write_epic` / :func:`write_knowledge` and
run the script the way the local worker does, then assert on the emitted JSON — errors block,
warnings don't, and an unloadable graph fails open to a clean skip.
"""
from __future__ import annotations

import importlib.util
import json
import sys

import pytest
from conftest import SCRIPTS, requires_ostler, run_script, write_epic, write_knowledge

SCRIPT = SCRIPTS / "ostler-doctor.py"


def _load_script_module():
    """Import ostler-doctor.py as a module so its ``main`` can be driven in-process."""
    spec = importlib.util.spec_from_file_location("ostler_doctor", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@requires_ostler
def test_clean_graph_passes(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    out = run_script("ostler-doctor.py", repo=tmp_path)
    assert out["integrity_ok"] == "yes", out["integrity_report"]
    assert out["integrity_errors"] == ""


@requires_ostler
def test_errors_block_with_pointers(tmp_path):
    # A story covering a seed that no epic declares → dangling-seed (error).
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}],
               stories=[{"slug": "s1", "covers": ["i1", "ghost-seed"]}])
    out = run_script("ostler-doctor.py", repo=tmp_path)
    assert out["integrity_ok"] == "no"
    assert "ghost-seed" in out["integrity_errors"]
    # the constraint that the resolver must not erase the ref is part of the pointer
    assert "never" in out["integrity_errors"].lower()


@requires_ostler
def test_warnings_do_not_block(tmp_path):
    # A knowledge surface with no matching feature doc → ungrounded-surface (warn), never a block.
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    write_knowledge(tmp_path, "form")
    out = run_script("ostler-doctor.py", repo=tmp_path)
    assert out["integrity_ok"] == "yes", out["integrity_report"]
    assert out["integrity_errors"] == ""
    assert "0 error(s)" in out["integrity_report"]
    assert "warning(s)" in out["integrity_report"] and "0 warning(s)" not in out["integrity_report"]


def test_skip_when_graph_cannot_load(tmp_path, monkeypatch, capsys):
    # doctor() raising (unloadable graph / infra fault) fails open to a clean skip, exit 0.
    mod = _load_script_module()

    class _Boom:
        def __init__(self, root):
            pass

        def doctor(self, *, epic=None):
            raise RuntimeError("no graph here")

    monkeypatch.setattr(mod, "Ostler", _Boom)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    monkeypatch.setenv("AGENT_REPO_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["integrity_ok"] == "skip"
    assert "could not run" in out["integrity_report"]
