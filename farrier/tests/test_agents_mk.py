"""The generated launcher (.agents/agents.mk): adapter regeneration, containerized runs, and one run target per workflow installed on the machine running `make`."""
from __future__ import annotations

from farrier.install import render_agents_mk


def test_regen_targets_always_present():
    mk = render_agents_mk()
    assert "agent-help:" in mk
    assert "agent-install:" in mk
    assert "agent-check:" in mk


def test_help_and_default_goal_are_left_to_the_including_makefile():
    """This file is included at the end of a repo's own Makefile: a `help` target here overrides the repo's (make warns on every invocation), and an unconditional `.DEFAULT_GOAL` steals a bare `make`."""
    mk = render_agents_mk()
    assert "\nhelp:" not in mk
    assert ".DEFAULT_GOAL := help" not in mk
    assert "ifeq ($(.DEFAULT_GOAL),)" in mk
    assert ".DEFAULT_GOAL := agent-help" in mk


def test_no_workflow_name_is_ever_written_into_the_file():
    """The whole reversal in one assertion."""
    mk = render_agents_mk()
    for name in ("coder", "author", "okf-builder", "research", "loop-runner"):
        assert name not in mk, name


def test_the_workflow_list_is_resolved_when_make_runs():
    mk = render_agents_mk()
    assert "AGENT_WORKFLOWS := $(shell $(FARRIER) workflows --names)" in mk
    assert "$(foreach wf,$(AGENT_WORKFLOWS),$(eval $(call agent_run_target,$(wf))))" in mk
    assert "define agent_run_target" in mk


def test_discovery_is_gated_on_actually_wanting_to_run_something():
    """`farrier workflows` shells out to pipx (~0.4s)."""
    mk = render_agents_mk()
    assert "ifneq ($(filter agent-run-%,$(MAKECMDGOALS)),)" in mk


def test_a_reader_with_no_run_target_is_told_where_to_look():
    mk = render_agents_mk()
    assert "agent-workflows:" in mk
    assert "$(FARRIER) workflows" in mk


def test_no_yaml_era_run_targets_or_docker_plumbing():
    """The YAML-era run targets are gone, not merely renamed."""
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


def test_each_launch_mints_its_own_run_id():
    mk = render_agents_mk()
    assert 'run_id="$$(cat /proc/sys/kernel/random/uuid)"' in mk
    assert 'AGENT_RUN_ID="$$run_id"' in mk
    assert 'project="$(1)-$$run_id"' in mk
    assert 'docker compose -p "$$project"' in mk


def test_each_run_gets_its_own_worktree_of_the_repo():
    mk = render_agents_mk()
    assert "AGENT_SOURCE_MODE=worktree" in mk
    assert 'worktree_root="$(AGENT_WORKTREE_ROOT)/$$run_id"' in mk
    assert 'AGENT_REPO_DIR="$$worktree_root/$$repo_name"' in mk


def test_the_repo_is_bound_at_its_own_host_path():
    """Git records a worktree's registration on both sides by absolute path, so the container and the host have to agree on what that path is."""
    mk = render_agents_mk()
    assert 'AGENT_REPO_HOST_DIR="$(AGENT_REPO)"' in mk
    assert "AGENT_WORKTREE_ROOT ?= $(AGENT_REPO)/.agents/worktrees" in mk


def test_the_base_branch_is_resolved_lazily():
    """`?=` keeps this git call out of every `make` in the including repo — it runs only when a launch actually expands it."""
    mk = render_agents_mk()
    assert "AGENT_BASE_BRANCH  ?= $(shell git -C" in mk


def test_runs_as_nobody_with_the_operators_group():
    """65534:<host gid> — the uid is not yours, the group access is, so run output under a bind-mounted host path stays writable from the host."""
    mk = render_agents_mk()
    assert "AGENT_UID  ?= 65534" in mk
    assert "AGENT_GID  ?= $(shell id -g)" in mk
    assert 'AGENT_UID="$(AGENT_UID)" AGENT_GID="$(AGENT_GID)"' in mk


def test_run_output_stays_writable_from_the_host():
    """Group access is the only thing bridging the container's uid and yours, so nothing may drop the group write bit."""
    mk = render_agents_mk()
    assert "core.sharedRepository group" in mk
    assert 'chmod g+s "$$worktree_root"' in mk


def test_the_operators_own_repo_config_is_only_touched_when_absent():
    """It is their repo, and the setting persists and changes how their own git writes — so it is announced, and never overwritten."""
    mk = render_agents_mk()
    assert "config --local core.sharedRepository || true" in mk
    assert "[agent] set core.sharedRepository=group" in mk


def test_credentials_are_staged_per_run_rather_than_read_in_place():
    """`~/.claude/.credentials.json` is mode 600, so a container that is not you cannot read it and the run dies at "Not logged in"."""
    mk = render_agents_mk()
    assert 'run_auth="$$worktree_root/.credentials.json"' in mk
    assert 'install -m 640 "$$HOME/.claude/.credentials.json" "$$run_auth"' in mk
    assert 'AGENT_CREDENTIALS_FILE="$$run_auth"' in mk


def test_a_machine_with_no_credentials_file_still_launches():
    """CLAUDE_CODE_OAUTH_TOKEN is the other supported auth path, and it needs no file at all — so a missing credentials file is skipped, not fatal."""
    mk = render_agents_mk()
    assert 'if [ -r "$$HOME/.claude/.credentials.json" ]; then' in mk


def test_operating_targets_address_a_single_run():
    """With N runs in flight, every operating verb has to name which one."""
    mk = render_agents_mk()
    for target in ("agent-runs:", "agent-logs:", "agent-stop:", "agent-clean:"):
        assert target in mk, target
    assert mk.count("$(call agent_require_run)") == 3
    assert 'docker compose -p "$(RUN)" -f "$(AGENT_COMPOSE)" stop' in mk
    assert 'docker compose -p "$(RUN)" -f "$(AGENT_COMPOSE)" down -v' in mk


def test_compose_file_comes_from_the_stablemate_checkout():
    """compose.yaml/Dockerfile are harness files in the repo, not distribution files — there is no installed package to resolve them from."""
    mk = render_agents_mk()
    assert "AGENT_COMPOSE ?= $(STABLEMATE_DIR)/workhorse/compose.yaml" in mk


def test_farrier_regeneration_is_library_aware():
    mk = render_agents_mk()
    assert "AGENTS_DIR     ?= $(shell farrier config show library_dir)" in mk
    assert (
        'FARRIER_LIB_ARG := $(if $(wildcard $(AGENTS_DIR)/library),'
        '--library "$(AGENTS_DIR)",)'
    ) in mk
    assert "uv run --project $(STABLEMATE_DIR)/farrier farrier" in mk
