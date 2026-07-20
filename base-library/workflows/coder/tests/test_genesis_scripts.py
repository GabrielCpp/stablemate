"""Direct subprocess tests for the `genesis` flow's deterministic scripts.

Same hermetic style as test_run_lint.py: seed a tmp dir, run the real script, assert the JSON
contract. Git runs for real (there is nothing to mock); farrier and the stack's native init
tooling are not invoked — those nodes are exercised through their argument contract only.

The assertions worth reading are in test_validate_genesis_*: they pin the *silent* failures
genesis exists to prevent (ostler binding to an ancestor repo, an empty instructions map, a
missing docs/epics that makes epic-coverage validation short-circuit), each of which produces
a passing-looking run rather than an error.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(script: str, args: list[str], cwd: Path) -> dict:
    env = {**os.environ, "AGENT_REPO_DIR": str(cwd), "PYTHONPATH": str(SCRIPTS)}
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, cwd=str(cwd), env=env, timeout=120,
    )
    assert result.returncode == 0, f"{script} exited {result.returncode}: {result.stderr}"
    return json.loads(result.stdout)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


# ── resolve-genesis-target ────────────────────────────────────────────────────

def test_resolve_target_absent(tmp_path):
    out = _run("resolve-genesis-target.py", [str(tmp_path / "new"), "api"], tmp_path)
    assert out["target_state"] == "absent"
    assert out["target_dir"] == str(tmp_path / "new")


def test_resolve_target_empty_dir_counts_as_absent(tmp_path):
    """A bare `mkdir` must still route to full genesis, not to config-refresh-only."""
    (tmp_path / "new").mkdir()
    out = _run("resolve-genesis-target.py", [str(tmp_path / "new"), "api"], tmp_path)
    assert out["target_state"] == "absent"


def test_resolve_target_partial(tmp_path):
    target = tmp_path / "new"
    target.mkdir()
    (target / "stray.txt").write_text("x", encoding="utf-8")
    out = _run("resolve-genesis-target.py", [str(target), "api"], tmp_path)
    assert out["target_state"] == "partial"
    assert "nothing already there will be removed" in out["genesis_note"]


def test_resolve_target_existing(tmp_path):
    target = tmp_path / "live"
    target.mkdir()
    (target / "agents.yml").write_text("repo:\n  name: live\n", encoding="utf-8")
    out = _run("resolve-genesis-target.py", [str(target), "api"], tmp_path)
    assert out["target_state"] == "existing"


def test_new_service_in_an_existing_repo_is_still_absent(tmp_path):
    """The monorepo-growth case. Keying the skeleton on repo state would skip it here, so
    a second surface could never be added beside the first."""
    target = tmp_path / "live"
    (target / "api").mkdir(parents=True)
    (target / "api" / "go.mod").write_text("module x\n", encoding="utf-8")
    (target / "agents.yml").write_text("repo:\n  name: live\n", encoding="utf-8")

    out = _run("resolve-genesis-target.py", [str(target), "web", "web", "package.json"], tmp_path)
    assert out["target_state"] == "existing", "the repo is established"
    assert out["service_state"] == "absent", "but this service is not — it must still be built"


def test_existing_service_is_detected_by_its_own_marker(tmp_path):
    target = tmp_path / "live"
    (target / "api").mkdir(parents=True)
    (target / "api" / "go.mod").write_text("module x\n", encoding="utf-8")
    (target / "agents.yml").write_text("repo:\n  name: live\n", encoding="utf-8")

    out = _run("resolve-genesis-target.py", [str(target), "api", "api", "go.mod"], tmp_path)
    assert out["service_state"] == "existing"


# ── genesis-git-init ──────────────────────────────────────────────────────────

def test_git_init_creates_repo_with_a_commit(tmp_path):
    target = tmp_path / "new"
    out = _run("genesis-git-init.py", [str(target), "absent"], tmp_path)
    assert out["git_ready"] == "yes"
    assert out["initial_commit"], "an unborn HEAD leaves nothing for a branch to point at"
    assert (target / ".git").exists()


def test_git_init_adds_no_remote(tmp_path):
    """Local-only by design — PR delivery is optional downstream, not assumed."""
    target = tmp_path / "new"
    _run("genesis-git-init.py", [str(target), "absent"], tmp_path)
    remotes = subprocess.run(["git", "remote"], cwd=str(target), capture_output=True, text=True)
    assert remotes.stdout.strip() == ""


def test_git_init_is_idempotent(tmp_path):
    target = tmp_path / "new"
    first = _run("genesis-git-init.py", [str(target), "absent"], tmp_path)
    second = _run("genesis-git-init.py", [str(target), "existing"], tmp_path)
    assert second["git_ready"] == "yes"
    assert second["initial_commit"] == first["initial_commit"], "re-run must not re-commit"


def test_git_init_lands_a_commit_on_an_unborn_head(tmp_path):
    target = tmp_path / "new"
    target.mkdir()
    _git(target, "init", "-q")
    out = _run("genesis-git-init.py", [str(target), "partial"], tmp_path)
    assert out["git_ready"] == "yes" and out["initial_commit"]


# ── write-genesis-agents-yml ──────────────────────────────────────────────────

def _agents(target: Path) -> dict:
    import yaml
    return yaml.safe_load((target / "agents.yml").read_text(encoding="utf-8"))


def test_agents_yml_declares_the_workspace_block(tmp_path):
    target = tmp_path / "new"
    target.mkdir()
    out = _run("write-genesis-agents-yml.py",
               [str(target), "api", "go", "api", "go.mod,main.go", "coder",
                "shared-docs:docs,go-service:api", "claude"], tmp_path)
    assert out["agents_yml_written"] == "yes"
    data = _agents(target)
    assert data["repo"]["name"] == "new", "the repo is named for its directory"
    assert data["packs"] == ["go"]
    # `farrier scaffold <id>` refuses an id not enabled here, so install_farrier's scaffold
    # step renders nothing unless this node declares them. Ids only — the dir is its business.
    assert data["scaffolds"] == ["shared-docs", "go-service"]
    # The workspace: block is what lets the planner target the service at all.
    assert data["workspace"]["service_roots"] == ["api"]
    assert data["workspace"]["service_markers"] == ["go.mod", "main.go"]


def test_repo_name_is_the_directory_not_the_service(tmp_path):
    """A monorepo holds several services under ONE repo. Two things key off the repo name:
    `resolve_workspace` (so the planner resolves services under it) and farrier's
    generated-skill prefix. Taking the first surface's service name produced a workspace
    keyed on 'api' and 49 skills named `api-flutter-*`."""
    target = tmp_path / "todo-app"
    target.mkdir()
    _run("write-genesis-agents-yml.py",
         [str(target), "api", "go", "api", "go.mod", "coder", "", "claude"], tmp_path)
    assert _agents(target)["repo"]["name"] == "todo-app"


def test_agents_yml_enables_an_assistant(tmp_path):
    """`farrier install` hard-exits with "No agents selected in config" when `agents:` is
    absent, so omitting it made install fail outright — surfacing much later as an empty
    instructions map and a validate_genesis repair loop over something fully deterministic."""
    target = tmp_path / "new"
    target.mkdir()
    _run("write-genesis-agents-yml.py",
         [str(target), "api", "go", "api", "go.mod", "coder", "", ""], tmp_path)
    assert _agents(target)["agents"] == {"claude": True, "codex": False, "copilot": False}


def test_agents_yml_keeps_an_existing_assistant_choice(tmp_path):
    """A config-refresh re-run must not overwrite assistants the repo already chose."""
    target = tmp_path / "new"
    target.mkdir()
    (target / "agents.yml").write_text(
        "repo:\n  name: api\nagents:\n  codex: true\n", encoding="utf-8")
    _run("write-genesis-agents-yml.py",
         [str(target), "api", "go", "api", "go.mod", "coder", "", "claude"], tmp_path)
    assert _agents(target)["agents"] == {"codex": True}


def test_agents_yml_merges_rather_than_clobbering(tmp_path):
    """A re-run must not drop packs, workflows, or hand-edits — that is what makes genesis
    safe to re-run during setup iteration."""
    target = tmp_path / "new"
    target.mkdir()
    (target / "agents.yml").write_text(
        "repo:\n  name: api\npacks:\n  - handwritten\nagents:\n  copilot: true\n",
        encoding="utf-8")
    _run("write-genesis-agents-yml.py",
         [str(target), "api", "go", "api", "go.mod", "coder", ""], tmp_path)
    data = _agents(target)
    assert data["packs"] == ["handwritten", "go"]
    assert data["agents"] == {"copilot": True}, "unrelated keys must survive"


def test_agents_yml_refuses_to_clobber_an_unreadable_file(tmp_path):
    target = tmp_path / "new"
    target.mkdir()
    (target / "agents.yml").write_text("repo: [unclosed\n", encoding="utf-8")
    out = _run("write-genesis-agents-yml.py",
               [str(target), "api", "go", "api", "go.mod", "coder", ""], tmp_path)
    assert out["agents_yml_written"] == "no"
    assert "refusing to clobber" in out["agents_yml_note"]


# ── init-genesis-skeleton ─────────────────────────────────────────────────────

def test_skeleton_runs_init_and_finds_the_marker(tmp_path):
    target = tmp_path / "new"
    target.mkdir()
    out = _run("init-genesis-skeleton.py",
               [str(target), "api", "touch go.mod", "go.mod"], tmp_path)
    assert out["skeleton_ok"] == "yes"
    assert out["marker_path"] == "api/go.mod"
    assert (target / "api" / "go.mod").exists()


def test_skeleton_fails_when_init_makes_no_marker(tmp_path):
    """Exit 0 is not proof a service was made — some generators write into a subdirectory
    or no-op. The marker is the proof, and validate-plan-context.py needs it to be real."""
    target = tmp_path / "new"
    target.mkdir()
    out = _run("init-genesis-skeleton.py",
               [str(target), "api", "echo did-nothing", "go.mod"], tmp_path)
    assert out["skeleton_ok"] == "no"
    assert "was not created" in out["skeleton_note"]


def test_skeleton_is_idempotent(tmp_path):
    """`go mod init` and friends fail or clobber on re-run, so an existing marker skips."""
    target = tmp_path / "new"
    (target / "api").mkdir(parents=True)
    (target / "api" / "go.mod").write_text("module example.com/api\n", encoding="utf-8")
    out = _run("init-genesis-skeleton.py",
               [str(target), "api", "exit 1", "go.mod"], tmp_path)
    assert out["skeleton_ok"] == "yes"
    assert "idempotent re-run" in out["skeleton_note"]


def test_skeleton_reports_a_missing_init_cmd_actionably(tmp_path):
    target = tmp_path / "new"
    target.mkdir()
    out = _run("init-genesis-skeleton.py", [str(target), "api", "", "go.mod"], tmp_path)
    assert out["skeleton_ok"] == "no"
    assert "init_cmd" in out["skeleton_note"]


# ── validate-genesis: the preconditions the main loop assumes ─────────────────

def _good_repo(tmp_path) -> Path:
    """A repo satisfying every genesis postcondition."""
    target = tmp_path / "repo"
    (target / "api").mkdir(parents=True)
    (target / "api" / "go.mod").write_text("module example.com/api\n", encoding="utf-8")
    (target / "docs" / "epics").mkdir(parents=True)
    (target / "docs" / "backlog.md").write_text("- [x] a thing\n", encoding="utf-8")
    (target / ".agents").mkdir()
    (target / ".agents" / "agents-context.json").write_text(
        json.dumps({"instructions": {"go-service": {"path": "skills/go.md"}}}), encoding="utf-8")
    (target / "agents.yml").write_text("repo:\n  name: repo\n", encoding="utf-8")
    (target / "Makefile").write_text("lint:\n\t@echo lint\n", encoding="utf-8")
    _git(target, "init", "-q")
    _git(target, "add", "-A")
    _git(target, "-c", "user.email=t@example.com", "-c", "user.name=t",
         "commit", "-q", "-m", "init")
    return target


def _validate(target: Path, tmp_path) -> dict:
    return _run("validate-genesis.py", [str(target), "api", "go.mod"], tmp_path)


def test_validate_genesis_passes_on_a_complete_repo(tmp_path):
    out = _validate(_good_repo(tmp_path), tmp_path)
    assert out["genesis_valid"] == "yes", out["genesis_errors"]
    assert out["genesis_warnings"] == ""


def test_validate_genesis_catches_the_ostler_ancestor_misbind(tmp_path):
    """The one genuinely silent failure. Without .git the target has no boundary, so ostler
    binds to whatever repo sits above it — ids from the parent's registry, docs into the
    parent's tree, no error anywhere. A benchmark cannot detect this after the fact."""
    parent = tmp_path / "outer"
    (parent / "docs").mkdir(parents=True)   # makes `parent` look like a repo root to ostler
    target = parent / "inner"
    (target / "api").mkdir(parents=True)
    (target / "api" / "go.mod").write_text("module example.com/api\n", encoding="utf-8")

    out = _validate(target, tmp_path)
    assert out["genesis_valid"] == "no"
    assert "ostler binds to" in out["genesis_errors"]
    assert str(parent) in out["genesis_errors"]


def test_validate_genesis_catches_an_unborn_head(tmp_path):
    target = _good_repo(tmp_path)
    import shutil
    shutil.rmtree(target / ".git")
    _git(target, "init", "-q")
    out = _validate(target, tmp_path)
    assert out["genesis_valid"] == "no"
    assert "unborn HEAD" in out["genesis_errors"]


def test_validate_genesis_catches_a_missing_service_marker(tmp_path):
    target = _good_repo(tmp_path)
    (target / "api" / "go.mod").unlink()
    out = _validate(target, tmp_path)
    assert out["genesis_valid"] == "no"
    assert "no service marker" in out["genesis_errors"]


def test_validate_genesis_catches_an_empty_instructions_map(tmp_path):
    """Empty means resolve-impl-context.py resolves every skill to nothing and the
    implementation stage runs unskilled — and still reports success."""
    target = _good_repo(tmp_path)
    (target / ".agents" / "agents-context.json").write_text(
        json.dumps({"instructions": {}}), encoding="utf-8")
    out = _validate(target, tmp_path)
    assert out["genesis_valid"] == "no"
    assert "instructions" in out["genesis_errors"]


def test_validate_genesis_catches_a_missing_epics_dir(tmp_path):
    """Without docs/epics/ ostler infers the 'exploration' profile, doctor short-circuits,
    and epic-coverage validation reports success having checked nothing."""
    target = _good_repo(tmp_path)
    (target / "docs" / "epics").rmdir()
    out = _validate(target, tmp_path)
    assert out["genesis_valid"] == "no"
    assert "docs/epics" in out["genesis_errors"]


def test_validate_genesis_catches_a_missing_backlog(tmp_path):
    target = _good_repo(tmp_path)
    (target / "docs" / "backlog.md").unlink()
    out = _validate(target, tmp_path)
    assert out["genesis_valid"] == "no"
    assert "backlog.md" in out["genesis_errors"]


def test_validate_genesis_warns_but_passes_without_a_lint_target(tmp_path):
    """A missing lint target degrades the gate to a skip rather than breaking the repo —
    a legibility problem, so a warning, not an error."""
    target = _good_repo(tmp_path)
    (target / "Makefile").unlink()
    out = _validate(target, tmp_path)
    assert out["genesis_valid"] == "yes"
    assert "lint" in out["genesis_warnings"]


def test_validate_genesis_shares_the_service_assertion_with_the_planner_gate(tmp_path):
    """Genesis's postcondition and validate-plan-context.py's precondition are the same
    assertion; sharing one implementation is what stops them drifting silently apart."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        from service_contract import service_problems
    finally:
        sys.path.pop(0)
    target = _good_repo(tmp_path)
    assert service_problems(target / "api", ["go.mod"], "repo::api") == []
    assert service_problems(target / "web", ["package.json"], "repo::web") != []
