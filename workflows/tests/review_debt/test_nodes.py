"""The nodes of `review-debt`: the complete read and the trends writer."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from workhorse.pyflow.blueprint import node_spec

from review_debt.scripted import git_out
from workhorse_workflows.review_debt.nodes import read_register, write_trends
from workhorse_workflows.review_debt.schemas import Cluster, Singleton, TrendReport


def test_the_read_holds_every_status_in_every_repository(
    repo: Path, logger: logging.Logger, file_record: Callable[..., str]
) -> None:
    file_record("a-open", repo_name="api-service")
    file_record("b-done", repo_name="web-app", status="done")
    file_record("c-dropped", repo_name="web-app", area="nav", status="dropped")

    read = read_register(logger, repo_dir=str(repo))

    assert read.ids == ["a-open", "b-done", "c-dropped"], read
    assert len(read.listing) == 3
    assert read.listing[1].startswith("b-done\tweb-app\tcart\tdone\t"), read.listing
    assert read.shelf.endswith("backlogs"), read.shelf
    assert read.unreadable == []


def test_an_unreadable_record_is_carried_and_never_accounted(
    repo: Path, logger: logging.Logger, file_record: Callable[..., str]
) -> None:
    file_record("fine")
    broken = Path(read_register(logger, repo_dir=str(repo)).shelf) / "api-service" / "cart" / "broken"
    broken.mkdir(parents=True)
    (broken / "record.md").write_text("not a record\n", encoding="utf-8")

    read = read_register(logger, repo_dir=str(repo))

    assert read.ids == ["fine"], read
    assert read.unreadable == [str(broken / "record.md")], read


def test_a_file_at_the_shelf_root_is_never_read_as_a_record(
    repo: Path, logger: logging.Logger, file_record: Callable[..., str]
) -> None:
    file_record("fine")
    shelf = Path(read_register(logger, repo_dir=str(repo)).shelf)
    (shelf / "record.md").write_text("---\nid: stray\n---\n", encoding="utf-8")
    (shelf / "trends.md").write_text("# trends\n", encoding="utf-8")

    read = read_register(logger, repo_dir=str(repo))

    assert read.ids == ["fine"], read
    assert read.unreadable == [], read


def test_an_empty_shelf_reads_as_no_ids(repo: Path, artifacts: Path, logger: logging.Logger) -> None:
    read = read_register(logger, repo_dir=str(repo))

    assert (read.ids, read.listing, read.unreadable) == ([], [], [])


def test_a_dry_run_read_is_empty() -> None:
    stub = node_spec(read_register).stub
    assert stub is not None
    assert stub(logging.getLogger("x")).ids == []


def test_writing_the_same_report_twice_changes_once(
    repo: Path, artifacts: Path, logger: logging.Logger, file_record: Callable[..., str]
) -> None:
    file_record("one")
    file_record("two")
    read = read_register(logger, repo_dir=str(repo))
    report = TrendReport(
        clusters=[Cluster(name="n", cause="shared", ids=["one", "two"])], singletons=[], summary="s"
    )
    before = int(git_out(artifacts, "rev-list", "--count", "HEAD"))

    first = write_trends(logger, read, report, repo_dir=str(repo))
    second = write_trends(logger, read, report, repo_dir=str(repo))

    assert (first.changed, second.changed) == (True, False)
    assert int(git_out(artifacts, "rev-list", "--count", "HEAD")) == before


def test_the_rendered_file_is_the_same_text_for_the_same_report(
    repo: Path, artifacts: Path, logger: logging.Logger, file_record: Callable[..., str]
) -> None:
    file_record("one")
    file_record("two")
    read = read_register(logger, repo_dir=str(repo))
    report = TrendReport(
        clusters=[], singletons=[Singleton(id="two", cause="x"), Singleton(id="one", cause="y")], summary="s"
    )

    write_trends(logger, read, report, repo_dir=str(repo))
    text = (artifacts / "backlogs" / "trends.md").read_text(encoding="utf-8")

    assert text.index("- one ") < text.index("- two "), text
