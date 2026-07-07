"""Tests for groom.discovery: mount/env/label parsing against a fixture shaped
like a real `docker inspect` blob (trimmed to the fields discovery.py reads,
matching a workhorse-author-1 style container), plus the scan()/current-node
reconciliation logic with docker_io mocked out.

Run: uv run python tests/test_discovery.py   (or via pytest)
"""
from __future__ import annotations

from unittest.mock import patch

from groom import discovery
from groom.models import WorkflowState


def _inspect(**overrides) -> dict:
    base = {
        "Id": "abcdef012345678901234567890123456789012345678901234567890123",
        "Name": "/workhorse-author-1",
        "State": {"Running": True, "ExitCode": 0},
        "Config": {
            "Env": [
                "REPO_NAME=Predykt",
                "REPO_BRANCH=fixes/03-datasheet-header",
                "PREDYKT_GITHUB_TOKEN=super-secret-value",
                "PATH=/usr/bin",
            ],
        },
        "Mounts": [
            {"Type": "bind", "Source": "/host/workflow", "Destination": "/workflow"},
            {"Type": "volume", "Name": "author-1-runs", "Destination": "/runs"},
            {"Type": "volume", "Name": "author-1-workspace", "Destination": "/workspace"},
        ],
    }
    base.update(overrides)
    return base


def test_is_workhorse_container_requires_all_three_mounts():
    assert discovery.is_workhorse_container(_inspect()) is True

    missing_runs = _inspect(Mounts=[
        {"Type": "bind", "Source": "/host/workflow", "Destination": "/workflow"},
        {"Type": "volume", "Name": "author-1-workspace", "Destination": "/workspace"},
    ])
    assert discovery.is_workhorse_container(missing_runs) is False


def test_is_workhorse_container_ignores_unrelated_containers():
    unrelated = _inspect(Mounts=[{"Type": "bind", "Source": "/tmp", "Destination": "/tmp"}])
    assert discovery.is_workhorse_container(unrelated) is False


def test_container_from_inspect_reads_env_name_and_volumes():
    wf = discovery.container_from_inspect(_inspect())
    assert wf.container_id == "abcdef012345"
    assert wf.name == "workhorse-author-1"
    assert wf.repo_name == "Predykt"
    assert wf.repo_branch == "fixes/03-datasheet-header"
    assert wf.workspace_volume == "author-1-workspace"
    assert wf.runs_volume == "author-1-runs"
    assert wf.state == WorkflowState.RUNNING
    # Secrets present in the container's own env must never surface here.
    assert "PREDYKT_GITHUB_TOKEN" not in vars(wf).values()
    assert "super-secret-value" not in vars(wf).values()


def test_workflow_type_from_workflow_mount_basename():
    wf = discovery.container_from_inspect(_inspect(Mounts=[
        {"Type": "bind", "Source": "/host/agents/workflows/coder", "Destination": "/workflow"},
        {"Type": "volume", "Name": "coder-1-runs", "Destination": "/runs"},
        {"Type": "volume", "Name": "coder-1-workspace", "Destination": "/workspace"},
    ]))
    assert wf.workflow_type == "coder"


def test_workflow_type_falls_back_to_compose_service_label():
    # A bind straight at .../workflow gives the generic basename, so the compose
    # service name is used instead.
    wf = discovery.container_from_inspect(_inspect(Config={
        "Env": ["REPO_NAME=Predykt"],
        "Labels": {"com.docker.compose.service": "author"},
    }))
    assert wf.workflow_type == "author"


def test_container_from_inspect_marks_stopped_container_idle():
    wf = discovery.container_from_inspect(_inspect(State={"Running": False, "ExitCode": 2}))
    assert wf.state == WorkflowState.IDLE


def test_container_from_inspect_falls_back_to_id_when_unnamed():
    wf = discovery.container_from_inspect(_inspect(Name=""))
    assert wf.name == wf.container_id


def test_find_gates_only_keeps_files_still_awaiting():
    with patch.object(discovery.docker_io, "grep_awaiting_files", return_value=["docs/a.md", "docs/b.md"]), \
         patch.object(
             discovery.docker_io,
             "read_file",
             side_effect=lambda vol, path: {
                 "docs/a.md": "STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\n\nWhich one?\n",
                 "docs/b.md": "STATUS: CONSUMED\n",  # already answered since the grep ran
             }[path],
         ):
        found = discovery._find_gates("some-volume")

    assert [g.file_path for g in found] == ["docs/a.md"]
    assert found[0].question == "Which one?"


def test_scan_marks_blocked_workflow_and_finished_run():
    running_blocked = _inspect()
    finished = _inspect(
        Id="fedcba987654321098765432109876543210987654321098765432109876",
        Name="/workhorse-coder-2",
        Mounts=[
            {"Type": "bind", "Source": "/host/workflow", "Destination": "/workflow"},
            {"Type": "volume", "Name": "coder-2-runs", "Destination": "/runs"},
            {"Type": "volume", "Name": "coder-2-workspace", "Destination": "/workspace"},
        ],
    )

    def _fake_inspect(container_id):
        return running_blocked if container_id.startswith("abcdef") else finished

    def _fake_run_dirs(volume):
        return {"author-1-runs": ["run-20260705-090000"], "coder-2-runs": ["run-20260704-120000"]}.get(volume, [])

    def _fake_read_file(volume, rel_path):
        if volume == "author-1-runs" and rel_path.endswith("checkpoint.json"):
            return '{"current_id": "resolve_integrity"}'
        if volume == "coder-2-runs" and rel_path.endswith("run.json"):
            return '{"terminal": "done"}'
        if volume == "author-1-workspace" and rel_path == "docs/gate.md":
            return "STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\n\nWhich default?\n"
        return None

    def _fake_grep(volume, mount_subdir=""):
        return ["docs/gate.md"] if volume == "author-1-workspace" else []

    with patch.object(discovery.docker_io, "docker_ps_all", return_value=[{"ID": "abcdef012345"}, {"ID": "fedcba987654"}]), \
         patch.object(discovery.docker_io, "docker_inspect", side_effect=_fake_inspect), \
         patch.object(discovery.docker_io, "list_run_dirs", side_effect=_fake_run_dirs), \
         patch.object(discovery.docker_io, "read_file", side_effect=_fake_read_file), \
         patch.object(discovery.docker_io, "grep_awaiting_files", side_effect=_fake_grep):
        found = discovery.scan()

    by_id = {wf.container_id: wf for wf in found}
    author = by_id["abcdef012345"]
    coder = by_id["fedcba987654"]

    assert author.state == WorkflowState.BLOCKED
    assert author.current_node == "resolve_integrity"
    assert "docs/gate.md" in author.gates
    assert author.gates["docs/gate.md"].workflow_id == "abcdef012345"

    # A finished run's terminal state wins even though it has no live gates.
    assert coder.state == WorkflowState.FINISHED


def test_present_container_ids_passes_through_docker_layer():
    with patch.object(discovery.docker_io, "list_container_ids", return_value={"abc123456789"}):
        assert discovery.present_container_ids() == {"abc123456789"}
    # None (docker unreachable) is propagated so callers skip pruning.
    with patch.object(discovery.docker_io, "list_container_ids", return_value=None):
        assert discovery.present_container_ids() is None


def test_scan_skips_containers_that_are_not_workhorse_containers():
    with patch.object(discovery.docker_io, "docker_ps_all", return_value=[{"ID": "zzz999"}]), \
         patch.object(discovery.docker_io, "docker_inspect", return_value={"Mounts": []}):
        found = discovery.scan()
    assert found == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
