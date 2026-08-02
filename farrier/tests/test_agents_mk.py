"""The generated launcher (.agents/agents.mk): adapter regeneration always, plus one
containerized run target per installed workflow.

Two things are being pinned here. The regeneration half (`agent-install`,
`agent-check`) is emitted for every repo, so an existing root Makefile can `include`
the launcher unconditionally. The run half is emitted only for the workflows pipx
discovery actually found, and each target launches ONE CONTAINER PER RUN — a fresh
UUID, its own compose project, and therefore its own volume set — because N
concurrent runs of one workflow is the whole point (docs/plans/
container-concurrent-runs.md).

The run id assertions are the load-bearing ones: workhorse derives a run id from a
digest of the run params when none is given, and in a container those params are
identical every launch, so an absent --run-id means every container claims the same
run dir and the second one resumes or deletes the first.

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


def test_no_workflows_renders_the_adapter_only_launcher():
    """A repo with no workflow installed gets no container plumbing at all.

    Discovery is the only source of truth for what is runnable, so "nothing
    discovered" has to render as "no run targets" rather than as a target that
    fails at `docker compose up` time.
    """
    mk = render_agents_mk()
    assert ".PHONY: help agent-install agent-check\n" in mk
    for absent in ("agent-run-", "docker compose", "AGENT_RUN_ID", "agent_launch"):
        assert absent not in mk, absent
    # The reader who has no target still needs to know how to run one.
    assert "workhorse-<name> run" in mk
    assert "--dry-run" in mk


def test_no_yaml_era_run_targets_or_docker_plumbing():
    """The YAML-era run targets are gone, not merely renamed.

    Each of these drove the retired front end: `--workflow <dir>/workflow.yaml`, a
    compose override generated per installed workflow, and a `WF` variable naming
    which of them to run. The launcher's run targets are per-workflow
    (`agent-run-coder`), never a single `agent-run` dispatching on `WF`, so
    asserting these stay absent keeps a copy-paste from an old launcher from
    reintroducing an invocation workhorse no longer accepts.
    """
    mk = render_agents_mk(["coder", "author"])
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


def test_one_run_target_per_discovered_workflow():
    mk = render_agents_mk(["coder", "author", "okf-builder"])
    for name in ("coder", "author", "okf-builder"):
        assert f"\nagent-run-{name}: ##" in mk
        assert f"$(call agent_launch,{name})" in mk
        assert f" agent-run-{name}" in mk  # .PHONY
    # Sorted, so regeneration is deterministic and --check does not churn on the
    # order pipx happened to list them in.
    assert mk.index("agent-run-author:") < mk.index("agent-run-coder:")
    assert mk.index("agent-run-coder:") < mk.index("agent-run-okf-builder:")


def test_render_is_deterministic_for_the_same_set():
    """--check compares rendered text, so anything order- or clock-dependent in the
    launcher would report the file as dirty on every run."""
    assert render_agents_mk(["coder", "author"]) == render_agents_mk(["author", "coder"])


def test_each_launch_mints_its_own_run_id():
    mk = render_agents_mk(["coder"])
    # A UUID from the kernel rather than a new dependency (uuidgen is not
    # guaranteed installed; /proc/sys/kernel/random/uuid is).
    assert 'run_id="$$(cat /proc/sys/kernel/random/uuid)"' in mk
    # It reaches workhorse as the container's run identity...
    assert 'AGENT_RUN_ID="$$run_id"' in mk
    # ...and names the compose project, which is what makes the named volumes
    # per-run (compose namespaces volumes by project).
    assert 'project="$(1)-$$run_id"' in mk
    assert 'docker compose -p "$$project"' in mk


def test_runs_as_nobody_with_the_operators_group():
    """65534:<host gid> — the uid is not yours, the group access is, so run output
    under a bind-mounted host path stays writable from the host."""
    mk = render_agents_mk(["coder"])
    assert "AGENT_UID  ?= 65534" in mk
    assert "AGENT_GID  ?= $(shell id -g)" in mk
    assert 'AGENT_UID="$(AGENT_UID)" AGENT_GID="$(AGENT_GID)"' in mk


def test_operating_targets_address_a_single_run():
    """With N runs in flight, every operating verb has to name which one."""
    mk = render_agents_mk(["coder"])
    for target in ("agent-runs:", "agent-logs:", "agent-stop:", "agent-clean:"):
        assert target in mk, target
    assert mk.count("$(call agent_require_run)") == 3
    # Destructive and non-destructive stops are separate targets: `stop` leaves the
    # volumes so `docker restart` resumes the same run id from its checkpoint.
    assert 'docker compose -p "$(RUN)" -f "$(AGENT_COMPOSE)" stop' in mk
    assert 'docker compose -p "$(RUN)" -f "$(AGENT_COMPOSE)" down -v' in mk


def test_compose_file_comes_from_the_stablemate_checkout():
    """compose.yaml/Dockerfile are harness files in the repo, not distribution
    files — there is no installed package to resolve them from."""
    mk = render_agents_mk(["coder"])
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
