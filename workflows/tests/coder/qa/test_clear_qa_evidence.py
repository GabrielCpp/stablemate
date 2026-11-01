"""What the QA flow clears before a pass, and what it leaves for the owner."""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse_workflows.coder.qa.nodes.qa import clear_qa_evidence

LOG = logging.getLogger("test")


def test_the_scored_evidence_goes_and_the_dry_run_ledgers_stay(tmp_path: Path) -> None:
    """The owner pays for a dry run per scenario while it debugs the plan. A pass that wiped them made the next turn run them again."""
    spec = tmp_path / "spec"
    (spec / "qa" / "steps").mkdir(parents=True)
    (spec / "qa" / "qa-run.ndjson").write_text("", encoding="utf-8")
    (spec / "qa" / "copy-link").mkdir()
    (spec / "qa" / "copy-link" / "qa-run.ndjson").write_text("", encoding="utf-8")
    (spec / "qa-evidence.json").write_text("{}", encoding="utf-8")
    (spec / "qa-report.md").write_text("", encoding="utf-8")

    result = clear_qa_evidence(LOG, spec_dir=str(spec))

    assert result.cleared
    assert not (spec / "qa" / "steps").exists()
    assert not (spec / "qa" / "qa-run.ndjson").exists()
    assert not (spec / "qa-evidence.json").exists()
    assert not (spec / "qa-report.md").exists()
    assert (spec / "qa" / "copy-link" / "qa-run.ndjson").is_file()


def test_no_spec_dir_clears_nothing(tmp_path: Path) -> None:
    result = clear_qa_evidence(LOG, spec_dir="")

    assert not result.cleared
