"""The fix lane draws the oldest open `qa` record of the workspace and closes it once the fix has landed."""
from __future__ import annotations

import logging
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from ostler import Ostler
from ostler.register import FiledBy, Record, Status
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.pyflow.blueprint import node_spec
from workhorse_workflows.coder.shared.backlog import already_fixed, close_fix_item, select_fix_item

OLD = "ACME-01J00000000000000000000001"
NEWER = "ACME-01J00000000000000000000002"
NEWEST = "ACME-01J00000000000000000000003"


@pytest.fixture
def artifacts() -> Path:
    root = core_config.ensure_artifacts_repo()
    subprocess.run(["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    return root


def _file(
    repo: Path,
    record_id: str,
    *,
    repo_name: str = "acme",
    filed_by: FiledBy = "qa",
    status: Status = "open",
    body: str = "",
) -> None:
    filing = Ostler(repo).file_record(
        repo=repo_name, area="cart", pattern="guard-the-total", summary=f"summary of {record_id}",
        filed_by=filed_by, record_id=record_id, status=status, body=body,
    )
    assert filing.record is not None, filing.message


def _record(repo: Path, record_id: str) -> Record:
    [found] = [r for r in Ostler(repo).records().records if r.id == record_id]
    return found


def test_the_pick_and_the_close_are_nodes_a_flow_can_call() -> None:
    assert node_spec(select_fix_item)
    assert node_spec(close_fix_item)


def test_the_oldest_minted_record_is_drawn_first(repo: Path, artifacts: Path, logger: logging.Logger) -> None:
    _file(repo, NEWEST)
    _file(repo, OLD, body="Why it is wrong.")
    _file(repo, NEWER)

    pick = select_fix_item(logger, repo_dir=str(repo))

    assert pick.has_fix, pick
    assert (pick.record_id, pick.summary) == (OLD, f"summary of {OLD}")
    assert (pick.repo, pick.area, pick.body) == ("acme", "cart", "Why it is wrong.")


def test_an_imported_record_with_no_ulid_sorts_before_every_minted_one(
    repo: Path, artifacts: Path, logger: logging.Logger
) -> None:
    _file(repo, OLD)
    _file(repo, "widget-pagination")
    _file(repo, "acme-cache")

    first = select_fix_item(logger, repo_dir=str(repo))
    assert first.record_id == "acme-cache"

    Ostler(repo).close_record("acme-cache", "done", "shipped")
    second = select_fix_item(logger, repo_dir=str(repo))
    assert second.record_id == "widget-pagination"

    Ostler(repo).close_record("widget-pagination", "done", "shipped")
    assert select_fix_item(logger, repo_dir=str(repo)).record_id == OLD


@pytest.mark.parametrize("filed_by", ["coder", "person", "qa-deferred", "survey", "parity"])
def test_a_record_another_filer_holds_is_never_drawn(
    repo: Path, artifacts: Path, logger: logging.Logger, filed_by: FiledBy
) -> None:
    _file(repo, OLD, filed_by=filed_by)

    pick = select_fix_item(logger, repo_dir=str(repo))

    assert not pick.has_fix
    assert pick.reason


@pytest.mark.parametrize("status", ["done", "dropped", "promoted"])
def test_a_closed_record_is_never_drawn(repo: Path, artifacts: Path, logger: logging.Logger, status: Status) -> None:
    _file(repo, OLD, status=status)

    assert not select_fix_item(logger, repo_dir=str(repo)).has_fix


def test_a_record_of_a_repository_outside_the_workspace_is_not_drawn(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
    tmp_path: Path,
    name_workspace: Callable[[dict[str, Path]], None],
) -> None:
    repos = {name: tmp_path / "ws" / name for name in ("api-service", "web-app")}
    for path in repos.values():
        path.mkdir(parents=True)
    name_workspace(repos)
    _file(repo, OLD, repo_name="mobile-app")
    _file(repo, NEWER, repo_name="web-app")

    pick = select_fix_item(logger, repo_dir=str(repo), workspace="acme")

    assert pick.record_id == NEWER
    assert pick.repo == "web-app"


def test_an_empty_register_gives_no_fix(repo: Path, artifacts: Path, logger: logging.Logger) -> None:
    pick = select_fix_item(logger, repo_dir=str(repo))

    assert pick.has_fix is False
    assert pick.reason


def test_closing_marks_the_record_done_with_each_repos_commit_in_the_reason(
    repo: Path, artifacts: Path, logger: logging.Logger
) -> None:
    _file(repo, OLD)
    sha = "0123456789abcdef0123456789abcdef01234567"

    closed = close_fix_item(logger, OLD, {"api": sha, "web": "fedcba9876543210fedcba9876543210fedcba98"}, repo_dir=str(repo))

    assert (closed.closed, closed.record_id) == (True, OLD), closed
    record = _record(repo, OLD)
    assert record.status == "done"
    assert record.reason == "fixed in api@0123456, web@fedcba9"
    subjects = subprocess.run(
        ["git", "-C", str(artifacts), "log", "--format=%s"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert subjects == ["init"]


def test_closing_twice_is_a_no_op_that_succeeds(repo: Path, artifacts: Path, logger: logging.Logger) -> None:
    _file(repo, OLD)
    close_fix_item(logger, OLD, {"api": "0123456789abcdef"}, repo_dir=str(repo))
    commits_before = subprocess.run(
        ["git", "-C", str(artifacts), "rev-list", "--count", "HEAD"], capture_output=True, text=True, check=True
    ).stdout

    again = close_fix_item(logger, OLD, {"api": "0123456789abcdef"}, repo_dir=str(repo))

    assert again.closed is True, again
    after = subprocess.run(
        ["git", "-C", str(artifacts), "rev-list", "--count", "HEAD"], capture_output=True, text=True, check=True
    ).stdout
    assert after == commits_before


def test_closing_an_unknown_record_is_reported_not_raised(
    repo: Path, artifacts: Path, logger: logging.Logger
) -> None:
    closed = close_fix_item(logger, "no-such-record", {"api": "0123456"}, repo_dir=str(repo))

    assert closed.closed is False
    assert "no-such-record" in closed.reason


def _ulid_at(seconds: int) -> str:
    millis = seconds * 1000
    digits = []
    for _ in range(10):
        millis, rem = divmod(millis, 32)
        digits.append("0123456789ABCDEFGHJKMNPQRSTVWXYZ"[rem])
    return "".join(reversed(digits)) + "0" * 16


def _touch(repo: Path, name: str, when: int) -> str:
    (repo / name).write_text(f"{when}\n", encoding="utf-8")
    env = {"GIT_AUTHOR_DATE": f"@{when} +0000", "GIT_COMMITTER_DATE": f"@{when} +0000"}
    subprocess.run(["git", "-C", str(repo), "add", name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", f"touch {name}"], check=True, env={**os.environ, **env})
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _file_with(repo: Path, record_id: str, symbols: list[str]) -> None:
    filing = Ostler(repo).file_record(
        repo="acme", area="cart", pattern="guard-the-total", summary="s", filed_by="qa",
        record_id=record_id, symbols=symbols,
    )
    assert filing.record is not None, filing.message


def test_a_commit_after_the_filing_that_touches_a_symbol_is_the_evidence(
    repo: Path, artifacts: Path, logger: logging.Logger
) -> None:
    filed = int(time.time()) - 10_000
    record_id = f"ACME-{_ulid_at(filed)}"
    _file_with(repo, record_id, ["cart.go"])
    sha = _touch(repo, "cart.go", filed + 100)

    evidence = already_fixed(logger, record_id, repo_dir=str(repo))

    assert (evidence.found, evidence.repo, evidence.sha) == (True, "acme", sha), evidence


def test_a_commit_that_predates_the_filing_is_no_evidence(
    repo: Path, artifacts: Path, logger: logging.Logger
) -> None:
    filed = int(time.time()) - 10_000
    record_id = f"ACME-{_ulid_at(filed)}"
    _file_with(repo, record_id, ["cart.go"])
    _touch(repo, "cart.go", filed - 100)

    assert already_fixed(logger, record_id, repo_dir=str(repo)).found is False


def test_a_record_naming_no_symbols_has_no_evidence(repo: Path, artifacts: Path, logger: logging.Logger) -> None:
    filed = int(time.time()) - 10_000
    record_id = f"ACME-{_ulid_at(filed)}"
    _file_with(repo, record_id, [])
    _touch(repo, "cart.go", filed + 100)

    assert already_fixed(logger, record_id, repo_dir=str(repo)).found is False


def test_a_close_prefix_leads_the_reason(repo: Path, artifacts: Path, logger: logging.Logger) -> None:
    _file(repo, OLD)

    close_fix_item(logger, OLD, {"api": "0123456789abcdef"}, repo_dir=str(repo), prefix="already fixed in")

    assert _record(repo, OLD).reason == "already fixed in api@0123456"
