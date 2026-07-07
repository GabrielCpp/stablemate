"""The generated launcher (.agents/agents.mk) is emitted for every repo, but its
workflow-run targets appear only when a workflow is installed.

Rationale: `agent-install`/`agent-check` are useful even for a skills/prompts-only
repo (and let an existing root Makefile `include` the launcher unconditionally),
while `agent-run`/`agent-native`/… only make sense with a workflow to run.

    ./.venv/bin/python -m pytest tests/test_agents_mk.py
"""
from __future__ import annotations

from farrier.install import render_agents_mk

META = {
    "repo_url": "REPLACE_ME-git-remote-url",
    "branch": "main",
    "agents_dir": "$(abspath $(CURDIR)/../vigilant-octo/agents)",
    "repo_name": "demo",
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
    assert "WF           ?= author" in mk
    assert "agent-run" in mk[mk.index(".PHONY"):mk.index("\n", mk.index(".PHONY"))]
