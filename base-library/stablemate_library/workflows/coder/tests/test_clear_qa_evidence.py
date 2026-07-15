"""Tests for stale QA output cleanup before context generation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "clear-qa-evidence.py"


def test_clears_qa_tree_and_root_evidence_without_recreating_runner_output(
    tmp_path: Path,
) -> None:
    spec = tmp_path / "docs" / "specs" / "story"
    qa = spec / "qa"
    qa.mkdir(parents=True)
    (qa / "stale.txt").write_text("stale", encoding="utf-8")
    (spec / "qa-evidence.json").write_text("{}", encoding="utf-8")
    (spec / "qa-plan.yml").write_text("version: 2\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(spec), ""],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"qa_cleared": "yes"}
    assert not qa.exists()
    assert not (spec / "qa-evidence.json").exists()
    assert (spec / "qa-plan.yml").is_file()
