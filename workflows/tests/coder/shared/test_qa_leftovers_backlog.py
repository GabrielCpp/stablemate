"""The items a story's QA left over land on the register as `qa` records, one artifacts commit per drain."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from ostler import Ostler
from ostler.register import Record
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.pyflow.blueprint import node_spec
from workhorse_workflows.coder.shared.backlog import file_backlog_items, filed_backlog
from workhorse_workflows.coder.shared.docs import CONTEXT_FILE

ITEMS = "backlog-items.json"


def _spec(tmp_path: Path, *items: dict, story: str = "ACME-1") -> str:
    spec = tmp_path / "specs" / story
    spec.mkdir(parents=True, exist_ok=True)
    (spec / CONTEXT_FILE).write_text(json.dumps({"story": {"id": story}}), encoding="utf-8")
    (spec / ITEMS).write_text(json.dumps(list(items)), encoding="utf-8")
    return str(spec)


def _item(item_id: str, description: str, **fields: object) -> dict:
    return {
        "id": item_id,
        "description": description,
        "repo": "acme",
        "area": "cart",
        "pattern": "guard-the-total",
        "symbols": ["cart/total.go"],
    } | fields


@pytest.fixture(autouse=True)
def _agents_dir_is_ignored(repo: Path, git: Callable[..., subprocess.CompletedProcess]) -> None:
    (repo / ".gitignore").write_text(".agents/\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore the agents dir")


@pytest.fixture
def artifacts() -> Path:
    root = core_config.ensure_artifacts_repo()
    subprocess.run(["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    return root


@pytest.fixture
def two_repos(tmp_path: Path, name_workspace: Callable[[dict[str, Path]], None]) -> dict[str, Path]:
    repos = {name: tmp_path / "ws" / name for name in ("api-service", "web-app")}
    for path in repos.values():
        path.mkdir(parents=True)
    name_workspace(repos)
    return repos


def _subjects(root: Path) -> list[str]:
    return subprocess.run(
        ["git", "-C", str(root), "log", "--format=%s"], capture_output=True, text=True, check=True
    ).stdout.splitlines()


def _records(repo: Path) -> list[Record]:
    return list(Ostler(repo).records().records)


def test_the_leftovers_are_nodes_a_flow_can_call() -> None:
    assert node_spec(filed_backlog)
    assert node_spec(file_backlog_items)


def test_each_item_becomes_a_qa_record_in_one_artifacts_commit(
    repo: Path, tmp_path: Path, artifacts: Path, logger: logging.Logger, git: Callable[..., subprocess.CompletedProcess]
) -> None:
    head = git(repo, "rev-parse", "HEAD").stdout
    spec = _spec(
        tmp_path,
        _item("cart-total-overflow", "The cart total overflows past 2^31 cents."),
        _item(
            "cart-empty-state",
            "The empty cart renders a blank page.\nIt should say the cart is empty.",
            area="Cart UI",
            pattern="",
            symbols=[],
        ),
    )

    drained = file_backlog_items(logger, spec_dir=spec, repo_dir=str(repo))

    assert (drained.appended, drained.skipped) == (2, 0), drained
    by_summary = {r.summary: r for r in _records(repo)}
    overflow = by_summary["The cart total overflows past 2^31 cents."]
    assert (overflow.repo, overflow.area, overflow.pattern, overflow.symbols) == (
        "acme", "cart", "guard-the-total", ["cart/total.go"])
    assert (overflow.filed_by, overflow.status, overflow.source_story, overflow.body) == (
        "qa", "open", "ACME-1", "")
    assert overflow.id != "cart-total-overflow"
    empty = by_summary["The empty cart renders a blank page."]
    assert (empty.area, empty.pattern) == ("cart-ui", "untriaged")
    assert empty.body == "The empty cart renders a blank page.\nIt should say the cart is empty."
    assert _subjects(artifacts) == ["init"]
    assert git(repo, "rev-parse", "HEAD").stdout == head
    assert git(repo, "status", "--porcelain").stdout == ""
    assert not (tmp_path / "specs" / "ACME-1" / ITEMS).exists()


def test_a_dropped_item_is_not_filed(
    repo: Path, tmp_path: Path, artifacts: Path, logger: logging.Logger
) -> None:
    spec = _spec(tmp_path, _item("kept", "Keep this one."), _item("gone", "A judge said this was already held."))

    drained = file_backlog_items(logger, spec_dir=spec, repo_dir=str(repo), drop=["gone"])

    assert (drained.appended, drained.skipped) == (1, 1), drained
    assert [r.summary for r in _records(repo)] == ["Keep this one."]


def test_an_item_that_restates_an_open_qa_record_is_skipped(
    repo: Path, tmp_path: Path, artifacts: Path, logger: logging.Logger
) -> None:
    Ostler(repo).file_record(
        repo="acme", area="cart", pattern="guard-the-total", summary="The cart total   overflows!", filed_by="qa"
    )
    spec = _spec(
        tmp_path,
        _item("a", "the cart total overflows"),
        _item("b", "Another cause entirely."),
        _item("c", "Another cause, entirely"),
    )

    drained = file_backlog_items(logger, spec_dir=spec, repo_dir=str(repo))

    assert (drained.appended, drained.skipped) == (1, 2), drained
    assert sorted(r.summary for r in _records(repo)) == ["Another cause entirely.", "The cart total   overflows!"]


def test_a_closed_record_does_not_make_a_new_item_a_duplicate(
    repo: Path, tmp_path: Path, artifacts: Path, logger: logging.Logger
) -> None:
    filing = Ostler(repo).file_record(
        repo="acme", area="cart", pattern="guard-the-total", summary="The cart total overflows", filed_by="qa",
        status="done",
    )
    assert filing.record is not None

    drained = file_backlog_items(logger, spec_dir=_spec(tmp_path, _item("a", "The cart total overflows")), repo_dir=str(repo))

    assert drained.appended == 1, drained


def test_a_record_another_filer_holds_is_not_a_duplicate(
    repo: Path, tmp_path: Path, artifacts: Path, logger: logging.Logger
) -> None:
    Ostler(repo).file_record(
        repo="acme", area="cart", pattern="guard-the-total", summary="The cart total overflows", filed_by="coder"
    )

    drained = file_backlog_items(logger, spec_dir=_spec(tmp_path, _item("a", "The cart total overflows")), repo_dir=str(repo))

    assert drained.appended == 1, drained


def test_a_two_repo_workspace_places_each_item_by_its_repo(
    repo: Path, tmp_path: Path, artifacts: Path, logger: logging.Logger, two_repos: dict[str, Path]
) -> None:
    spec = _spec(
        tmp_path,
        _item("a", "The api drops a header.", repo="api-service"),
        _item("b", "The web app drops a click.", repo="web-app"),
    )

    drained = file_backlog_items(logger, spec_dir=spec, repo_dir=str(repo), workspace="acme")

    assert drained.appended == 2, drained
    assert {(r.repo, r.summary) for r in _records(repo)} == {
        ("api-service", "The api drops a header."),
        ("web-app", "The web app drops a click."),
    }
    assert _subjects(artifacts) == ["init"]


def test_an_item_no_repository_of_the_workspace_owns_is_refused_and_logged(
    repo: Path,
    tmp_path: Path,
    artifacts: Path,
    logger: logging.Logger,
    two_repos: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = _spec(tmp_path, _item("a", "Lost item.", repo="mobile-app"), _item("b", "Placed item.", repo="web-app"))

    with caplog.at_level("INFO"):
        drained = file_backlog_items(logger, spec_dir=spec, repo_dir=str(repo), workspace="acme")

    assert (drained.appended, drained.skipped) == (1, 1), drained
    assert [r.summary for r in _records(repo)] == ["Placed item."]
    messages = [r.getMessage() for r in caplog.records]
    assert any("Lost item." in m and "api-service" in m and "web-app" in m for m in messages), messages


def test_nothing_filed_commits_nothing_and_still_clears_the_items(
    repo: Path, tmp_path: Path, artifacts: Path, logger: logging.Logger
) -> None:
    spec = _spec(tmp_path, _item("a", "Dropped one."))

    drained = file_backlog_items(logger, spec_dir=spec, repo_dir=str(repo), drop=["a"])

    assert drained.appended == 0, drained
    assert _subjects(artifacts) == ["init"]
    assert not (tmp_path / "specs" / "ACME-1" / ITEMS).exists()


def test_filed_lists_the_open_qa_records_of_the_workspace_repos_and_the_pending_items(
    repo: Path, tmp_path: Path, artifacts: Path, logger: logging.Logger, two_repos: dict[str, Path]
) -> None:
    okf = Ostler(repo)
    held = okf.file_record(repo="web-app", area="a", pattern="p", summary="Held by qa", filed_by="qa")
    okf.file_record(repo="web-app", area="a", pattern="p", summary="Held by coder", filed_by="coder")
    okf.file_record(repo="web-app", area="a", pattern="p", summary="Closed by qa", filed_by="qa", status="done")
    okf.file_record(repo="elsewhere", area="a", pattern="p", summary="Other repo", filed_by="qa")
    assert held.record is not None
    spec = _spec(tmp_path, _item("Cart Total", "The cart total overflows.\nSecond line."))

    state = filed_backlog(logger, spec_dir=spec, repo_dir=str(repo), workspace="acme")

    assert state.filed == {held.record.id: "Held by qa"}
    assert state.items == {"cart-total": "The cart total overflows. Second line."}


def test_filed_with_no_register_and_no_items_is_empty(
    repo: Path, artifacts: Path, logger: logging.Logger
) -> None:
    state = filed_backlog(logger, spec_dir="", repo_dir=str(repo))

    assert (state.filed, state.items) == ({}, {})
