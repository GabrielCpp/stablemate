"""The one leverage test that needs `_frozenapp`, kept beside it until its fate is decided."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TASKS = Path(__file__).parents[1] / "tasks"
sys.path.insert(0, str(TASKS))

import _frozenapp as frozen  # noqa: E402
from paddock.tasks import leverage as lev  # noqa: E402


def test_a_fixture_refuses_a_leverage_key_it_does_not_have() -> None:
    with pytest.raises(ValueError, match="leverage must name one or more of"):
        frozen.Fixture(app="apps/x", repo_dir="x", leverage=("obligations", "clicks"))
    assert frozen.Fixture(app="apps/x", repo_dir="x").leverage == lev.LEVERAGE_KEYS
