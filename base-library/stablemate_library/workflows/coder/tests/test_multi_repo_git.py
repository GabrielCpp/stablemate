"""Direct subprocess tests for multi-repo git scripts.

Uses real git repos in hermetic tmp_path sandboxes. No mocked git — these
scripts shell out to the `git` CLI directly (never GitPython, whose
import-time `git version` probe crashes under the workflow test harness's
mocked git shim — see lib/ghutil.py), so we test them against real repos.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(script: str, args: list[str], cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "AGENT_REPO_DIR": str(cwd)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


def _run_sh(script: str, args: list[str], cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "AGENT_REPO_DIR": str(cwd)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


def _init_git_repo(path: Path, name: str = "test") -> Path:
    """Initialise a bare-minimum git repo with one commit."""
    path.mkdir(parents=True, exist_ok=True)
    for cmd in [
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "t"],
    ]:
        subprocess.run(cmd, cwd=str(path), check=True, capture_output=True)
    (path / "README.md").write_text(f"# {name}", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=str(path), check=True, capture_output=True)
    return path


def _seed_workspace(root: Path, repo_names: list[str]) -> tuple[Path, Path]:
    """Create git repos + workspace file. Returns (ws_file, docs_repo)."""
    docs_repo = _init_git_repo(root / "vigilant-octo")
    repos: list[dict] = []
    for name in repo_names:
        repo_path = root / name
        _init_git_repo(repo_path)
        (repo_path / "agents.yml").write_text(yaml.dump({"repo": {"name": name}, "workspace": {}}), encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "add agents.yml"], cwd=str(repo_path), check=True, capture_output=True)
        repos.append({"name": name, "path": f"../{name}"})

    ws_file = docs_repo / "workspace.code-workspace"
    ws_data = {"folders": [{"name": "vigilant-octo", "path": "vigilant-octo"}, *repos]}
    ws_file.write_text(json.dumps(ws_data, indent=2), encoding="utf-8")

    spec_dir = docs_repo / "specs" / "s-1"
    spec_dir.mkdir(parents=True)
    plan_ctx = {
        "services": [{"repo": n, "path": ".", "type": "go", "plan_file": "plan.md"} for n in repo_names],
        "implementation_order": [f"{n}::." for n in repo_names],
    }
    (spec_dir / "plan-context.json").write_text(json.dumps(plan_ctx, indent=2), encoding="utf-8")

    subprocess.run(["git", "add", "-A"], cwd=str(docs_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "add workspace"], cwd=str(docs_repo), check=True, capture_output=True)

    return ws_file, docs_repo


# ---------------------------------------------------------------------------
# branch-multi-repo.py
# ---------------------------------------------------------------------------


def test_branch_creates_in_docs_and_repos(tmp_path):
    """Story branch is created in both the docs repo and all affected repos."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["api-service"])

    result = _run(
        "branch-multi-repo.py",
        ["my-story"],
        docs_repo,
        extra_env={
            "CODER_WORKSPACE": str(ws_file),
            "SPEC_DIR": "specs/s-1",
        },
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["branched"] == "yes"
    assert "vigilant-octo" in out["repos"]
    assert "api-service" in out["repos"]

    # Verify branch exists in both repos
    for repo_path in [docs_repo, tmp_path / "api-service"]:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "story/my-story"],
            cwd=str(repo_path), capture_output=True,
        )
        assert proc.returncode == 0, f"Branch missing in {repo_path.name}"


def test_branch_idempotent(tmp_path):
    """Running branch script twice on an existing branch succeeds without error."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["api-service"])

    env = {
        "CODER_WORKSPACE": str(ws_file),
        "SPEC_DIR": "specs/s-1",
    }
    _run("branch-multi-repo.py", ["my-story"], docs_repo, extra_env=env)
    result = _run("branch-multi-repo.py", ["my-story"], docs_repo, extra_env=env)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["branched"] == "yes"


# ---------------------------------------------------------------------------
# commit-multi-repo.py
# ---------------------------------------------------------------------------


def test_commit_skips_clean_repos(tmp_path):
    """Repos with no changes are skipped; committed list is empty."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["api-service"])

    result = _run(
        "commit-multi-repo.py",
        ["my-story", "CASE-123"],
        docs_repo,
        extra_env={
            "CODER_WORKSPACE": str(ws_file),
            "SPEC_DIR": "specs/s-1",
        },
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["committed"] == "no"
    assert out["repos_committed"] == []


def test_commit_captures_dirty_repo(tmp_path):
    """A repo with changes gets committed with the right message."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["api-service"])

    # Make a change in api-service
    api_service = tmp_path / "api-service"
    (api_service / "new_file.txt").write_text("change", encoding="utf-8")

    result = _run(
        "commit-multi-repo.py",
        ["my-story", "CASE-123"],
        docs_repo,
        extra_env={
            "CODER_WORKSPACE": str(ws_file),
            "SPEC_DIR": "specs/s-1",
        },
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["committed"] == "yes"
    assert "api-service" in out["repos_committed"]

    # Verify commit message
    log = subprocess.run(
        ["git", "log", "--format=%s", "-1"],
        cwd=str(api_service), capture_output=True, text=True,
    )
    assert log.stdout.strip() == "CASE-123: my-story"


def test_commit_slug_only_without_epic(tmp_path):
    """When no epic is provided, commit message is just the slug."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["api-service"])
    api_service = tmp_path / "api-service"
    (api_service / "new_file.txt").write_text("change", encoding="utf-8")

    result = _run(
        "commit-multi-repo.py",
        ["my-story"],  # no epic
        docs_repo,
        extra_env={
            "CODER_WORKSPACE": str(ws_file),
            "SPEC_DIR": "specs/s-1",
        },
    )

    assert result.returncode == 0, result.stderr
    log = subprocess.run(
        ["git", "log", "--format=%s", "-1"],
        cwd=str(api_service), capture_output=True, text=True,
    )
    assert log.stdout.strip() == "my-story"


# ---------------------------------------------------------------------------
# branch-story.sh (story mode)
# ---------------------------------------------------------------------------


def test_branch_story_branches_docs_and_affected_repos(tmp_path):
    """branch-story.py branches the docs repo AND all repos listed in plan-context.json."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["mobile-app"])

    result = _run(
        "branch-story.py",
        ["CASE-4403"],
        docs_repo,
        extra_env={
            "CODER_WORKSPACE": str(ws_file),
            "SPEC_DIR": "specs/s-1",
        },
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["story_branch"] == "CASE-4403"
    assert "vigilant-octo" in out["repos"]
    assert "mobile-app" in out["repos"]

    for repo_path in [docs_repo, tmp_path / "mobile-app"]:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "CASE-4403"],
            cwd=str(repo_path), capture_output=True,
        )
        assert proc.returncode == 0, f"Branch missing in {repo_path.name}"


def test_branch_story_uses_absolute_docs_path(tmp_path):
    """branch-story.py resolves the docs root from an absolute docs_path arg, not CWD."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["mobile-app"])

    result = _run(
        "branch-story.py",
        ["CASE-4403", str(docs_repo)],
        tmp_path,  # CWD is parent, NOT the docs repo — proves absolute path is used
        extra_env={
            "CODER_WORKSPACE": str(ws_file),
            "SPEC_DIR": "specs/s-1",
        },
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["story_branch"] == "CASE-4403"
    assert "vigilant-octo" in out["repos"]
    assert "mobile-app" in out["repos"]


def test_branch_story_idempotent(tmp_path):
    """Running branch-story.py twice succeeds without error and preserves the branch."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["mobile-app"])

    env = {
        "CODER_WORKSPACE": str(ws_file),
        "SPEC_DIR": "specs/s-1",
    }
    _run("branch-story.py", ["CASE-4403"], docs_repo, extra_env=env)
    result = _run("branch-story.py", ["CASE-4403"], docs_repo, extra_env=env)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["story_branch"] == "CASE-4403"


def test_branch_story_no_workspace_file_only_docs(tmp_path):
    """Without CODER_WORKSPACE, branch-story.py still branches the docs repo."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["mobile-app"])

    result = _run(
        "branch-story.py",
        ["CASE-4403"],
        docs_repo,
        # No CODER_WORKSPACE → no code repos branched, but docs repo is still branched
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["story_branch"] == "CASE-4403"
    assert "vigilant-octo" in out["repos"]
    # mobile-app is not branched without the workspace file
    assert "mobile-app" not in out["repos"]


# ---------------------------------------------------------------------------
# branch-code-repos.py (post-planning code repo branching)
# ---------------------------------------------------------------------------


def _checkout_branch(repo_path: Path, branch: str) -> None:
    """Create and check out branch in repo_path (must not already exist)."""
    subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=str(repo_path), check=True, capture_output=True,
    )


def test_branch_code_repos_branches_affected_repos(tmp_path):
    """Branches code repos onto the branch that the docs repo is currently on."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["api-service", "web-app"])
    _checkout_branch(docs_repo, "story/CASE-4403")

    result = _run(
        "branch-code-repos.py",
        ["specs/s-1"],
        docs_repo,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert "api-service" in out["branched"]
    assert "web-app" in out["branched"]
    assert out["already_on_branch"] == []

    for name in ["api-service", "web-app"]:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "story/CASE-4403"],
            cwd=str(tmp_path / name), capture_output=True,
        )
        assert proc.returncode == 0, f"Branch missing in {name}"


def test_branch_code_repos_skips_docs_repo(tmp_path):
    """The docs repo itself is never touched by branch-code-repos.py."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["api-service"])
    _checkout_branch(docs_repo, "story/CASE-4403")

    result = _run(
        "branch-code-repos.py",
        ["specs/s-1"],
        docs_repo,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert "vigilant-octo" not in out["branched"]
    assert "vigilant-octo" not in out["already_on_branch"]


def test_branch_code_repos_idempotent(tmp_path):
    """Running branch-code-repos.py twice: second run reports already_on_branch."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["api-service"])
    _checkout_branch(docs_repo, "story/CASE-4403")
    env = {"CODER_WORKSPACE": str(ws_file)}

    _run("branch-code-repos.py", ["specs/s-1"], docs_repo, extra_env=env)
    result = _run("branch-code-repos.py", ["specs/s-1"], docs_repo, extra_env=env)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert "api-service" in out["already_on_branch"]
    assert out["branched"] == []


def test_branch_code_repos_uses_docs_repo_branch(tmp_path):
    """The target branch is read from the docs repo HEAD, not passed as an argument."""
    ws_file, docs_repo = _seed_workspace(tmp_path, ["api-service"])
    _checkout_branch(docs_repo, "feat/EPIC-42")

    result = _run(
        "branch-code-repos.py",
        ["specs/s-1"],
        docs_repo,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert "api-service" in out["branched"]
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "feat/EPIC-42"],
        cwd=str(tmp_path / "api-service"), capture_output=True,
    )
    assert proc.returncode == 0, "api-service should be on feat/EPIC-42"
