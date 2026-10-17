"""Specs live in the user's artifacts folder unless `docRoots: specs:` keeps them in the repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ostler.cli import main
from ostler.model import load
from ostler.path import resolve_spec, resolve_spec_arg, specs_root_in

from conftest import FOO_ID, specs_root, write


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo, check=True, capture_output=True,
    )


def test_the_default_specs_root_is_under_the_artifacts_dir(repo: Path):
    assert specs_root_in(repo) == specs_root()
    assert not specs_root().is_relative_to(repo.resolve())


def test_a_repo_and_its_worktree_share_one_specs_root(repo: Path, tmp_path_factory):
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    tree = tmp_path_factory.mktemp("elsewhere") / "wt"
    _git(repo, "worktree", "add", "-q", str(tree))

    assert specs_root_in(tree) == specs_root_in(repo) == specs_root()


def test_doc_roots_specs_keeps_specs_in_the_repo(repo: Path):
    write(repo / "ostler.yml", "organization:\n  docRoots:\n    specs: docs/specs\n")

    assert specs_root_in(repo) == repo / "docs/specs"
    assert resolve_spec(load(repo), "01-foo") == str(repo / "docs/specs" / FOO_ID)


def test_doc_roots_specs_accepts_an_absolute_path(repo: Path, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("kept")
    write(repo / "ostler.yml", f"organization:\n  docRoots:\n    specs: {elsewhere}\n")

    assert specs_root_in(repo) == elsewhere


def test_path_spec_prints_an_absolute_path_outside_the_repo(repo: Path, capsys):
    assert main(["-C", str(repo), "path", "spec", FOO_ID]) == 0

    printed = Path(capsys.readouterr().out.strip())
    assert printed == specs_root() / FOO_ID
    assert not printed.is_relative_to(repo.resolve())


def test_create_spec_writes_into_the_artifacts_folder(repo: Path):
    assert main(["-C", str(repo), "create", "spec", FOO_ID, "plan.md"]) == 0

    assert (specs_root() / FOO_ID / "plan.md").is_file()
    assert not (repo / "docs/specs").exists()


def test_a_spec_argument_resolves_as_typed_then_under_the_specs_root_then_the_repo(repo: Path):
    absolute = repo / "elsewhere/01-foo"
    assert resolve_spec_arg(repo, absolute) == absolute
    assert resolve_spec_arg(repo, Path("01-foo")) == specs_root() / "01-foo"
    (repo / "legacy/01-foo").mkdir(parents=True)
    assert resolve_spec_arg(repo, Path("legacy/01-foo")) == repo / "legacy/01-foo"
    (specs_root() / "legacy/01-foo").mkdir(parents=True)
    assert resolve_spec_arg(repo, Path("legacy/01-foo")) == specs_root() / "legacy/01-foo"
