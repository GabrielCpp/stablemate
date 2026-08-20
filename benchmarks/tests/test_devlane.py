"""Tests for the dev-lane harness's fix-lap reader.

One property, and it is the one the measurement rests on: a repair lap closed its gate
when no later lap was sent at the same source. Everything else `devlane.py` prints is
formatting; this is the number a plan step is allowed to claim from.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "devlane", Path(__file__).parents[1] / "devlane.py"
)
# A spec and a loader are what a real file on disk always yields; the import machinery
# answers None for the cases this is not (a namespace package, an unimportable path).
assert _spec is not None and _spec.loader is not None
devlane = importlib.util.module_from_spec(_spec)
sys.modules["devlane"] = devlane
_spec.loader.exec_module(devlane)


def write_lap(repo: Path, run_id: str, seq: int, source: str, lap: int) -> None:
    """One `dev-fix` turn directory, with the two lines the fix envelope really renders."""
    turn = repo / ".agents" / "runs" / f"coder-{run_id}" / "turns" / f"001-{seq:05d}-dev-fix"
    turn.mkdir(parents=True)
    (turn / "prompt.md").write_text(
        "# Coder Workflow — Fix Stage\n\n"
        f"- **Gate:** `{source}`\n"
        f"- **Repair attempt:** {lap}\n",
        encoding="utf-8",
    )


def test_the_last_lap_at_a_source_is_the_one_that_closed_its_gate(tmp_path: Path) -> None:
    """A gate that came back was sent at again; the one that did not is the closer.

    This is the same question the flow asks — it re-runs the gate and believes the gate,
    not the turn's own `status` — so the measurement reads the sequence, not the claim.
    """
    write_lap(tmp_path, "r", 3, "lint", 1)
    write_lap(tmp_path, "r", 4, "lint", 2)

    assert [(lap.source, lap.lap, lap.closed) for lap in devlane.laps(tmp_path, "r")] == [
        ("lint", 1, False),
        ("lint", 2, True),
    ]


def test_a_source_is_counted_independently_of_the_ones_interleaved_with_it(
    tmp_path: Path,
) -> None:
    """Gates re-run in order, so another source's lap can sit between two of this one's.

    Reading adjacency instead would call the first `lint` lap closed because a `test` lap
    followed it — and inflate exactly the rate this row exists to watch.
    """
    write_lap(tmp_path, "r", 3, "lint", 1)
    write_lap(tmp_path, "r", 4, "test", 1)
    write_lap(tmp_path, "r", 5, "lint", 2)

    closed = {(lap.source, lap.lap): lap.closed for lap in devlane.laps(tmp_path, "r")}

    assert closed == {("lint", 1): False, ("test", 1): True, ("lint", 2): True}


def test_a_run_that_never_repaired_reports_no_laps(tmp_path: Path) -> None:
    """The happy path is silent here, and the renderer has to say so rather than divide."""
    (tmp_path / ".agents" / "runs" / "coder-r" / "turns").mkdir(parents=True)

    assert devlane.laps(tmp_path, "r") == []
    assert "no repair laps" in devlane.render_laps({"r": []})


def test_the_rate_is_reported_per_source_and_never_averaged(tmp_path: Path) -> None:
    """One source getting worse while the mean holds flat is the failure being watched."""
    write_lap(tmp_path, "r", 3, "lint", 1)
    write_lap(tmp_path, "r", 4, "test", 1)
    write_lap(tmp_path, "r", 5, "test", 2)

    table = devlane.render_laps({"r": devlane.laps(tmp_path, "r")})

    assert "| `lint` | 1 | 1 | 100% |" in table
    assert "| `test` | 2 | 1 | 50% |" in table
