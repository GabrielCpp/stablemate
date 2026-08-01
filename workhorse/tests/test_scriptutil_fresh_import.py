"""Tests for scriptutil.fresh_import and its WORKHORSE_FRESH_IMPORT=0 escape hatch.

fresh_import exists so a fix landed on disk mid-run reaches the nodes still ahead in
the graph: it purges sys.modules and re-imports. The cost is that the caller gets a
NEW module object, so anything a test monkeypatched onto the old one is discarded —
which silently disables a monkeypatched seam. WORKHORSE_FRESH_IMPORT=0 is the escape
hatch for exactly that; these tests pin both halves of the contract.
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
            import wh_probe_a  # noqa: PLC0415  # ty: ignore[unresolved-import]

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
            import wh_probe_b  # noqa: PLC0415  # ty: ignore[unresolved-import]

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


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
