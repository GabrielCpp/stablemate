"""The generated launcher (.agents/agents.mk) is emitted for every repo, and carries
only the two targets that regenerate and verify farrier's adapters.

Rationale: farrier installs skills and prompts, not workflows. A workflow is a
Python package workhorse resolves through the `workhorse.workflows` entry-point
group, so nothing about running one is per-repo generated state — `agent-install`
and `agent-check` are the whole launcher, and an existing root Makefile can
`include` it unconditionally.

    ./.venv/bin/python -m pytest tests/test_agents_mk.py
"""
from __future__ import annotations

from farrier.install import render_agents_mk


def test_regen_targets_always_present():
    mk = render_agents_mk()
    assert "help:" in mk
    assert "agent-install:" in mk
    assert "agent-check:" in mk
    assert ".DEFAULT_GOAL := help" in mk
    # .PHONY lists exactly those.
    assert ".PHONY: help agent-install agent-check\n" in mk


def test_no_workflow_run_targets_or_docker_plumbing():
    """The YAML-era run targets are gone, not merely unused.

    Each of these drove the retired front end: `--workflow <dir>/workflow.yaml`,
    a compose override generated per installed workflow, and a `WF` variable
    naming which of them to run. Asserting their absence keeps a copy-paste from
    an old launcher from reintroducing an invocation workhorse no longer accepts.
    """
    mk = render_agents_mk()
    for absent in (
        "agent-run:",
        "agent-native:",
        "agent-build:",
        "agent-hello:",
        "agent-artifacts:",
        "COMPOSE :=",
        "WORKFLOW_DIR",
        "WORKFLOW_ARG",
        "--workflow",
        "local.compose.yaml",
        "WF           ?=",
    ):
        assert absent not in mk, absent


def test_points_at_the_workhorse_cli_for_running_a_workflow():
    """A reader who lost `make agent-run` needs the replacement in the same file."""
    mk = render_agents_mk()
    assert "workhorse run <name>" in mk
    assert "--dry-run" in mk


def test_farrier_regeneration_is_library_aware():
    mk = render_agents_mk()
    assert "AGENTS_DIR     ?= $(shell farrier config show library_dir)" in mk
    assert (
        'FARRIER_LIB_ARG := $(if $(wildcard $(AGENTS_DIR)/library),'
        '--library "$(AGENTS_DIR)",)'
    ) in mk
    # SRC=1 still runs the installer from a local stablemate checkout.
    assert "uv run --project $(STABLEMATE_DIR)/farrier farrier" in mk
