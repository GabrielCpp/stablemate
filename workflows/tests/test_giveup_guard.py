"""`scripts/check_no_giveup.py` fires, and its vocabulary list keeps the names that matter."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_no_giveup.py"

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
