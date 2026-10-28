"""A dev turn's follow-ups land on the Register as records and in one artifacts commit, so the code repos stay clean."""
from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from ostler import Ostler, doctor
from ostler.model import load
from pydantic import ValidationError
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.pyflow.blueprint import node_spec
from workhorse_workflows.coder.shared.backlog import close_fix_item, file_follow_up_backlog, seed_fix_story
from workhorse_workflows.coder.shared.schemas.dev_story import FollowUp
from workhorse_workflows.coder.shared.story_commit import check_repos_clean

AREA = "billing"
PATTERN = "extract-module"


def _follow_up(title: str, reason: str = "the slice works without it", **over: object) -> FollowUp:
    fields: dict[str, object] = {"title": title, "reason": reason, "area": AREA, "pattern": PATTERN}
    return FollowUp.model_validate({**fields, **over})


@pytest.fixture(autouse=True)
def _agents_dir_is_ignored(repo: Path, git: Callable[..., subprocess.CompletedProcess]) -> None:
    """Ostler pins its id prefix under `.agents/`, which a real repository ignores."""
    (repo / ".gitignore").write_text(".agents/\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore the agents dir")


@pytest.fixture
def artifacts() -> Path:
    """The artifacts dir of this test, already a git repository with one commit."""
    root = core_config.ensure_artifacts_repo()
    subprocess.run(["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    return root


def _subjects(root: Path) -> list[str]:
    return subprocess.run(
        ["git", "-C", str(root), "log", "--format=%s"], capture_output=True, text=True, check=True
    ).stdout.splitlines()


def _folders(artifacts: Path) -> list[str]:
    return sorted(
        p.parent.relative_to(artifacts / "backlogs").as_posix()
        for p in (artifacts / "backlogs").glob("*/*/*/record.md")
    )


def _file_open(repo: Path, summary: str, record_id: str, repo_name: str = "acme") -> None:
    filing = Ostler(repo).file_record(
        repo=repo_name, area=AREA, pattern=PATTERN, summary=summary, filed_by="coder",
        record_id=record_id,
    )
    assert filing.ok, filing


def test_the_filer_is_a_node_a_flow_can_call() -> None:
    assert node_spec(file_follow_up_backlog)


def test_the_filed_follow_ups_are_committed_to_the_artifacts_repo_and_leave_the_code_repo_clean(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    head = git(repo, "rev-parse", "HEAD").stdout

    drained = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[_follow_up("Clear the cache on sign-out"), _follow_up("Paginate the report list", area="reports")],
        repo_dir=str(repo),
    )

    assert drained.appended == 2, drained
    folders = _folders(artifacts)
    assert [f.rsplit("/", 1)[0] for f in folders] == ["acme/billing", "acme/reports"], folders
    assert _subjects(artifacts) == ["init"]
    assert git(repo, "rev-parse", "HEAD").stdout == head
    assert git(repo, "status", "--porcelain").stdout == ""
    assert not (repo / "docs").exists()
    assert check_repos_clean(logger, story_slug="acme-story", repo_dir=str(repo)).clean is True


def test_a_record_carries_what_the_proposal_said_and_an_id_ostler_minted(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
) -> None:
    file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[_follow_up(
            "  Clear the cache\n on sign-out ", "it goes stale", symbols=["cache.py", "Session.close"]
        )],
        repo_dir=str(repo),
    )

    (record,) = Ostler(repo).records().records
    assert (record.repo, record.area, record.pattern) == ("acme", AREA, PATTERN)
    assert (record.filed_by, record.source_story, record.status) == ("coder", "acme-story", "open")
    assert record.summary == "Clear the cache on sign-out"
    assert record.body == "it goes stale"
    assert record.symbols == ["cache.py", "Session.close"]
    assert record.id.startswith("ACME-") and len(record.id) > len("acme-story-12345678")
    assert (artifacts / "backlogs/acme/billing" / record.id / "record.md").is_file()


def test_nothing_filed_commits_nothing(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    head = git(repo, "rev-parse", "HEAD").stdout

    drained = file_follow_up_backlog(
        logger, parent="acme-story", follow_ups=[_follow_up("", "no title")], repo_dir=str(repo)
    )

    assert drained.appended == 0, drained
    assert _subjects(artifacts) == ["init"]
    assert _folders(artifacts) == []
    assert git(repo, "rev-parse", "HEAD").stdout == head


@pytest.mark.parametrize("area", ["", "api/internal/core/calculation/compile.go", "Billing"])
def test_a_follow_up_whose_area_is_not_one_kebab_word_fails_the_turn_s_result(area: str) -> None:
    with pytest.raises(ValidationError, match="area"):
        _follow_up("Warm the cache", area=area)


@pytest.mark.parametrize("over", [{"pattern": ""}])
def test_a_follow_up_without_a_pattern_is_refused_with_a_reason(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
    caplog: pytest.LogCaptureFixture,
    over: dict[str, str],
) -> None:
    with caplog.at_level("INFO"):
        drained = file_follow_up_backlog(
            logger, parent="acme-story", follow_ups=[_follow_up("Warm the cache", **over)], repo_dir=str(repo)
        )

    assert (drained.appended, drained.skipped) == (0, 1), drained
    assert _folders(artifacts) == [] and _subjects(artifacts) == ["init"]
    assert any("Warm the cache" in r.getMessage() and next(iter(over)) in r.getMessage() for r in caplog.records)


HAND_FILED_SUMMARY = "Sign-out leaves the saved report snapshots in the browser."
HAND_FILED_ID = "clear-report-snapshots-on-sign-out"


def test_a_follow_up_that_cites_an_open_record_is_not_filed_again(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _file_open(repo, HAND_FILED_SUMMARY, HAND_FILED_ID)
    before = _folders(artifacts)

    with caplog.at_level("INFO"):
        drained = file_follow_up_backlog(
            logger,
            parent="acme-story",
            follow_ups=[_follow_up(
                "Wipe stored snapshots when the user leaves", f"It is on the register as [{HAND_FILED_ID}]."
            )],
            repo_dir=str(repo),
        )

    assert drained.appended == 0, drained
    assert _folders(artifacts) == before
    assert _subjects(artifacts) == ["init"]
    assert any(HAND_FILED_ID in r.getMessage() for r in caplog.records)


def test_a_follow_up_one_word_off_an_open_record_id_is_not_filed_again(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
) -> None:
    _file_open(repo, HAND_FILED_SUMMARY, HAND_FILED_ID)

    drained = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[_follow_up("Clear saved report snapshots on sign-out")],
        repo_dir=str(repo),
    )

    assert drained.appended == 0, drained
    assert _subjects(artifacts) == ["init"]


def test_a_follow_up_filed_earlier_under_another_reason_is_not_filed_again(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
) -> None:
    title = "Return a 404 for an unknown report"

    first = file_follow_up_backlog(
        logger, parent="acme-story", follow_ups=[_follow_up(title, "today it answers 400")], repo_dir=str(repo)
    )
    again = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[_follow_up(title, "a missing report answers 400 today")],
        repo_dir=str(repo),
    )

    assert first.appended == 1, first
    assert again.appended == 0, again
    assert len(_folders(artifacts)) == 1
    assert _subjects(artifacts) == ["init"]


def test_a_batch_files_a_repeated_follow_up_once_and_a_distinct_one_still(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
) -> None:
    drained = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[
            _follow_up("Paginate the report list", "long lists load slowly"),
            _follow_up("Paginate the report list", "a long list is slow to load"),
            _follow_up("Clear the export cache on sign-in", "a stale export can show"),
        ],
        repo_dir=str(repo),
    )

    assert drained.appended == 2, drained
    summaries = sorted(r.summary for r in Ostler(repo).records().records)
    assert summaries == ["Clear the export cache on sign-in", "Paginate the report list"]
    assert len(_subjects(artifacts)) == 1


def test_a_closed_record_does_not_hold_back_the_same_title(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
) -> None:
    filing = Ostler(repo).file_record(
        repo="acme", area=AREA, pattern=PATTERN, summary="Warm the cache", filed_by="coder", status="done"
    )
    assert filing.ok, filing

    drained = file_follow_up_backlog(
        logger, parent="acme-story", follow_ups=[_follow_up("Warm the cache")], repo_dir=str(repo)
    )

    assert drained.appended == 1, drained


def test_a_bookkeeping_commit_is_not_refused_by_the_repository_hooks(
    repo: Path,
    artifacts: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """A hook that judges the whole working tree, such as a rendered-skill drift check, has nothing to say about the records the workflow wrote, and a refusal would end the run."""
    _file_open(repo, "Clear the cache on sign-out", "acme-cache")
    for root in (repo, artifacts):
        hook = root / git(root, "rev-parse", "--git-path", "hooks/pre-commit").stdout.strip()
        hook.parent.mkdir(parents=True, exist_ok=True)
        write(hook, f"#!{sys.executable}\nimport sys\nsys.exit(1)\n")
        hook.chmod(0o755)

    drained = file_follow_up_backlog(
        logger, parent="acme-story", follow_ups=[_follow_up("Warm the cache", "")], repo_dir=str(repo)
    )
    closed = close_fix_item(logger, "acme-cache", {"acme": "0123456789abcdef"}, repo_dir=str(repo))

    assert drained.appended == 1, drained
    assert closed.closed is True, closed
    assert _subjects(artifacts) == ["init"]
    assert git(repo, "log", "-1", "--format=%s").stdout.strip() == "ignore the agents dir"
    assert check_repos_clean(logger, story_slug="acme-story", repo_dir=str(repo)).clean is True


@pytest.fixture
def two_repos(
    tmp_path: Path,
    name_workspace: Callable[[dict[str, Path]], None],
) -> dict[str, Path]:
    """A workspace of two code repos, `api-service` and `web-app`."""
    repos = {name: tmp_path / "ws" / name for name in ("api-service", "web-app")}
    for path in repos.values():
        path.mkdir(parents=True)
    name_workspace(repos)
    return repos


def test_a_follow_up_is_shelved_under_the_repository_it_names(
    repo: Path,
    artifacts: Path,
    two_repos: dict[str, Path],
    logger: logging.Logger,
) -> None:
    drained = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[_follow_up("Widen the form API", repo="web-app"), _follow_up("Clear the cache", repo="api-service")],
        repo_dir=str(repo),
        workspace="acme",
    )

    assert drained.appended == 2, drained
    assert [f.split("/")[0] for f in _folders(artifacts)] == ["api-service", "web-app"]
    assert len(_subjects(artifacts)) == 1
    assert all(not any(p.iterdir()) for p in two_repos.values())


def test_a_follow_up_naming_no_repository_of_a_two_repo_workspace_is_refused_with_the_known_names(
    repo: Path,
    artifacts: Path,
    two_repos: dict[str, Path],
    logger: logging.Logger,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO"):
        drained = file_follow_up_backlog(
            logger,
            parent="acme-story",
            follow_ups=[_follow_up("Widen the form API"), _follow_up("Clear the cache", repo="globex-site")],
            repo_dir=str(repo),
            workspace="acme",
        )

    assert (drained.appended, drained.skipped) == (0, 2), drained
    assert _folders(artifacts) == [] and _subjects(artifacts) == ["init"]
    messages = [r.getMessage() for r in caplog.records]
    assert any("Widen the form API" in m and "api-service" in m and "web-app" in m for m in messages), messages


def test_a_follow_up_naming_no_repository_of_a_one_repo_workspace_takes_the_only_one(
    repo: Path,
    artifacts: Path,
    tmp_path: Path,
    name_workspace: Callable[[dict[str, Path]], None],
    logger: logging.Logger,
) -> None:
    only = tmp_path / "ws" / "api-service"
    only.mkdir(parents=True)
    name_workspace({"api-service": only})

    drained = file_follow_up_backlog(
        logger, parent="acme-story", follow_ups=[_follow_up("Widen the form API")], repo_dir=str(repo),
        workspace="acme",
    )

    assert drained.appended == 1, drained
    assert [f.split("/")[0] for f in _folders(artifacts)] == ["api-service"]


def test_the_same_title_in_another_repository_is_a_different_cause(
    repo: Path,
    artifacts: Path,
    two_repos: dict[str, Path],
    logger: logging.Logger,
) -> None:
    _file_open(repo, "Widen the form API", "acme-widen-form", repo_name="api-service")

    drained = file_follow_up_backlog(
        logger, parent="acme-story", follow_ups=[_follow_up("Widen the form API", repo="web-app")],
        repo_dir=str(repo), workspace="acme",
    )

    assert drained.appended == 1, drained
    assert sorted(f.split("/")[0] for f in _folders(artifacts)) == ["api-service", "web-app"]


def test_the_fixes_bucket_the_coder_creates_needs_no_milestone(
    repo: Path,
    logger: logging.Logger,
) -> None:
    assert Ostler(repo).create_milestone("mvp", "MVP").ok

    seeded = seed_fix_story(
        logger,
        record_id="acme-cache",
        summary="Clear the cache on sign-out",
        repo_dir=str(repo),
        repo="acme",
        area=AREA,
    )

    graph = load(repo)
    bucket = next(epic for epic in graph.epics if epic.name == seeded.epic)
    assert bucket.followups is True
    unowned = [f.ref for f in doctor.run(graph).findings if f.code == "epic-without-milestone"]
    assert unowned == [], unowned


def test_the_fix_story_seed_names_the_record_it_came_from(
    repo: Path,
    logger: logging.Logger,
) -> None:
    assert Ostler(repo).create_milestone("mvp", "MVP").ok

    seeded = seed_fix_story(
        logger,
        record_id="acme-cache",
        summary="Clear the cache on sign-out",
        repo_dir=str(repo),
        repo="acme",
        area=AREA,
    )

    seeds = Ostler(repo).list("seed", epic=seeded.epic)
    assert [s["sourceRecord"] for s in seeds if s["id"] == "acme-cache"] == ["acme-cache"]
