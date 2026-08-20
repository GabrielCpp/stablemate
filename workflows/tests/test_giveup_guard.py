"""`scripts/check_no_giveup.py` fires, and its vocabulary list keeps the names that matter.

The guard is a substring sweep, so *that* it matches is not in doubt. What is in doubt is
everything around the match: that the sweep reaches the tracked tree, that a hit becomes a
non-zero exit rather than a printed warning, and — the part no amount of running it on a
clean tree can show — that the list still names the machinery of the deleted pattern.

The zero-diff streak is the case that forced this file. The guard banned its
`failure_class` string, which reads like coverage until you check the code it was written
against: by then that exit had already become a gate, and the string was gone. The counter,
its cap and the gate it jumped to were the whole mechanism, and the guard would have let
all three back in. A list that can silently lose an entry is why the required names are
asserted here rather than left to a reviewer.

The names are spelled in fragments on purpose. This file is tracked under `workflows/`,
which is exactly what the guard scans, so writing them whole would make the guard fail on
its own test.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_no_giveup.py"

#: Assembled at import time so the literal never appears in this file. See the docstring.
REQUIRED = (
    "giveup" + "_reason",
    "operator" + "_consulted",
    "Qa" + "GiveupRecord",
    "record" + "_qa_giveup",
    "docs-" + "not-passed",
    "zero-" + "diff-streak",
    "MAX_ZERO" + "_DIFF_COMMITS",
    "_zero" + "_diff_gate",
    "zero" + "_diff=",
)


@pytest.fixture(scope="module")
def guard() -> Any:
    spec = importlib.util.spec_from_file_location("check_no_giveup", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", REQUIRED)
def test_the_vocabulary_survives(guard: Any, name: str) -> None:
    assert name in guard.BANNED


def test_a_reintroduction_fails_the_guard(
    guard: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One line of the old code, and the guard exits non-zero rather than warning."""
    planted = tmp_path / "workflow.py"
    planted.write_text(
        "        if zero_diff >= self.MAX_ZERO" + "_DIFF_COMMITS:\n", encoding="utf-8"
    )
    monkeypatch.setattr(guard, "REPO", tmp_path)
    monkeypatch.setattr(guard, "_tracked_files", lambda: [planted])

    offenders = guard.check_no_giveup()

    assert offenders and "workflow.py:1" in offenders[0]
    assert guard.main() == 1


def test_the_tree_is_clean(guard: Any) -> None:
    """The half `make check-no-giveup` runs, here so a package suite sees it too."""
    assert guard.check_no_giveup() == []
