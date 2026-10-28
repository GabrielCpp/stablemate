"""The person Producer: ``ostler backlog add`` and ``ostler create backlog-item`` file a record on the untracked backlogs shelf and commit nothing."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ostler import register
from ostler.api import Ostler
from ostler.cli import main
from ostler.model import load


def run(root: Path, *argv: str) -> int:
    return main(["-C", str(root), *argv])


def artifacts() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve()


def git(*argv: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(artifacts()), *argv],
        capture_output=True, text=True, check=True, timeout=30,
    )
    return done.stdout


def subjects() -> list[str]:
    if not (artifacts() / ".git").exists():
        return []
    try:
        return git("log", "--format=%s").splitlines()
    except subprocess.CalledProcessError:
        return []


def test_backlog_add_files_a_person_record_and_commits_nothing(tmp_path: Path, capsys) -> None:
    code = run(
        tmp_path, "backlog", "add", "Extract the invoice rounding rules",
        "--repo", "api-service", "--area", "billing", "--symbol", "billing/rounding.py",
        "--symbol", "Invoice.total", "--body", "The slice worked without it.",
        "--prefix", "acme", "--json",
    )

    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["id"].startswith("acme-")
    read = register.records(load(tmp_path)).records
    assert [(r.id, r.repo, r.area, r.pattern, r.filed_by, r.status) for r in read] == [
        (out["id"], "api-service", "billing", "untriaged", "person", "open")]
    assert read[0].symbols == ["billing/rounding.py", "Invoice.total"]
    assert read[0].body == "The slice worked without it."
    assert subjects() == []
    assert not (tmp_path / "docs").exists()


def test_backlog_add_keeps_a_given_id_and_a_given_pattern(tmp_path: Path) -> None:
    assert run(tmp_path, "backlog", "add", "Widen the form API", "--repo", "web-app",
               "--area", "ui", "--pattern", "widen-api", "--id", "BL-77") == 0

    [only] = register.records(load(tmp_path)).records
    assert (only.id, only.pattern) == ("BL-77", "widen-api")
    assert subjects() == []


def test_create_backlog_item_files_the_same_record(tmp_path: Path, capsys) -> None:
    code = run(tmp_path, "create", "backlog-item", "Ship draft recovery",
               "--repo", "web-app", "--area", "drafts", "--prefix", "acme", "--json")

    assert code == 0
    out = json.loads(capsys.readouterr().out)
    [only] = register.records(load(tmp_path)).records
    assert only.id == out["id"] and only.filed_by == "person" and only.pattern == "untriaged"
    assert len(only.id.split("-", 1)[1]) == 26
    assert subjects() == []


@pytest.mark.parametrize("argv", [
    ("Extract it", "--repo", "Api Service", "--area", "billing"),
    ("Extract it", "--repo", "api-service", "--area", "billing/rounding"),
    ("Extract it", "--repo", "api-service", "--area", ""),
    ("  ", "--repo", "api-service", "--area", "billing"),
    ("two\nlines", "--repo", "api-service", "--area", "billing"),
])
@pytest.mark.parametrize("verb", [("backlog", "add"), ("create", "backlog-item")])
def test_a_refused_record_exits_non_zero_with_the_reason_and_files_nothing(
    tmp_path: Path, capsys, verb: tuple[str, str], argv: tuple[str, ...],
) -> None:
    code = run(tmp_path, *verb, *argv)

    assert code == 1
    assert "invalid record" in capsys.readouterr().out
    assert register.records(load(tmp_path)).records == ()
    assert subjects() == []


def test_a_taken_id_is_refused_and_the_shelf_keeps_the_first_record(tmp_path: Path, capsys) -> None:
    assert run(tmp_path, "backlog", "add", "First", "--repo", "api-service",
               "--area", "billing", "--id", "BL-1") == 0
    capsys.readouterr()

    code = run(tmp_path, "backlog", "add", "Second", "--repo", "web-app",
               "--area", "ui", "--id", "BL-1")

    assert code == 1
    printed = capsys.readouterr().out
    assert "BL-1" in printed and "already taken" in printed
    [only] = register.records(load(tmp_path)).records
    assert only.summary == "First"
    assert subjects() == []


def test_a_filing_without_repo_or_area_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        run(tmp_path, "backlog", "add", "Something")

    assert exc.value.code == 2


def test_the_facade_files_a_person_record_and_commits_nothing(tmp_path: Path) -> None:
    okf = Ostler(tmp_path)

    result = okf.create_backlog_item("Ship draft recovery", repo="web-app", area="drafts", prefix="acme")

    assert result.ok and result.entity_id.startswith("acme-")
    assert [r.id for r in okf.records().records] == [result.entity_id]
    assert subjects() == []


def test_filing_leaves_the_shelf_out_of_git(tmp_path: Path) -> None:
    graph = load(tmp_path)
    filing = register.file_record(graph, repo="api-service", area="billing", pattern="x",
                                  summary="Mine", filed_by="person", record_id="BL-1")

    assert filing.ok and filing.path is not None
    assert subjects() == []
    assert "BL-1" not in git("status", "--porcelain", "-uall")
    assert git("check-ignore", "backlogs/api-service/billing/BL-1/record.md").strip()
