from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.exercise import EVIDENCE_KEPT, keep_evidence


def _spec(tmp_path: Path) -> Path:
    spec = tmp_path / "spec"
    output = spec / "qa/generated/foo-maestro-output/x"
    output.mkdir(parents=True)
    _ = (output / "commands-a.json").write_text("[]", encoding="utf-8")
    _ = (output / "screenshot-1.png").write_bytes(b"png")
    _ = (spec / "qa/generated/foo.yaml").write_text("appId: x", encoding="utf-8")
    (spec / "qa/traces").mkdir()
    _ = (spec / "qa/traces/foo-maestro.txt").write_text("log", encoding="utf-8")
    return spec


def test_keeps_runner_output_and_not_compiled_sources(tmp_path: Path) -> None:
    kept = keep_evidence(_spec(tmp_path), tmp_path / "evidence")
    assert kept is not None
    assert (kept / "generated/foo-maestro-output/x/commands-a.json").read_text(encoding="utf-8") == "[]"
    assert (kept / "generated/foo-maestro-output/x/screenshot-1.png").is_file()
    assert (kept / "traces/foo-maestro.txt").is_file()
    assert not (kept / "generated/foo.yaml").exists()


def test_keeps_nothing_when_the_run_left_no_output(tmp_path: Path) -> None:
    (tmp_path / "spec/qa").mkdir(parents=True)
    assert keep_evidence(tmp_path / "spec", tmp_path / "evidence") is None
    assert not (tmp_path / "evidence").exists()


def test_prunes_the_oldest_beyond_the_limit(tmp_path: Path) -> None:
    into = tmp_path / "evidence"
    for day in range(EVIDENCE_KEPT):
        (into / f"2026010{day // 10}T0000{day % 10}0Z").mkdir(parents=True)
    oldest = sorted(into.iterdir())[0]
    kept = keep_evidence(_spec(tmp_path), into)
    assert kept is not None
    dirs = sorted(into.iterdir())
    assert len(dirs) == EVIDENCE_KEPT
    assert oldest not in dirs
    assert kept in dirs
