"""Tests for scriptutil.fresh_import and its WORKHORSE_FRESH_IMPORT=0 escape hatch.

fresh_import exists so a fix landed on disk mid-run reaches the nodes still ahead in
the graph: it purges sys.modules and re-imports. The cost is that the caller gets a
NEW module object, so anything a test monkeypatched onto the old one is discarded —
which silently disables the seams `workhorse.testing` documents as the way to fake a
script's dependencies. WorkflowRun therefore sets WORKHORSE_FRESH_IMPORT=0 for the
duration of a run; these tests pin both halves of that contract.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from workhorse.scriptutil import fresh_import


def _write_module(directory: str, name: str, body: str) -> None:
    (Path(directory) / f"{name}.py").write_text(body, encoding="utf-8")


def test_fresh_import_picks_up_an_edit_made_after_the_first_import():
    with tempfile.TemporaryDirectory() as d:
        _write_module(d, "wh_probe_a", "VALUE = 'before'\n")
        sys.path.insert(0, d)
        try:
            import wh_probe_a  # noqa: PLC0415

            assert wh_probe_a.VALUE == "before"
            _write_module(d, "wh_probe_a", "VALUE = 'after'\n")

            env = dict(os.environ)
            env.pop("WORKHORSE_FRESH_IMPORT", None)
            with patch.dict(os.environ, env, clear=True):
                reloaded = fresh_import("wh_probe_a")

            assert reloaded.VALUE == "after"
        finally:
            sys.path.remove(d)
            sys.modules.pop("wh_probe_a", None)


def test_disabled_fresh_import_preserves_a_monkeypatched_attribute():
    """The reason the hatch exists: a patched seam must survive the re-import call."""
    with tempfile.TemporaryDirectory() as d:
        _write_module(d, "wh_probe_b", "def seam():\n    return 'real'\n")
        sys.path.insert(0, d)
        try:
            import wh_probe_b  # noqa: PLC0415

            wh_probe_b.seam = lambda: "faked"

            with patch.dict(os.environ, {"WORKHORSE_FRESH_IMPORT": "0"}):
                same = fresh_import("wh_probe_b", also_purge=("wh_probe_b",))

            assert same is wh_probe_b
            assert same.seam() == "faked"
        finally:
            sys.path.remove(d)
            sys.modules.pop("wh_probe_b", None)


def test_disabled_fresh_import_still_imports_a_module_not_yet_loaded():
    """Disabling the purge must not turn fresh_import into a lookup that can miss."""
    with tempfile.TemporaryDirectory() as d:
        _write_module(d, "wh_probe_c", "VALUE = 'loaded'\n")
        sys.path.insert(0, d)
        try:
            sys.modules.pop("wh_probe_c", None)
            with patch.dict(os.environ, {"WORKHORSE_FRESH_IMPORT": "0"}):
                mod = fresh_import("wh_probe_c")

            assert mod.VALUE == "loaded"
        finally:
            sys.path.remove(d)
            sys.modules.pop("wh_probe_c", None)


_ONE_SCRIPT_WORKFLOW = """\
name: fresh-import-probe
vars: {}
start: probe
nodes:
  - id: probe
    type: script
    script: scripts/probe.py
    args: []
    outputs:
      - key: probe_result
    next: done
  - id: done
    type: terminal
"""

_PROBE_SCRIPT = """\
import json
import os


def main(logger):
    print(json.dumps({"probe_result": os.environ.get("WORKHORSE_FRESH_IMPORT", "unset")}))
"""


def test_workflow_run_disables_fresh_import_for_the_duration_of_a_run():
    """A script node sees it off during the run; the ambient value is restored after."""
    from workhorse.testing import WorkflowRun  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as wf_dir, tempfile.TemporaryDirectory() as sandbox:
        wf = Path(wf_dir)
        (wf / "scripts").mkdir()
        (wf / "workflow.yaml").write_text(_ONE_SCRIPT_WORKFLOW, encoding="utf-8")
        (wf / "scripts" / "probe.py").write_text(_PROBE_SCRIPT, encoding="utf-8")

        with patch.dict(os.environ, {"WORKHORSE_FRESH_IMPORT": "ambient"}):
            result = WorkflowRun(wf / "workflow.yaml", Path(sandbox)).run()
            after = os.environ["WORKHORSE_FRESH_IMPORT"]

        # Inside the tempdirs: step_outputs reads the run's artifacts off disk.
        assert result.step_outputs("probe") == {"probe_result": "0"}, (
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert after == "ambient", "the harness must restore the ambient value"
