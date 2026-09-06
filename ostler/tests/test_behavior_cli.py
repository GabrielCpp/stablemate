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
    candidates = data["inventory"]["candidates"]
    claims = [item for packet in data["packets"] for item in packet["claims"]]
    assert {item["kind"] for item in candidates} >= {"route", "function_default", "raise", "return"}
    assert any("limit=20" in item["text"] for item in candidates)
    assert any("50 items" in item["text"] for item in claims)
    assert any("missing.py::list_items" in item["citations"] for item in claims)
    # api.py exports list_items and nothing cites it: a deterministic finding, never a packet.
    assert {packet["group"] for packet in data["packets"]} == {"ungrounded_book"}
    assert [(item["path"], item["exported_symbols"]) for item in data["undocumented"]] == [("api.py", ["list_items"])]
    assert len(claims) == 1, "The API and endpoint titles must not become semantic claims"
    assert all(packet["digest"] for packet in data["packets"])
    assert data["omitted_candidates"] == data["omitted_claims"] == 0
    assert not (behavior_repo / "docs/features/sources.json").exists()


def test_audit_prints_the_undocumented_file_finding(
    behavior_repo: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["-C", str(behavior_repo), "audit", "api.py", "--no-index"]) == 0
    out = capsys.readouterr().out
    assert "Undocumented: api.py:" in out
    assert "list_items" in out and "no claim cites this file" in out


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


def test_audit_tier_flag_defers_private_uncited_candidates(
    behavior_repo: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    (behavior_repo / "api.py").write_text(
        "def list_items(limit=20):\n    return _clip(limit)\n\ndef _clip(limit):\n    return items[:limit]\n",
        encoding="utf-8",
    )
    assert main(["-C", str(behavior_repo), "audit", "api.py", "--json", "--no-index"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tier"] == 1 and data["deferred_candidates"] == 1
    assert main(["-C", str(behavior_repo), "audit", "api.py", "--no-index"]) == 0
    assert "Deferred: 1 tier-2 candidates" in capsys.readouterr().out
    assert main(["-C", str(behavior_repo), "audit", "api.py", "--json", "--no-index", "--tier", "all"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tier"] == "all" and data["deferred_candidates"] == 0
