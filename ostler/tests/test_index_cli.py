"""The index controls — the escape hatch, the visibility, the eviction and the proof."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from ostler import api, doctor, index
from ostler.api import Ostler
from ostler.cli import _build_parser, main

GRAPH_COMMANDS: dict[str, list[str]] = {
    "doctor": ["doctor"],
    "trace": ["trace", "seed-a1"],
    "list": ["list", "--type", "story"],
    "search": ["search", "Foo"],
    "graph": ["graph"],
    "reach": ["reach", "--from", "screen/home"],
    "locators": ["locators"],
    "next-epic": ["next-epic"],
    "next-story": ["next-story", "epic-a"],
    "find": ["find", "program"],
}

COMMANDS = pytest.mark.parametrize(
    "argv", list(GRAPH_COMMANDS.values()), ids=list(GRAPH_COMMANDS)
)


@pytest.fixture
def index_home(tmp_path, monkeypatch) -> Path:
    """A resolved index directory of this test's own, and no operator config in reach."""
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config/config.toml"))
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    resolved = tmp_path / "resolved-index"
    monkeypatch.setenv(index.INDEX_DIR_ENV, str(resolved))
    return resolved


def entry(directory: Path, name: str, *, age_days: float = 0.0) -> Path:
    """One entry file in *directory*, aged *age_days* into the past."""
    path = directory / name[:2] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"payload")
    when = time.time() - age_days * 24 * 60 * 60
    os.utime(path, (when, when))
    return path


def entry_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*") if p.is_file())


def out(capsys) -> str:
    return capsys.readouterr().out


def report_of(capsys) -> dict:
    return json.loads(out(capsys))


STALE_DAYS = 90.0


@COMMANDS
def test_every_graph_loading_command_accepts_no_index(argv):
    args = _build_parser().parse_args([*argv, "--no-index"])

    assert args.no_index is True


@COMMANDS
def test_no_index_is_off_unless_asked_for(argv):
    """On by default from the first commit — the flag is the escape hatch, not the switch."""
    args = _build_parser().parse_args(argv)

    assert args.no_index is False


@COMMANDS
def test_every_graph_loading_command_runs_with_no_index(repo, index_home, argv, capsys):
    """Accepting the flag is not enough: the command still has to complete under it."""
    code = main(["-C", str(repo), *argv, "--no-index"])
    capsys.readouterr()

    assert isinstance(code, int)


def test_no_index_forces_the_uncached_path(repo, tmp_path, index_home, capsys):
    """Nothing is read from the index and nothing is written to it."""
    explicit = tmp_path / "untouched-index"

    assert main([
        "-C", str(repo), "doctor", "--json",
        "--index-dir", str(explicit), "--no-index",
    ]) == 0
    counts = report_of(capsys)["index"]

    assert (counts["hits"], counts["misses"]) == (0, 0)
    assert entry_files(explicit) == []
    assert entry_files(index_home) == []


@COMMANDS
def test_every_graph_loading_command_accepts_an_explicit_index_directory(argv, tmp_path):
    chosen = tmp_path / "chosen"
    args = _build_parser().parse_args([*argv, "--index-dir", str(chosen)])

    assert Path(args.index_dir) == chosen


@COMMANDS
def test_every_graph_loading_command_runs_against_an_explicit_index_directory(
    repo, tmp_path, index_home, argv, capsys
):
    code = main(["-C", str(repo), *argv, "--index-dir", str(tmp_path / "chosen")])
    capsys.readouterr()

    assert isinstance(code, int)


def test_the_resolved_default_is_used_when_nothing_overrides_it(repo, index_home, capsys):
    assert main(["-C", str(repo), "doctor", "--json"]) == 0

    assert Path(report_of(capsys)["index"]["dir"]) == index_home


def test_an_explicit_index_directory_beats_the_resolved_default(repo, tmp_path, index_home, capsys):
    """`$OSTLER_INDEX_DIR` is set by the fixture; the argument still wins."""
    explicit = tmp_path / "explicit-index"

    assert main(["-C", str(repo), "doctor", "--json", "--index-dir", str(explicit)]) == 0

    assert Path(report_of(capsys)["index"]["dir"]) == explicit


def test_json_output_carries_an_index_hit_miss_line(repo, index_home, capsys):
    assert main(["-C", str(repo), "doctor", "--json"]) == 0
    counts = report_of(capsys)["index"]

    assert isinstance(counts["hits"], int)
    assert isinstance(counts["misses"], int)


def test_the_hit_miss_line_survives_the_rest_of_the_report(repo, index_home, capsys):
    """The index block is added to the report, not substituted for it."""
    assert main(["-C", str(repo), "doctor", "--json"]) == 0
    report = report_of(capsys)

    assert "index" in report
    assert {"org", "profile", "epics", "errors", "warnings", "findings"} <= set(report)
    assert report["errors"] == 0


def test_cache_clean_removes_the_aged_out_entries_and_keeps_the_rest(tmp_path, index_home, capsys):
    directory = tmp_path / "index"
    stale = [entry(directory, "aa11", age_days=STALE_DAYS),
             entry(directory, "bb22", age_days=STALE_DAYS)]
    fresh = entry(directory, "cc33")

    assert main(["-C", str(tmp_path), "cache", "clean", "--index-dir", str(directory)]) == 0
    printed = out(capsys)

    assert [p.exists() for p in stale] == [False, False]
    assert fresh.exists()
    assert "2" in printed, f"the clean must report what it removed: {printed!r}"


def test_cache_clean_all_removes_every_entry(tmp_path, index_home, capsys):
    directory = tmp_path / "index"
    written = [entry(directory, "aa11", age_days=STALE_DAYS),
               entry(directory, "bb22"),
               entry(directory, "cc33")]

    assert main([
        "-C", str(tmp_path), "cache", "clean", "--index-dir", str(directory), "--all",
    ]) == 0
    printed = out(capsys)

    assert entry_files(directory) == []
    assert [p.exists() for p in written] == [False, False, False]
    assert "3" in printed, f"the clean must report what it removed: {printed!r}"


def test_cache_clean_reports_what_it_removed_as_json(tmp_path, index_home, capsys):
    directory = tmp_path / "index"
    entry(directory, "aa11", age_days=STALE_DAYS)
    entry(directory, "bb22", age_days=STALE_DAYS)

    assert main([
        "-C", str(tmp_path), "cache", "clean", "--index-dir", str(directory), "--json",
    ]) == 0
    result = report_of(capsys)

    assert result["removed"] == 2
    assert Path(result["dir"]) == directory


def test_cache_clean_succeeds_against_a_directory_that_does_not_exist(tmp_path, index_home, capsys):
    """A fresh machine has no index directory; that is the normal state, not a failure."""
    absent = tmp_path / "never-written"

    assert main(["-C", str(tmp_path), "cache", "clean", "--index-dir", str(absent)]) == 0
    assert "0" in out(capsys)

    assert main([
        "-C", str(tmp_path), "cache", "clean", "--index-dir", str(absent), "--all",
    ]) == 0
    assert "0" in out(capsys)
    assert not absent.exists()


def test_cache_clean_cleans_the_directory_it_was_given(tmp_path, index_home, capsys):
    """The explicit directory overrides the resolved one here too."""
    resolved_entry = entry(index_home, "dd44", age_days=STALE_DAYS)
    explicit = tmp_path / "explicit-index"
    explicit_entry = entry(explicit, "ee55", age_days=STALE_DAYS)

    assert main([
        "-C", str(tmp_path), "cache", "clean", "--index-dir", str(explicit), "--all",
    ]) == 0
    capsys.readouterr()

    assert not explicit_entry.exists()
    assert resolved_entry.exists(), "the resolved index was not the one asked for"


def test_cache_clean_cleans_the_resolved_directory_when_given_none(tmp_path, index_home, capsys):
    stale = entry(index_home, "dd44", age_days=STALE_DAYS)
    fresh = entry(index_home, "ee55")

    assert main(["-C", str(tmp_path), "cache", "clean"]) == 0
    capsys.readouterr()

    assert not stale.exists()
    assert fresh.exists()


def test_verify_index_runs_doctor_both_ways(repo, index_home, monkeypatch, capsys):
    """One command, two runs: the cached path and the uncached one."""
    real = doctor.run
    runs: list[doctor.Report] = []

    def spy(*args, **kwargs):
        report = real(*args, **kwargs)
        runs.append(report)
        return report

    monkeypatch.setattr(doctor, "run", spy)

    assert main(["-C", str(repo), "doctor", "--verify-index"]) == 0
    capsys.readouterr()

    assert len(runs) == 2, "verify must run doctor with the index and without it"


def test_verify_index_passes_when_the_two_reports_are_identical(repo, index_home, capsys):
    """With no cached product consuming the store yet this passes trivially — which is the correct result, and the reason the gate is in place before anything is served."""
    assert main(["-C", str(repo), "doctor", "--verify-index"]) == 0


def test_verify_index_fails_with_a_diff_when_the_two_reports_differ(
    repo, index_home, monkeypatch, capsys
):
    real = doctor.run
    calls: list[int] = []

    def diverging(*args, **kwargs):
        report = real(*args, **kwargs)
        calls.append(1)
        if len(calls) == 2:
            report.findings.append(
                doctor.Finding(
                    severity="error",
                    code="injected-disagreement",
                    message="the two paths did not agree",
                )
            )
        return report

    monkeypatch.setattr(doctor, "run", diverging)

    code = main(["-C", str(repo), "doctor", "--verify-index"])
    printed = out(capsys)

    assert code != 0
    assert "injected-disagreement" in printed, f"the diff must name what differed: {printed!r}"


def test_verify_index_is_accepted_by_the_parser_as_one_command():
    """CI runs it as a single invocation — no flag pairing, no second command to compare against."""
    args = _build_parser().parse_args(["doctor", "--verify-index"])

    assert args.verify_index is True
    assert _build_parser().parse_args(["doctor"]).verify_index is False


def test_the_library_face_defaults_to_using_the_index(repo, index_home):
    okf = Ostler(repo)

    assert okf.index.enabled is True
    assert okf.index.directory == index_home
    assert okf.index_stats() == {
        "dir": str(index_home), "enabled": True, "hits": 0, "misses": 0,
    }


def test_the_library_face_takes_no_index_and_an_explicit_directory(repo, tmp_path, index_home):
    explicit = tmp_path / "library-index"

    okf = Ostler(repo, use_index=False, index_dir=explicit)
    okf.doctor()

    assert okf.index.enabled is False
    assert okf.index_stats()["hits"] == 0 and okf.index_stats()["misses"] == 0
    assert entry_files(explicit) == []
    assert entry_files(index_home) == []


def test_the_library_face_loads_with_its_own_store_active(repo, tmp_path, index_home):
    """One store for the object's life, active for every load it does."""
    explicit = tmp_path / "library-index"
    okf = Ostler(repo, index_dir=explicit)
    seen: list[index.IndexStore | None] = []

    def spy(*args, **kwargs):
        seen.append(index.active())
        return real(*args, **kwargs)

    real = api.load
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(api, "load", spy)
        okf.graph
        (repo / "docs/features/area/rec3.md").write_text(
            "---\ntype: feature\nid: t-3\ntitle: Rec 3\n---\n\n# Rec 3\n", encoding="utf-8")
        okf.reload().graph

    assert seen == [okf.index, okf.index]
    assert index.active() is None, "the session must not outlive the load"
