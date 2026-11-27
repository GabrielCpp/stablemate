"""A book moved out of its repository by the guide's own commands is read from the artifacts folder and checks green."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from book_fakes import git as _git
from book_todo import FIXTURE, runtime
from conftest import write
from test_book_branch_cli import _commit
from test_book_home_resolution import MOVE_GUIDE, _artifacts, _ostler

PAGE = "date: 2026-11-22\n\nA todo is never listed twice.\n"


def _sh(folder: Path, command: str) -> str:
    done = subprocess.run(["bash", "-ec", command], cwd=folder, capture_output=True, text=True, check=False)
    assert done.returncode == 0, command + "\n" + done.stdout + done.stderr
    return done.stdout


def move_book(repo: Path, artifacts: Path, product: str) -> None:
    env = f'ARTIFACTS="{artifacts}"; PRODUCT="{product}"; NAME="{repo.name}"'
    assert _sh(repo, f'{env}; git -C "$ARTIFACTS" status --porcelain') == ""
    moved = _ostler(["book", "move", "--from", "services"], repo)
    assert moved.returncode == 0, moved.stdout + moved.stderr
    _sh(repo, f'{env}; mkdir -p "$ARTIFACTS/products/$PRODUCT" && cp product/*.md "$ARTIFACTS/products/$PRODUCT/"')
    _sh(repo, f'{env}; git -C "$ARTIFACTS" add services products')
    _sh(repo, f'{env}; git -C "$ARTIFACTS" commit --quiet -m "docs(book): move the $NAME book from its repository"')
    _sh(repo, f"{env}; git rm -r --quiet services product")
    _sh(repo, f'{env}; git commit --quiet -m "docs: move the book to the artifacts folder"')


def _acme(tmp_path: Path) -> Path:
    repo = tmp_path / "code" / "acme"
    shutil.copytree(FIXTURE, repo, ignore=shutil.ignore_patterns("__pycache__", "node_modules", "agents.yml"))
    write(repo / "agents.yml", "repo:\n  id_prefix: A\n")
    write(repo / "product" / "one-rule.md", PAGE)
    _git(repo, "init", "--quiet", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "init")
    return repo.resolve()


def _artifacts_repo() -> Path:
    folder = _artifacts()
    _git(folder, "init", "--quiet", "-b", "main")
    _git(folder, "add", "-A")
    _git(folder, "commit", "--quiet", "--allow-empty", "-m", "start")
    return folder


def _ostler_with_env(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    binary = Path(sys.executable).parent / "ostler"
    env = {**os.environ, **runtime(1)}
    return subprocess.run([str(binary), *arguments], cwd=cwd, env=env, capture_output=True, text=True, check=False)


def _merges(folder: Path) -> str:
    return _git(folder, "log", "--merges", "--format=%H").strip()


def test_an_in_repo_book_is_refused_before_the_move_and_checks_green_after(tmp_path):
    repo = _acme(tmp_path)
    artifacts = _artifacts_repo()
    refused = _ostler(["book", "search", "hello"], repo)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "home: repo" in refused.stderr
    assert MOVE_GUIDE in refused.stderr
    move_book(repo, artifacts, "acme")
    assert not (repo / "services").exists()
    assert (artifacts / "services" / "acme" / "api" / "service.py").is_file()
    assert 'owner="services.acme.api"' in (artifacts / "services" / "acme" / "web" / "foreign.py").read_text()
    for module in ("services.acme.api", "services.acme.web"):
        checked = _ostler_with_env(["book", "check", module, "--app", str(repo)], repo)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        assert "check: 0 findings" in checked.stdout
    paged = _ostler(["book", "pages"], repo)
    assert paged.returncode == 0, paged.stdout + paged.stderr
    assert "product  one-rule  2026-11-22" in paged.stdout
    assert (artifacts / "products" / "acme" / "one-rule.md").is_file()
    found = _ostler(["book", "search", "listed twice"], repo)
    assert found.returncode == 0, found.stdout + found.stderr
    assert "pages/product  products/acme/one-rule\n" in found.stdout
    assert _merges(repo) == ""
    assert _merges(artifacts) == ""


def test_a_pointer_is_checked_against_the_app_after_the_move(tmp_path):
    repo = _acme(tmp_path)
    artifacts = _artifacts_repo()
    move_book(repo, artifacts, "acme")
    (repo / "app.py").unlink()
    _git(repo, "rm", "--quiet", "--cached", "app.py")
    checked = _ostler_with_env(["book", "check", "services.acme.api", "--app", str(repo)], repo)
    assert checked.returncode != 0, checked.stdout + checked.stderr
    assert "app.py" in checked.stdout + checked.stderr


@pytest.fixture
def _trees(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(f'worktree_dir = "{tmp_path / "trees"}"\n')
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))


def test_a_worktree_branch_after_the_move_opens_a_book_root_holding_the_moved_services_and_lands_by_rebase(tmp_path, _trees):
    repo = _acme(tmp_path)
    artifacts = _artifacts_repo()
    move_book(repo, artifacts, "acme")
    linked = tmp_path / "code" / "acme-x"
    _git(repo, "worktree", "add", "--quiet", "-b", "feat/x", str(linked))
    opened = _ostler(["book", "branch"], linked)
    assert opened.returncode == 0, opened.stdout + opened.stderr
    root = Path(opened.stdout.strip())
    assert root != artifacts
    assert (root / "services" / "acme" / "api" / "service.py").is_file()
    _commit(root, "products/acme/two-rules.md", PAGE)
    landed = _ostler(["book", "land"], linked)
    assert landed.returncode == 0, landed.stdout + landed.stderr
    assert "products/acme/two-rules.md" in _git(artifacts, "show", "--stat", "--format=%s", "HEAD")
    assert (artifacts / "products" / "acme" / "two-rules.md").is_file()
    assert _merges(artifacts) == ""
    assert not root.exists()


def test_a_flat_book_in_the_artifacts_folder_moves_by_the_guide(tmp_path):
    repo = _acme(tmp_path)
    artifacts = _artifacts_repo()
    shutil.copytree(repo / "services", artifacts / "services", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    _git(artifacts, "add", "-A")
    _git(artifacts, "commit", "--quiet", "-m", "flat books")
    _git(repo, "rm", "-r", "--quiet", "services")
    _git(repo, "commit", "--quiet", "-m", "drop the in-repo book")
    refused = _ostler_with_env(["book", "check", "services.acme.api", "--app", str(repo)], repo)
    assert refused.returncode != 0, refused.stdout + refused.stderr
    assert "ostler book move api --repo acme" in refused.stdout + refused.stderr
    moved = _ostler(["book", "move", "api", "web", "digest", "kit", "__init__.py", "--repo", "acme"], artifacts)
    assert moved.returncode == 0, moved.stdout + moved.stderr
    _git(artifacts, "add", "-A", "services")
    _git(artifacts, "commit", "--quiet", "-m", "docs(book): move the acme books into their repository folder")
    checked = _ostler_with_env(["book", "check", "services.acme.api", "--app", str(repo)], repo)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "check: 0 findings" in checked.stdout
