"""The generated launcher (.agents/agents.mk): adapter regeneration, containerized
runs, and one run target per workflow installed on the machine running `make`.

Two properties are being pinned, and they pull against each other.

**The file is byte-identical everywhere.** It is tracked in the repo, so anything
machine-specific in it churns for every developer, fails `agent-check` on a machine
with a different pipx set, and — for a workflow installed from a local path — commits
somebody's home directory. So the workflow list is *not* rendered in; the file asks
`farrier workflows --names` when make parses it.

**The run targets are still real per-workflow targets.** `$(eval)` generates them
from that list, so `make agent-run-typo` gets make's own "No rule to make target"
rather than launching nothing. (`tests/test_launcher_make.py` runs real `make`
against the rendered file to check that end; the assertions here are about what is
and is not written into it.)

The run id assertions are load-bearing: workhorse derives a run id from a digest of
the run params when none is given, and in a container those params are identical
every launch — so an absent `--run-id` means every container claims the same run dir
and the second one resumes or deletes the first.

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


def test_no_workflow_name_is_ever_written_into_the_file():
    """The whole reversal in one assertion. This file is tracked; the installed set
    belongs to the machine. A name baked in here is drift waiting to happen."""
    mk = render_agents_mk()
    for name in ("coder", "author", "okf-builder", "research", "hello-world"):
        assert name not in mk, name


def test_the_workflow_list_is_resolved_when_make_runs():
    mk = render_agents_mk()
    assert "AGENT_WORKFLOWS := $(shell $(FARRIER) workflows --names)" in mk
    # …and turned into real targets, not a pattern rule that swallows typos.
    assert "$(foreach wf,$(AGENT_WORKFLOWS),$(eval $(call agent_run_target,$(wf))))" in mk
    assert "define agent_run_target" in mk


def test_discovery_is_gated_on_actually_wanting_to_run_something():
    """`farrier workflows` shells out to pipx (~0.4s). Every `make <anything>` in the
    including repo would otherwise pay for it."""
    mk = render_agents_mk()
    assert "ifneq ($(filter agent-run-%,$(MAKECMDGOALS)),)" in mk


def test_a_reader_with_no_run_target_is_told_where_to_look():
    mk = render_agents_mk()
    assert "agent-workflows:" in mk
    assert "$(FARRIER) workflows" in mk


def test_no_yaml_era_run_targets_or_docker_plumbing():
    """The YAML-era run targets are gone, not merely renamed.

    Each of these drove the retired front end: `--workflow <dir>/workflow.yaml`, a
    compose override generated per installed workflow, and a `WF` variable naming
    which of them to run. The launcher's run targets are per-workflow
    (`agent-run-coder`), never a single `agent-run` dispatching on `WF`, so asserting
    these stay absent keeps a copy-paste from an old launcher from reintroducing an
    invocation workhorse no longer accepts.
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


def test_each_launch_mints_its_own_run_id():
    mk = render_agents_mk()
    # A UUID from the kernel rather than a new dependency (uuidgen is not guaranteed
    # installed; /proc/sys/kernel/random/uuid is).
    assert 'run_id="$$(cat /proc/sys/kernel/random/uuid)"' in mk
    # It reaches workhorse as the container's run identity...
    assert 'AGENT_RUN_ID="$$run_id"' in mk
    # ...and names the compose project, which is what makes the named volumes per-run
    # (compose namespaces volumes by project).
    assert 'project="$(1)-$$run_id"' in mk
    assert 'docker compose -p "$$project"' in mk


def test_each_run_gets_its_own_worktree_of_the_repo():
    mk = render_agents_mk()
    assert "AGENT_SOURCE_MODE=worktree" in mk
    # Per RUN, not per repo — that is what lets several be in flight at once.
    assert 'worktree_root="$(AGENT_WORKTREE_ROOT)/$$run_id"' in mk
    # The run works IN its own tree, never in the shared source: pointing every run
    # at the host repo would put N agents in one working directory.
    assert 'AGENT_REPO_DIR="$$worktree_root/$$repo_name"' in mk


def test_the_repo_is_bound_at_its_own_host_path():
    """Git records a worktree's registration on both sides by absolute path, so the
    container and the host have to agree on what that path is."""
    mk = render_agents_mk()
    assert 'AGENT_REPO_HOST_DIR="$(AGENT_REPO)"' in mk
    # Worktrees live under the repo, so ONE bind covers the source and every tree.
    assert "AGENT_WORKTREE_ROOT ?= $(AGENT_REPO)/.agents/worktrees" in mk


def test_the_base_branch_is_resolved_lazily():
    """`?=` keeps this git call out of every `make` in the including repo — it runs
    only when a launch actually expands it."""
    mk = render_agents_mk()
    assert "AGENT_BASE_BRANCH  ?= $(shell git -C" in mk


def test_runs_as_nobody_with_the_operators_group():
    """65534:<host gid> — the uid is not yours, the group access is, so run output
    under a bind-mounted host path stays writable from the host."""
    mk = render_agents_mk()
    assert "AGENT_UID  ?= 65534" in mk
    assert "AGENT_GID  ?= $(shell id -g)" in mk
    assert 'AGENT_UID="$(AGENT_UID)" AGENT_GID="$(AGENT_GID)"' in mk


def test_run_output_stays_writable_from_the_host():
    """Group access is the only thing bridging the container's uid and yours, so
    nothing may drop the group write bit. Git works against this by default — it
    writes into `.git` with no group write at all — and `core.sharedRepository` on
    the SOURCE repo is what relaxes it, because that is where a worktree's objects
    and refs land."""
    mk = render_agents_mk()
    assert "core.sharedRepository group" in mk
    # setgid, so directories the container mints inherit your group.
    assert 'chmod g+s "$$worktree_root"' in mk


def test_the_operators_own_repo_config_is_only_touched_when_absent():
    """It is their repo, and the setting persists and changes how their own git
    writes — so it is announced, and never overwritten."""
    mk = render_agents_mk()
    assert "config --local core.sharedRepository || true" in mk
    assert "[agent] set core.sharedRepository=group" in mk


def test_credentials_are_staged_per_run_rather_than_read_in_place():
    """`~/.claude/.credentials.json` is mode 600, so a container that is not you
    cannot read it and the run dies at "Not logged in". The copy is 640 and per-run;
    the operator's own file is never modified — chmod-ing it would be undone the
    next time the CLI rotates the token."""
    mk = render_agents_mk()
    assert 'run_auth="$$worktree_root/.credentials.json"' in mk
    assert 'install -m 640 "$$HOME/.claude/.credentials.json" "$$run_auth"' in mk
    assert 'AGENT_CREDENTIALS_FILE="$$run_auth"' in mk


def test_a_machine_with_no_credentials_file_still_launches():
    """CLAUDE_CODE_OAUTH_TOKEN is the other supported auth path, and it needs no
    file at all — so a missing credentials file is skipped, not fatal."""
    mk = render_agents_mk()
    assert 'if [ -r "$$HOME/.claude/.credentials.json" ]; then' in mk


def test_operating_targets_address_a_single_run():
    """With N runs in flight, every operating verb has to name which one."""
    mk = render_agents_mk()
    for target in ("agent-runs:", "agent-logs:", "agent-stop:", "agent-clean:"):
        assert target in mk, target
    assert mk.count("$(call agent_require_run)") == 3
    # Destructive and non-destructive stops are separate targets: `stop` leaves the
    # volumes so `docker restart` resumes the same run id from its checkpoint.
    assert 'docker compose -p "$(RUN)" -f "$(AGENT_COMPOSE)" stop' in mk
    assert 'docker compose -p "$(RUN)" -f "$(AGENT_COMPOSE)" down -v' in mk


def test_compose_file_comes_from_the_stablemate_checkout():
    """compose.yaml/Dockerfile are harness files in the repo, not distribution files
    — there is no installed package to resolve them from."""
    mk = render_agents_mk()
    assert "AGENT_COMPOSE ?= $(STABLEMATE_DIR)/workhorse/compose.yaml" in mk


def test_farrier_regeneration_is_library_aware():
    mk = render_agents_mk()
    assert "AGENTS_DIR     ?= $(shell farrier config show library_dir)" in mk
    assert (
        'FARRIER_LIB_ARG := $(if $(wildcard $(AGENTS_DIR)/library),'
        '--library "$(AGENTS_DIR)",)'
    ) in mk
    # SRC=1 still runs the installer from a local stablemate checkout.
    assert "uv run --project $(STABLEMATE_DIR)/farrier farrier" in mk
