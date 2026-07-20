"""Tests for the author workflow's git/PR scripts: branch-author.py, commit-author.py,
open-author-pr.py, and gh-token.py.

Builds real git repos in hermetic tmp_path sandboxes (no mocked git — these scripts shell
out to the `git` CLI directly, mirroring the coder workflow's test_multi_repo_git.py
convention). `open-author-pr.py` is exercised through its offline failure paths and
local-origin resolution (no network or GitHub credentials in the test environment).
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "scripts"


def _run(script: str, args: list[str], cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "AGENT_REPO_DIR": str(cwd)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, cwd=str(cwd), env=env,
    )


def _init_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for cmd in [
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "t"],
    ]:
        subprocess.run(cmd, cwd=str(path), check=True, capture_output=True)
    (path / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=str(path), check=True, capture_output=True)
    return path


def _load_open_author_pr():
    script_path = SCRIPTS / "open-author-pr.py"
    spec = importlib.util.spec_from_file_location("open_author_pr", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# branch-author.py
# ---------------------------------------------------------------------------


def test_branch_author_creates_branch(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    result = _run("branch-author.py", ["myworkflow-run123", "epic"], repo)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["base_branch"] == "main"
    assert out["author_branch"] == "author/myworkflow-run123"

    current = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert current == "author/myworkflow-run123"


def test_branch_author_idempotent_on_resume(tmp_path):
    """A second invocation with the same run_dir checks out the SAME branch (resume)."""
    repo = _init_git_repo(tmp_path / "repo")
    first = _run("branch-author.py", ["myworkflow-run123", "epic"], repo)
    assert first.returncode == 0, first.stderr

    # Simulate work done on the branch, then a resumed invocation.
    (repo / "note.txt").write_text("wip", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "wip"], cwd=str(repo), check=True, capture_output=True)

    subprocess.run(["git", "checkout", "main"], cwd=str(repo), check=True, capture_output=True)
    second = _run("branch-author.py", ["myworkflow-run123", "epic"], repo)
    assert second.returncode == 0, second.stderr
    out = json.loads(second.stdout)
    assert out["author_branch"] == "author/myworkflow-run123"

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout
    assert "wip" in log  # the wip commit survived — same branch, not recreated


def test_branch_author_resume_uses_configured_base(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    subprocess.run(
        ["git", "branch", "-m", "master"], cwd=str(repo), check=True,
        capture_output=True, timeout=10,
    )
    first = _run(
        "branch-author.py", ["myworkflow-run789", "epic"], repo,
        extra_env={"REPO_BRANCH": "master"},
    )
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["base_branch"] == "master"

    second = _run(
        "branch-author.py", ["myworkflow-run789", "epic"], repo,
        extra_env={"REPO_BRANCH": "master"},
    )

    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["base_branch"] == "master"


def test_branch_author_no_git_repo(tmp_path):
    repo = tmp_path / "not-a-repo"
    repo.mkdir()
    result = _run("branch-author.py", ["myworkflow-run456", "epic"], repo)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out == {"base_branch": "main", "author_branch": ""}


# ---------------------------------------------------------------------------
# commit-author.py
# ---------------------------------------------------------------------------


def test_commit_author_commits_changes(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    (repo / "docs" / "epics").mkdir(parents=True)
    (repo / "docs" / "epics" / "epic.md").write_text("# epic\n", encoding="utf-8")

    result = _run("commit-author.py", ["epic", "", ""], repo)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out == {"committed": "yes"}

    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout
    assert "author:" in log


def test_commit_author_story_mode_message(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    (repo / "story.md").write_text("# story\n", encoding="utf-8")

    result = _run("commit-author.py", ["story", "e1", "Add the widget bullet"], repo)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"committed": "yes"}

    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout
    assert "e1" in log and "Add the widget bullet" in log


def test_commit_author_no_changes(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    result = _run("commit-author.py", ["epic", "", ""], repo)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"committed": "no"}


def test_commit_author_no_git_repo(tmp_path):
    repo = tmp_path / "not-a-repo"
    repo.mkdir()
    result = _run("commit-author.py", ["epic", "", ""], repo)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"committed": "no"}


# ---------------------------------------------------------------------------
# open-author-pr.py (offline paths only — no network in the test env)
# ---------------------------------------------------------------------------


def test_open_author_pr_no_branch(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    result = _run("open-author-pr.py", ["main", "", "epic", "", ""], repo)

    assert result.returncode == 1
    assert "no author branch" in result.stderr


def test_open_author_pr_no_git_repo_skips(tmp_path):
    """No .git at all — PR delivery is unconfigured, not failed."""
    repo = tmp_path / "not-a-repo"
    repo.mkdir()
    result = _run("open-author-pr.py", ["main", "author/run1", "epic", "", ""], repo)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["author_pr"] == "skipped"
    assert "no .git" in payload["pr_skip_reason"]


def test_open_author_pr_no_token_skips(tmp_path):
    """No credentials configured is a supported local-only setup, not a failure.

    The "PR delivery is required" invariant is scoped to runs where a forge *is* configured
    (see test_open_author_pr_no_remote_skips for the sibling case): a greenfield repo created
    by `coder genesis` is local-only by design, and failing it here would fail a run that
    passed every authoring gate.
    """
    repo = _init_git_repo(tmp_path / "repo")
    subprocess.run(["git", "checkout", "-b", "author/run1"], cwd=str(repo), check=True, capture_output=True)

    # Empty-string override, not omission: _run merges extra_env on top of a full
    # os.environ copy, so clearing a pre-existing var requires an explicit falsy
    # value — the scripts treat "" the same as unset (`if value:` / `if token:`).
    result = _run(
        "open-author-pr.py", ["main", "author/run1", "epic", "", ""], repo,
        extra_env={"GH_TOKEN": "", "GITHUB_TOKEN": ""},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["author_pr"] == "skipped"
    assert "token" in payload["pr_skip_reason"]


def test_open_author_pr_no_remote_skips(tmp_path):
    """A local-only repo (git init, no origin) has no forge to deliver to."""
    repo = _init_git_repo(tmp_path / "repo")
    subprocess.run(["git", "checkout", "-b", "author/run1"], cwd=str(repo), check=True, capture_output=True)

    result = _run(
        "open-author-pr.py", ["main", "author/run1", "epic", "", ""], repo,
        extra_env={"GH_TOKEN": "fake-token", "GITHUB_TOKEN": "fake-token"},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["author_pr"] == "skipped"
    assert "github.com" in payload["pr_skip_reason"]


def test_open_author_pr_missing_branch_still_fails(tmp_path):
    """Delivery *is* configured here, so a genuine failure must stay a hard failure —
    the skip path must not have swallowed the required-delivery invariant."""
    repo = _init_git_repo(tmp_path / "repo")
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:example-org/docs.git"],
        cwd=str(repo), check=True, capture_output=True,
    )

    result = _run(
        "open-author-pr.py", ["main", "author/does-not-exist", "epic", "", ""], repo,
        extra_env={"GH_TOKEN": "fake-token", "GITHUB_TOKEN": "fake-token"},
    )

    assert result.returncode == 1
    assert "no branch" in result.stderr


def test_open_author_pr_resolves_local_clone_source_origin(tmp_path):
    source = _init_git_repo(tmp_path / "source")
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:example/docs.git"],
        cwd=str(source), check=True, capture_output=True, timeout=10,
    )
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", str(source), str(clone)],
        check=True, capture_output=True, timeout=10,
    )

    module = _load_open_author_pr()

    assert module.resolve_github_slug(clone) == "example/docs"


def test_remote_urls_reads_origin_via_safe_directory(tmp_path):
    """scriptutil.remote_urls (which open-author-pr now uses) reads a repo's origin
    through git with a per-call safe.directory trust, so a host-owned bind-mount
    source resolves rather than being refused for 'dubious ownership'."""
    from workhorse import scriptutil

    repo = _init_git_repo(tmp_path / "source")
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:example/docs.git"],
        cwd=str(repo), check=True, capture_output=True, timeout=10,
    )

    assert scriptutil.remote_urls(repo) == ["git@github.com:example/docs.git"]


# ---------------------------------------------------------------------------
# gh-token.py
# ---------------------------------------------------------------------------


def test_gh_token_falls_back_to_gh_token_env(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agents.yml").write_text("name: testrepo\n", encoding="utf-8")

    result = _run(
        "gh-token.py", [], repo,
        extra_env={"GH_TOKEN": "tok-123", "GITHUB_TOKEN": ""},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "tok-123"


def test_gh_token_prefers_configured_env(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agents.yml").write_text(
        "workflow:\n  githubTokenEnv: ACME_GITHUB_TOKEN\n", encoding="utf-8",
    )

    result = _run(
        "gh-token.py", [], repo,
        extra_env={"ACME_GITHUB_TOKEN": "special-tok", "GH_TOKEN": "generic-tok"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "special-tok"


def test_gh_token_no_token_emits_nothing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agents.yml").write_text("name: testrepo\n", encoding="utf-8")

    result = _run(
        "gh-token.py", [], repo,
        extra_env={"GH_TOKEN": "", "GITHUB_TOKEN": ""},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_gh_token_reads_bootstrap_config_before_clone(tmp_path):
    repo = tmp_path / "not-cloned-yet"
    repo.mkdir()
    config = tmp_path / "agents.yml"
    config.write_text(
        "workflow:\n  githubTokenEnv: BOOTSTRAP_GITHUB_TOKEN\n",
        encoding="utf-8",
    )

    result = _run(
        "gh-token.py",
        [],
        repo,
        extra_env={
            "AGENT_CONFIG_FILE": str(config),
            "BOOTSTRAP_GITHUB_TOKEN": "bootstrap-token",
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "bootstrap-token"


def test_checkout_workspace_requires_author_token(tmp_path):
    repo = tmp_path / "not-cloned-yet"
    repo.mkdir()
    config = tmp_path / "agents.yml"
    config.write_text(
        "workflow:\n  githubTokenEnv: MISSING_GITHUB_TOKEN\n",
        encoding="utf-8",
    )

    result = _run(
        "checkout-workspace.py",
        [],
        repo,
        extra_env={"AGENT_CONFIG_FILE": str(config), "MISSING_GITHUB_TOKEN": ""},
    )

    assert result.returncode == 1
    assert "no GitHub token" in result.stderr
