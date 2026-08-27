"""The `pre-commit` gate that keeps QA evidence out of history.

The script ships as an asset of the `ostler` skill rather than as ostler source — a
client repo installs it with the skill and runs it with a bare `python3`, so it imports
nothing from this package. These cases load it by path and drive it against real
throwaway repositories, because every rule it enforces is a statement about what `git`
has in the index, and a fake index would only pin our idea of one.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "base-library/library/skills/ostler/cli/scripts/check_staged_files.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_staged_files", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _stage(repo: Path, relative: str, content: bytes) -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    subprocess.run(["git", "add", "-f", "--", relative], cwd=repo, check=True)
    return path


# ---------------------------------------------------------------------------
# rule 1 — size
# ---------------------------------------------------------------------------


def test_an_oversized_blob_is_refused(repo: Path):
    _stage(repo, "assets/demo.webm", b"\0" * (gate.MAX_BYTES + 1))

    problems = gate.check_staged_files(repo)

    assert len(problems) == 1
    assert "demo.webm" in problems[0] and "limit" in problems[0]


def test_ordinary_source_passes(repo: Path):
    _stage(repo, "src/app.py", b"print('hello')\n")

    assert gate.check_staged_files(repo) == []


def test_the_size_read_is_the_index_not_the_worktree(repo: Path):
    """Staging a small file and then growing it on disk must still commit cleanly: what
    the commit carries is the blob `git add` wrote, and a worktree read would refuse a
    commit whose content is fine."""
    path = _stage(repo, "notes.md", b"small\n")
    path.write_bytes(b"\0" * (gate.MAX_BYTES + 1))

    assert gate.check_staged_files(repo) == []


def test_deleting_a_huge_blob_is_the_fix_not_a_finding(repo: Path):
    _stage(repo, "trace.zip", b"\0" * (gate.MAX_BYTES + 1))
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "seed"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "rm", "-q", "--", "trace.zip"], cwd=repo, check=True)

    assert gate.check_staged_files(repo) == []


# ---------------------------------------------------------------------------
# rule 2 — QA evidence
# ---------------------------------------------------------------------------


def test_an_artifact_directory_under_qa_is_evidence(repo: Path):
    _stage(repo, "docs/specs/story/qa/copy-link/traces/run.zip", b"x")

    problems = gate.check_staged_files(repo)

    assert len(problems) == 1
    assert "QA evidence" in problems[0]


def test_a_ledger_file_is_evidence_however_small(repo: Path):
    """Size alone lets two thousand of these through — the client repo's 2,167 committed
    files were mostly a few kilobytes each."""
    _stage(repo, "docs/specs/story/qa/qa-run.ndjson", b"{}\n")

    assert gate.check_staged_files(repo)


def test_a_file_beside_a_ledger_is_evidence_too(repo: Path):
    """A run writes more than the names we know. What marks the directory is the ledger
    sitting in it, so anything staged from inside it is refused."""
    (repo / "docs/specs/story/qa/copy-link").mkdir(parents=True)
    (repo / "docs/specs/story/qa/copy-link/qa-run.ndjson").write_text("", encoding="utf-8")
    _stage(repo, "docs/specs/story/qa/copy-link/console.log", b"noise\n")

    assert gate.check_staged_files(repo)


def test_source_code_in_a_package_called_qa_is_not_evidence(repo: Path):
    """`ostler/ostler/qa/session.py` and `workflows/.../coder/qa/nodes/qa.py` are code. A
    gate that refused them would be switched off within a day, and then it protects
    nothing at all."""
    _stage(repo, "ostler/ostler/qa/session.py", b"QA_DIRNAME = 'qa'\n")
    _stage(repo, "workflows/src/coder/qa/nodes/qa.py", b"def run():\n    ...\n")

    assert gate.check_staged_files(repo) == []


def test_the_plan_fixtures_beside_the_evidence_are_not_evidence(repo: Path):
    """`qa-inputs/` holds a plan's `inputs:` — tracked on purpose, and a sibling of the
    directory a run writes."""
    (repo / "docs/specs/story/qa").mkdir(parents=True)
    (repo / "docs/specs/story/qa/qa-run.ndjson").write_text("", encoding="utf-8")
    _stage(repo, "docs/specs/story/qa-inputs/seed.json", b"{}")

    assert gate.check_staged_files(repo) == []


# ---------------------------------------------------------------------------
# the escape hatch
# ---------------------------------------------------------------------------


def test_a_tracked_glob_excuses_a_path(repo: Path):
    """The exception reaches review as a diff somebody approved, which `--no-verify`
    never does."""
    _stage(repo, ".agent-checks.toml", b'[check-staged-files]\nallow = ["fixtures/*.sql"]\n')
    _stage(repo, "fixtures/dump.sql", b"-- " + b"x" * gate.MAX_BYTES)

    assert gate.check_staged_files(repo) == []


def test_a_repo_may_set_its_own_threshold(repo: Path):
    _stage(repo, ".agent-checks.toml", b"[check-staged-files]\nmax-bytes = 16\n")
    _stage(repo, "src/app.py", b"x" * 32)

    assert gate.check_staged_files(repo)


def test_a_repo_that_declares_nothing_still_gets_both_rules(repo: Path):
    _stage(repo, "docs/specs/story/qa/copy-link/videos/run.webm", b"x")

    assert gate.declarations(repo) == {}
    assert gate.check_staged_files(repo)


# ---------------------------------------------------------------------------
# the exit code the hook reads
# ---------------------------------------------------------------------------


def test_the_hook_exits_nonzero_and_says_how_to_proceed(repo: Path, capsys, monkeypatch):
    _stage(repo, "docs/specs/story/qa/copy-link/traces/run.zip", b"x")
    monkeypatch.setattr(sys, "argv", ["check_staged_files.py", "--root", str(repo)])

    assert gate.main() == 1

    err = capsys.readouterr().err
    assert "FAIL check_staged_files" in err
    assert "ostler qa clean" in err


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
