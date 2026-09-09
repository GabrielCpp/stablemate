"""Where `check_public.py` looks for the hook git would actually run.

The hook check failed a linked worktree while that worktree's commits were visibly being
blocked by the very hooks it reported missing. `<repo>/.git/hooks/pre-commit` is a plain
clone's layout and only a plain clone's: in a worktree `.git` is a *file*, and the hooks
live in the common directory it points at. A guard whose failure mode is "the guards are
off" has to be right about that, because the fix it prints (`make hooks`) does nothing for
a clone where they were never off.

So the layout is built rather than described — `git init`, a commit, `git worktree add` —
and the resolver is asked from inside it.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_public.py"


@pytest.fixture(scope="module")
def public() -> Any:
    spec = importlib.util.spec_from_file_location("check_public", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    root = tmp_path / "clone"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "file.txt").write_text("x\n", encoding="utf-8")
    _git(root, "add", "file.txt")
    _git(root, "commit", "-qm", "init")
    return root


def test_a_plain_clone_resolves_into_its_own_git_dir(
    public: Any, clone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(public, "REPO", clone)
    assert public._installed_hook() == clone / ".git" / "hooks" / "pre-commit"


def test_a_worktree_resolves_into_the_common_dir(
    public: Any, clone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression: a worktree's hooks are the clone's, and `.git` there is a file."""
    tree = tmp_path / "wt"
    _git(clone, "worktree", "add", "-q", "-b", "side", str(tree))
    assert (tree / ".git").is_file()
    monkeypatch.setattr(public, "REPO", tree)

    resolved = public._installed_hook()

    assert resolved == clone / ".git" / "hooks" / "pre-commit"
    assert not resolved.is_relative_to(tree)


def test_a_redirected_hooks_path_is_followed(
    public: Any, clone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`core.hooksPath` means the hook in `.git/hooks` is not the one git runs."""
    _git(clone, "config", "core.hooksPath", ".githooks")
    monkeypatch.setattr(public, "REPO", clone)
    assert public._installed_hook() == clone / ".githooks" / "pre-commit"


def test_a_tree_git_will_not_answer_for_reads_as_absent(
    public: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    monkeypatch.setattr(public, "REPO", bare)
    assert public._installed_hook() == bare / ".git" / "hooks" / "pre-commit"


# ── commit-message guard ────────────────────────────────────────────────────
#
# The hook reads ``.git/COMMIT_EDITMSG`` (which git writes before the hook runs) and
# greps it for private names. Two properties matter:
#
#   * Subject AND body are scanned. A name can hide in either; the pre-commit hook
#     cannot see either until the user has typed it.
#   * ``#`` lines (git's editor template hints) are skipped. A template hint that
#     happens to mention a name should not block every commit.
#
# The ``PRIVATE_NAMES`` env var drives the resolver; with it set, the test owns what
# counts as "private". A public contributor who has not configured any list sees the
# same no-op the hook sees — the function returns ``[]`` and the commit proceeds.


def test_a_commit_message_with_a_private_name_is_flagged(
    public: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STABLEMATE_PRIVATE_NAMES", "acme,globex")
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat(core): integrate the acme client\n", encoding="utf-8")

    offenders = public.check_no_private_names_in_commit_message(msg)

    assert any("acme" in o for o in offenders), offenders


def test_a_private_name_in_the_body_is_flagged_too(
    public: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The subject is what most reviewers read; the body is what the leak looks like."""
    monkeypatch.setenv("STABLEMATE_PRIVATE_NAMES", "globex")
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text(
        "feat(core): tidy the dashboard\n\n"
        "Wires the globex metrics endpoint into the status page.\n",
        encoding="utf-8",
    )

    offenders = public.check_no_private_names_in_commit_message(msg)

    assert any("globex" in o for o in offenders), offenders


def test_git_editor_hint_comments_are_ignored(
    public: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``# Please enter the commit message...`` is git's template, not a leak."""
    monkeypatch.setenv("STABLEMATE_PRIVATE_NAMES", "acme")
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text(
        "# Please enter the commit message for your changes. Lines starting\n"
        "# with '#' will be ignored, and an empty message aborts the commit.\n"
        "#\n"
        "# On branch main\n"
        "# Changes to be committed:\n"
        "#\tmodified:   core/x.py\n"
        "\n"
        "feat: clean diff\n",
        encoding="utf-8",
    )

    offenders = public.check_no_private_names_in_commit_message(msg)

    assert offenders == [], offenders


def test_no_names_configured_makes_the_check_a_no_op(
    public: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A public contributor cannot leak what they do not have on file."""
    monkeypatch.delenv("STABLEMATE_PRIVATE_NAMES", raising=False)
    # Also clear the .git/private-names file path if the test machine has one — the
    # resolver consults both; with either set, names are loaded.
    monkeypatch.setattr(public._private_names_module(), "load", lambda: [])
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat: mention acme just to be sure\n", encoding="utf-8")

    assert public.check_no_private_names_in_commit_message(msg) == []


def test_a_missing_commit_message_file_is_silently_skipped(
    public: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh repo's first commit may not have COMMIT_EDITMSG yet — absent is OK."""
    monkeypatch.setenv("STABLEMATE_PRIVATE_NAMES", "acme")
    msg = tmp_path / "does-not-exist"

    assert public.check_no_private_names_in_commit_message(msg) == []


def test_the_cli_flag_drives_a_clean_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: ``--commit-message PATH`` reads, scans, and exits 0 on a clean file."""
    monkeypatch.setenv("STABLEMATE_PRIVATE_NAMES", "acme")
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat: clean diff\n", encoding="utf-8")

    proc = subprocess.run(
        ["python3", str(SCRIPT), "--commit-message", str(msg)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_cli_flag_drives_a_failure_on_a_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a leak in the proposed message makes the hook exit 1."""
    monkeypatch.setenv("STABLEMATE_PRIVATE_NAMES", "acme")
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat: integrate acme client\n", encoding="utf-8")

    proc = subprocess.run(
        ["python3", str(SCRIPT), "--commit-message", str(msg)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "acme" in proc.stderr, proc.stderr
