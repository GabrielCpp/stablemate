from __future__ import annotations

import json
from pathlib import Path

import pytest

from ostler.cli import main


@pytest.fixture
def behavior_repo(tmp_path: Path) -> Path:
    docs = tmp_path / "docs/features/api"
    docs.mkdir(parents=True)
    (docs / "items.md").write_text(
        "---\ntype: server\ntitle: API\n---\n\n# API\n\n## Endpoints\n\n### items\n\n"
        "- does: Requests return at most 50 items.\n"
        "- code: missing.py::list_items\n",
        encoding="utf-8",
    )
    (tmp_path / "api.py").write_text(
        "@app.get('/items')\ndef list_items(limit=20):\n"
        "    if limit < 0:\n        raise ValueError('negative limit')\n"
        "    return items[:limit]\n",
        encoding="utf-8",
    )
    return tmp_path


def test_audit_prepares_uncited_evidence_and_ungrounded_claims(
    behavior_repo: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["-C", str(behavior_repo), "audit", "api.py", "--json", "--no-index"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "prepared"
    candidates = [item for packet in data["packets"] for item in packet["candidates"]]
    claims = [item for packet in data["packets"] for item in packet["claims"]]
    assert {item["kind"] for item in candidates} >= {"route", "function_default", "raise", "return"}
    assert any("limit=20" in item["text"] for item in candidates)
    assert any("50 items" in item["text"] for item in claims)
    assert any("missing.py::list_items" in item["citations"] for item in claims)
    assert {packet["group"] for packet in data["packets"]} == {"source_file", "ungrounded_book"}
    assert all(not packet["claims"] for packet in data["packets"] if packet["group"] == "source_file")
    assert len(claims) == 1, "The API and endpoint titles must not become semantic claims"
    assert all(packet["digest"] for packet in data["packets"])
    assert data["omitted_candidates"] == data["omitted_claims"] == 0
    assert not (behavior_repo / "docs/features/sources.json").exists()


def test_audit_reports_unsupported_files_without_claiming_complete(
    behavior_repo: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    (behavior_repo / "app.ts").write_text("export const limit = 50;", encoding="utf-8")
    assert main(["-C", str(behavior_repo), "audit", "api.py", "app.ts", "--json", "--no-index"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "prepared"
    assert any(item["path"] == "app.ts" and item["status"] == "unsupported"
               for item in data["inventory"]["files"])
    assert data["inventory"]["limitations"]


def test_audit_bounds_fail_instead_of_returning_a_truncated_success(
    behavior_repo: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["-C", str(behavior_repo), "audit", "api.py", "--json", "--max-chars", "10", "--no-index"]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "without truncation" in output.err


def test_audit_human_output_has_no_semantic_success_and_leaves_inputs_unchanged(
    behavior_repo: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    before = {path.relative_to(behavior_repo): path.read_bytes() for path in behavior_repo.rglob("*") if path.is_file()}
    assert main(["-C", str(behavior_repo), "audit", "api.py", "--no-index"]) == 0
    output = capsys.readouterr().out
    assert "No semantic verdicts inferred" in output and "api.py: parsed" in output
    after = {path.relative_to(behavior_repo): path.read_bytes() for path in behavior_repo.rglob("*") if path.is_file()}
    assert after == before
