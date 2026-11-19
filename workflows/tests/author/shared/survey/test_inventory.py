"""`record_slug` — the file name a unit's finding record is stored under."""
from __future__ import annotations

from workhorse_workflows.author.shared.survey import record_slug


def test_a_record_slug_is_filename_safe_and_lowercased() -> None:
    assert record_slug("src/api/handler.py") == "src-api-handler-py"
    assert record_slug("legacy/Reports/Q1 view") == "legacy-reports-q1-view"
