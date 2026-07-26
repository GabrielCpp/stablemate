"""Tests for the durable QA-stack bring-up node (ensure-stack.py)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "ensure-stack.py"


def _run(docs_root: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "qa-stack.yml", str(docs_root)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_skips_when_no_manifest_is_authored(tmp_path: Path) -> None:
    """A repo without a manifest is not a failure — QA proceeds exactly as before."""
    out = _run(tmp_path)
    assert out["stack_ready"] == "skip"


def test_ready_when_manifest_needs_no_bring_up(tmp_path: Path) -> None:
    """A manifest with no launch/prepare/seed steps is trivially ready (nothing to run)."""
    (tmp_path / "qa-stack.yml").write_text(
        "entry_url: http://localhost:65535\n", encoding="utf-8",
    )
    out = _run(tmp_path)
    assert out["stack_ready"] == "yes"
    assert out["stack_entry_url"] == "http://localhost:65535"


def test_reports_the_failing_prepare_step(tmp_path: Path) -> None:
    """A prepare step that exits nonzero fails the node at that step, and stops."""
    (tmp_path / "qa-stack.yml").write_text(
        "prepare:\n  - 'false'\nseed:\n  - 'true'\n", encoding="utf-8",
    )
    out = _run(tmp_path)
    assert out["stack_ready"] == "no"
    assert out["stack_failed_step"] == "prepare[0]"
