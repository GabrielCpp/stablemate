"""run.json holds every worktree a run was cut, and still reads the record an older run wrote."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from workhorse.artifacts import ArtifactWriter
from workhorse.cli.offline import print_params
from workhorse.records import PyflowCheckpoint, RunRecord, RunWorktree, WorktreeOutcome, parse_run_record, run_worktrees


def _entries() -> list[RunWorktree]:
    return [
        RunWorktree(name="api", path="/t/api-run-x", branch="run/x", repo="/c/api", base="main"),
        RunWorktree(name="artifacts", path="/t/artifacts-run-x", branch="run/x", repo="/a", base="HEAD", books=True),
    ]


def test_an_old_run_record_with_flat_worktree_fields_reads_as_one_entry():
    outcome = WorktreeOutcome(action="kept", reason="r")
    record = RunRecord(
        worktree_path="/t/api-run-x", worktree_branch="run/x", worktree_repo="/c/api", worktree_base="main",
        worktree_outcome=outcome,
    )

    [entry] = run_worktrees(record)

    assert (entry.name, entry.path, entry.branch, entry.repo, entry.base) == (
        "api", "/t/api-run-x", "run/x", "/c/api", "main",
    )
    assert entry.outcome == outcome


def test_an_old_run_record_resumes_with_its_worktree(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        RunRecord(worktree_path="/t/api-run-x", worktree_branch="run/x", worktree_repo="/c/api").model_dump_json()
    )

    writer = ArtifactWriter.resume(run_dir)

    assert [entry.path for entry in writer.worktrees] == ["/t/api-run-x"]


def test_record_worktree_writes_the_list_and_the_flat_fields(tmp_path):
    writer = ArtifactWriter("wf", tmp_path / "runs", run_id="t")

    writer.record_worktrees(_entries())

    record = parse_run_record((writer.run_dir / "run.json").read_text())
    assert [entry.name for entry in record.worktrees] == ["api", "artifacts"]
    assert (record.worktree_path, record.worktree_branch, record.worktree_repo, record.worktree_base) == (
        "/t/api-run-x", "run/x", "/c/api", "main",
    )
    assert record.worktrees[1].books is True


def test_record_worktree_of_one_makes_a_one_entry_list(tmp_path):
    writer = ArtifactWriter("wf", tmp_path / "runs", run_id="t")

    writer.record_worktree("/t/api-run-x", "run/x", repo="/c/api", base="main")

    [entry] = writer.worktrees
    assert (entry.name, entry.path, entry.base) == ("api", "/t/api-run-x", "main")


def test_outcomes_are_stamped_per_entry_and_the_first_is_mirrored(tmp_path):
    writer = ArtifactWriter("wf", tmp_path / "runs", run_id="t")
    writer.record_worktrees(_entries())
    done = [
        entry.model_copy(update={"outcome": WorktreeOutcome(action="removed", reason=entry.name)})
        for entry in _entries()
    ]

    writer.record_worktree_outcomes(done)

    record = parse_run_record((writer.run_dir / "run.json").read_text())
    assert [entry.outcome.reason for entry in record.worktrees if entry.outcome] == ["api", "artifacts"]
    assert record.worktree_outcome is not None and record.worktree_outcome.reason == "api"


def test_status_params_lists_every_worktree(tmp_path):
    writer = ArtifactWriter("wf", tmp_path / "runs", run_id="t")
    writer.record_worktrees(_entries())
    (writer.run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text(PyflowCheckpoint(state="start").model_dump_json())
    out = io.StringIO()

    with redirect_stdout(out):
        print_params(Path(writer.run_dir))

    report = json.loads(out.getvalue())
    assert [entry["name"] for entry in report["worktrees"]] == ["api", "artifacts"]
