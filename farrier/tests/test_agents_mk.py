"""The generated launcher (.agents/agents.mk) is emitted for every repo, but its
workflow-run targets appear only when a workflow is installed.

Rationale: `agent-install`/`agent-check` are useful even for a skills/prompts-only
repo (and let an existing root Makefile `include` the launcher unconditionally),
while `agent-run`/`agent-native`/… only make sense with a workflow to run.

    ./.venv/bin/python -m pytest tests/test_agents_mk.py
"""
from __future__ import annotations

from farrier.install import render_agents_mk, render_local_compose, resolve_workflow_meta

META = {
    "repo_url": "REPLACE_ME-git-remote-url",
    "branch": "main",
    "agents_dir": "$(abspath $(CURDIR)/../vigilant-octo/agents)",
    "repo_name": "demo",
    "remote_checkout": False,
    "agents": {"claude": False, "codex": True, "copilot": False},
}


def test_regen_targets_always_present():
    for workflows in ([], ["coder"]):
        mk = render_agents_mk(workflows, META)
        assert "help:" in mk
        assert "agent-install:" in mk
        assert "agent-check:" in mk
        assert ".DEFAULT_GOAL := help" in mk


def test_workflow_targets_omitted_without_workflows():
    mk = render_agents_mk([], META)
    assert "agent-run:" not in mk
    assert "agent-native:" not in mk
    assert "COMPOSE :=" not in mk
    assert "WORKFLOW_DIR" not in mk
    # .PHONY lists only the always-on targets.
    assert ".PHONY: help agent-install agent-check\n" in mk


def test_workflow_targets_present_with_workflows():
    # build_outputs passes a sorted list; WF defaults to the first entry.
    mk = render_agents_mk(["author", "coder"], META)
    assert "agent-run:" in mk
    assert "agent-native:" in mk
    assert "agent-artifacts:" in mk
    assert "COMPOSE :=" in mk
    assert "COMPOSE := docker compose -p $(PROJECT)" in mk
    assert 'PROJECT="$(PROJECT)"' in mk
    assert "WF           ?= author" in mk
    assert 'REPO_URL="$(REPO_URL)"' in mk
    assert 'REPO_CONFIG="$(REPO_CONFIG)"' in mk
    assert "bash -o pipefail -c" in mk
    assert "--exit-code-from $(WF)" in mk
    assert "agent-run" in mk[mk.index(".PHONY"):mk.index("\n", mk.index(".PHONY"))]


def test_local_compose_defaults_to_read_only_host_checkout():
    compose = render_local_compose(["author"], META)

    assert "REPO_URL: /mnt/demo-src" in compose
    assert "source: ${REPO_SRC:-.}" in compose
    assert "REPO_TOKEN_ENV" not in compose
    assert "${HOME}/.claude/.credentials.json" not in compose


def test_local_compose_mounts_claude_credentials_when_claude_enabled():
    meta = dict(META)
    meta["agents"] = {"claude": True, "codex": False, "copilot": False}

    compose = render_local_compose(["author"], meta)

    assert "CLAUDE_CODE_OAUTH_TOKEN: ${CLAUDE_CODE_OAUTH_TOKEN:-}" in compose
    assert "source: ${HOME}/.claude/.credentials.json" in compose
    assert "target: /mnt/claude-credentials.json" in compose


def test_explicit_repo_url_uses_authenticated_remote_checkout(tmp_path):
    meta = resolve_workflow_meta(
        {
            "workflow": {
                "repoUrl": "https://github.com/example/private.git",
                "branch": "master",
                "githubTokenEnv": "EXAMPLE_GITHUB_TOKEN",
                "envPassthrough": ["EXAMPLE_GITHUB_TOKEN"],
            }
        },
        tmp_path,
        "demo",
    )

    compose = render_local_compose(["author"], meta)

    assert "REPO_URL: ${REPO_URL:-https://github.com/example/private.git}" in compose
    assert "AGENT_CONFIG_FILE: /repo-config/agents.yml" in compose
    assert "target: /repo-config/agents.yml" in compose
    assert "EXAMPLE_GITHUB_TOKEN: ${EXAMPLE_GITHUB_TOKEN:-}" in compose
    assert "source: ${REPO_SRC" not in compose
