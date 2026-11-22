"""A single-repo trial keeps its book in the repo, so the artifacts folder never has to hold it."""

from __future__ import annotations

from pathlib import Path

import yaml
from fakes import commit_all, fake_run, init_repo
from smoke import git

from ostler.milestones import BOOKS_DIR
from paddock.tasks import greenfield, replay

MILESTONE_FIXTURE = greenfield.Fixture(
    milestone="milestones/m1",
    decision_records="records",
    surfaces=(greenfield.Surface(service="api", service_root="api"),),
)


def book_of(repo: Path) -> dict:
    return yaml.safe_load((repo / "agents.yml").read_text(encoding="utf-8"))["book"]


def test_keep_book_in_repo_adds_the_key_and_keeps_other_lines(tmp_path: Path) -> None:
    (tmp_path / "agents.yml").write_text("repo:\n  id_prefix: X\npacks:\n  - one\n", encoding="utf-8")

    replay.keep_book_in_repo(tmp_path)

    text = (tmp_path / "agents.yml").read_text(encoding="utf-8")
    assert text.startswith("repo:\n  id_prefix: X\npacks:\n  - one\n")
    assert book_of(tmp_path) == {"home": "repo"}


def test_keep_book_in_repo_creates_the_file(tmp_path: Path) -> None:
    replay.keep_book_in_repo(tmp_path)

    assert book_of(tmp_path) == {"home": "repo"}


def test_keep_book_in_repo_replaces_another_home_and_keeps_the_other_book_keys(tmp_path: Path) -> None:
    (tmp_path / "agents.yml").write_text(
        "book:\n  home: artifacts\n  product: acme\nrepo:\n  id_prefix: X\n", encoding="utf-8"
    )

    replay.keep_book_in_repo(tmp_path)

    assert book_of(tmp_path) == {"home": "repo", "product": "acme"}
    assert "id_prefix: X" in (tmp_path / "agents.yml").read_text(encoding="utf-8")


def test_keep_book_in_repo_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "agents.yml").write_text("repo:\n  id_prefix: X\n", encoding="utf-8")

    replay.keep_book_in_repo(tmp_path)
    once = (tmp_path / "agents.yml").read_text(encoding="utf-8")
    replay.keep_book_in_repo(tmp_path)

    assert (tmp_path / "agents.yml").read_text(encoding="utf-8") == once
    assert once.count("home:") == 1


def test_a_single_repo_replay_checkout_stages_the_book_in_the_repo(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    data = init_repo(run.data, {"agents.yml": "repo: {}\npacks:\n  - one\n", "app.py": "x = 1\n"})
    (data / "app.py").write_text("x = 2\n", encoding="utf-8")
    commit = commit_all(data, "later")
    git(tmp_path, "clone", "--quiet", str(data), str(run.stage))
    run.scratch.mkdir()
    pin = replay.Pin("S-1", {"docs": commit})

    dest = replay.checkout(
        run, replay.Fixture(app="x", pins=(pin,)), pin, "docs", tmp_path / "trial" / "x", lambda _repo: None
    )

    assert book_of(dest) == {"home": "repo"}
    assert "packs:" in (dest / "agents.yml").read_text(encoding="utf-8")


def test_a_single_repo_greenfield_seed_stages_the_book_in_the_repo(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    (run.stage / "docs").mkdir()
    (run.stage / "agents.yml").write_text("repo:\n  id_prefix: X\n", encoding="utf-8")
    milestone = run.benchmark.root / "milestones" / "m1"
    milestone.mkdir(parents=True)
    (milestone / greenfield.MILESTONE_FILE).write_text("# m\n", encoding="utf-8")

    greenfield.seed_milestone(run, MILESTONE_FIXTURE)

    assert book_of(run.stage) == {"home": "repo"}
    assert (run.stage / BOOKS_DIR / "api" / "service.py").is_file()
