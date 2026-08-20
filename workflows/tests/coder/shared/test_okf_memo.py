"""The obligation packet is rebuilt when its inputs move, and only then.

`build_okf_context` is visited many times per story — on the way in, after every repair
lap, and again for the docs gate — and each visit paid a full ostler construction to
re-derive a packet that is a pure function of the book, the diff and its arguments. These
tests pin both halves of the memo: a repeat visit with nothing moved must not rebuild, and
*anything* that moves must.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from workhorse.testing import make_git_repo
from workhorse_workflows.coder.shared import okf

LOGGER = logging.getLogger("test")


@dataclass
class FakeOutcome:
    ok: bool = True
    message: str = ""
    data: dict[str, Any] = field(default_factory=lambda: {"version": 1})
    problems: list[str] = field(default_factory=list)


class FakeOstler:
    """Stands in for the ~28s build: counts its calls and writes what the real one writes."""

    calls: list[Path] = []
    ok = True

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def qa_context(self, *, spec: str, **_: Any) -> FakeOutcome:
        spec_dir = self.root / spec
        spec_dir.mkdir(parents=True, exist_ok=True)
        for name in okf.PACKET_FILES:
            (spec_dir / name).write_text("{}\n", encoding="utf-8")
        FakeOstler.calls.append(spec_dir)
        return FakeOutcome(ok=FakeOstler.ok)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = make_git_repo(tmp_path / "app")
    (root / "docs").mkdir()
    FakeOstler.calls = []
    FakeOstler.ok = True
    monkeypatch.setattr(okf, "Ostler", FakeOstler)
    return root


def build(repo: Path) -> Any:
    return okf.build_okf_context(LOGGER, spec_dir="docs/spec", docs_path=str(repo))


def commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True, capture_output=True)


def test_a_repeat_visit_reuses_the_packet_byte_for_byte(repo: Path) -> None:
    first = build(repo)
    second = build(repo)
    assert len(FakeOstler.calls) == 1
    assert second.model_dump() == first.model_dump()
    assert second.status == "passed"


def test_editing_a_tracked_file_rebuilds(repo: Path) -> None:
    build(repo)
    (repo / "README.md").write_text("# moved\n", encoding="utf-8")
    build(repo)
    assert len(FakeOstler.calls) == 2


def test_a_brand_new_untracked_file_rebuilds(repo: Path) -> None:
    """The case a tracked-diff-only signature would miss — and the packet's usual input."""
    build(repo)
    (repo / "service.go").write_text("package main\n", encoding="utf-8")
    build(repo)
    assert len(FakeOstler.calls) == 2


def test_committing_rebuilds(repo: Path) -> None:
    """`HEAD` is part of the signature: the book the packet maps onto lives in the repo."""
    build(repo)
    (repo / "docs" / "note.md").write_text("# note\n", encoding="utf-8")
    commit(repo, "docs: a note")
    build(repo)
    assert len(FakeOstler.calls) == 2


def test_a_different_spec_dir_does_not_read_the_other_ones_memo(repo: Path) -> None:
    build(repo)
    okf.build_okf_context(LOGGER, spec_dir="docs/other", docs_path=str(repo))
    assert len(FakeOstler.calls) == 2


def test_a_missing_packet_file_rebuilds_even_with_a_matching_stamp(repo: Path) -> None:
    """The stamp records what *was* built; it is not itself the answer anyone reads."""
    build(repo)
    (repo / "docs" / "spec" / "qa-okf-context.md").unlink()
    build(repo)
    assert len(FakeOstler.calls) == 2


def test_a_failed_build_is_not_memoized(repo: Path) -> None:
    FakeOstler.ok = False
    first = build(repo)
    assert first.status == "invalid"
    assert not (repo / "docs" / "spec" / okf.STAMP_FILE).exists()
    build(repo)
    assert len(FakeOstler.calls) == 2


def test_an_unreadable_stamp_rebuilds_rather_than_guessing(repo: Path) -> None:
    build(repo)
    (repo / "docs" / "spec" / okf.STAMP_FILE).write_text("{ not json", encoding="utf-8")
    build(repo)
    assert len(FakeOstler.calls) == 2


def test_the_stamp_records_the_key_the_next_visit_recomputes(repo: Path) -> None:
    build(repo)
    stamp = json.loads((repo / "docs" / "spec" / okf.STAMP_FILE).read_text(encoding="utf-8"))
    outputs = tuple(
        f"docs/spec/{name}" for name in (*okf.PACKET_FILES, okf.STAMP_FILE)
    )
    signature = okf.worktree_signature(repo.resolve(), "HEAD", "WORKTREE", outputs)
    assert signature is not None
    assert stamp["fingerprint"] == okf.fingerprint(
        signature,
        {
            "spec": str(repo.resolve() / "docs/spec"),
            "story_file": "",
            "features_root": "",
            "source_roots": [],
            "base": "HEAD",
            "head": "WORKTREE",
            "exclude_paths": [],
        },
    )
