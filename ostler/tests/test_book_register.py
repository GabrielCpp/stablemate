"""The register of underspecified fields a book keeps for its product owner, and how a run reads and writes it."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any, Iterator

import pytest

from ostler.book import Answer, Endpoint
from ostler.book.inputs import Tried, Twin, Twinned
from ostler.book.register import Entry, entry_of, load, save, settle

from book_todo import FIXTURE, module, run_book

DAY = date(2026, 11, 11)


class ReadA(Endpoint):
    method = "GET"
    path = "/a"
    answers = (Answer(200, None, "read"),)


class ReadB(Endpoint):
    method = "GET"
    path = "/b"
    answers = (Answer(200, None, "read"),)


def split(endpoint: type[Any], dimension: str = "case", name: str = "locale", text: str = "p: x differs") -> Twinned:
    return Twinned(endpoint, Twin("body", name, dimension, "en", "EN"), played=True, split=text, answers=("ok {'a': 1}", "ok {'a': 2}"))


def clean(endpoint: type[Any], dimension: str = "case", name: str = "locale") -> Twinned:
    return Twinned(endpoint, Twin("body", name, dimension, "en", "EN"), played=True)


def test_an_entry_names_the_pair_the_two_values_the_two_answers_and_the_day():
    entry = entry_of(split(ReadA), DAY)
    assert entry == Entry("ReadA body locale case", "case", "'en' and 'EN'", "ok {'a': 1}", "ok {'a': 2}", "2026-11-11")


def test_an_answer_is_trimmed_to_a_line_a_person_reads():
    long = Twinned(ReadA, Twin("body", "locale", "case", "en", "EN"), played=True, split="x", answers=("ok " + "z" * 900, "ok"))
    assert len(entry_of(long, DAY).first) < 400


def test_a_register_written_is_read_back_whole(tmp_path: Path):
    file = tmp_path / "UNDERSPECIFIED.md"
    entries = [entry_of(split(ReadA), DAY), entry_of(split(ReadB, "surrounding spaces", "email"), DAY)]
    save(str(file), entries)
    assert load(str(file)) == entries
    assert file.read_text().startswith("# Underspecified")


def test_a_book_with_no_register_has_no_entries(tmp_path: Path):
    assert load(str(tmp_path / "UNDERSPECIFIED.md")) == []


def test_a_finding_the_register_holds_is_known_and_does_not_fail():
    entries = [entry_of(split(ReadA), DAY)]
    tried = Tried()
    tried.twins.append(split(ReadA))
    settled = settle(tried, entries, None, DAY)
    assert settled.known == tried.twins
    assert settled.fresh == []
    assert settled.stale == []
    assert tried.underspecified == []


def test_a_finding_the_register_lacks_stays_open_without_the_option():
    tried = Tried()
    tried.twins.append(split(ReadA))
    settled = settle(tried, [], None, DAY)
    assert settled.fresh == []
    assert tried.underspecified == tried.twins


def test_a_finding_the_register_lacks_is_added_with_the_option():
    tried = Tried()
    tried.twins.append(split(ReadA))
    settled = settle(tried, [], frozenset(), DAY)
    assert [e.key for e in settled.fresh] == ["ReadA body locale case"]
    assert settled.known == tried.twins
    assert tried.underspecified == []


def test_the_option_registers_only_what_lies_outside_the_named_calls():
    tried = Tried()
    tried.twins += [split(ReadA), split(ReadB)]
    settled = settle(tried, [], frozenset({"ReadA"}), DAY)
    assert [e.key for e in settled.fresh] == ["ReadB body locale case"]
    assert [t.endpoint for t in tried.underspecified] == [ReadA]


def test_an_entry_whose_pair_no_longer_splits_is_stale():
    entries = [entry_of(split(ReadA), DAY)]
    tried = Tried()
    tried.twins.append(clean(ReadA))
    settled = settle(tried, entries, frozenset(), DAY)
    assert settled.stale == entries


def test_an_entry_whose_pair_the_model_now_distinguishes_is_stale():
    entries = [entry_of(split(ReadA), DAY)]
    tried = Tried()
    tried.twins.append(Twinned(ReadA, Twin("body", "locale", "case", "en", "EN"), distinguished=True))
    assert settle(tried, entries, None, DAY).stale == entries


def test_an_entry_whose_pair_was_not_played_is_neither_known_nor_stale():
    entries = [entry_of(split(ReadA), DAY)]
    tried = Tried()
    settled = settle(tried, entries, None, DAY)
    assert (settled.known, settled.stale) == ([], [])


@pytest.fixture
def book(tmp_path: Path) -> Path:
    root = tmp_path / "book"
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


@pytest.fixture
def utc_server() -> Iterator:
    server = module("app").TodoServer(bug="remind_utc").start()
    yield server
    server.stop()


@pytest.fixture
def todo_server() -> Iterator:
    server = module("app").TodoServer().start()
    yield server
    server.stop()


def _run(book: Path, server: Any, out: Path, *extra: str):
    return run_book(["run", "services.api", "--no-stack", "--out", str(out), *extra], server.port, cwd=book)


def test_a_run_with_the_option_registers_the_findings_and_exits_clean(book, utc_server, tmp_path):
    done = _run(book, utc_server, tmp_path / "out", "--register")
    assert done.returncode == 0, done.stdout + done.stderr
    held = load(str(book / "services" / "api" / "UNDERSPECIFIED.md"))
    assert {e.key for e in held} == {"AddTodo body remind_at offset", "UpdateTodo body remind_at offset"}
    assert "2 known" in done.stdout


def test_a_later_run_without_the_option_reports_the_registered_findings_as_known(book, utc_server, tmp_path):
    _run(book, utc_server, tmp_path / "first", "--register")
    done = _run(book, utc_server, tmp_path / "second")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "KNOWN  twin AddTodo body remind_at offset" in done.stdout
    assert "Underspecified (fails the run)" not in done.stdout


def test_a_run_without_the_option_and_without_a_register_fails_on_the_findings(book, utc_server, tmp_path):
    done = _run(book, utc_server, tmp_path / "out")
    assert done.returncode == 1
    assert not (book / "services" / "api" / "UNDERSPECIFIED.md").exists()


def test_a_run_scoped_to_outside_calls_leaves_the_named_calls_failing(book, utc_server, tmp_path):
    done = _run(book, utc_server, tmp_path / "out", "--register-outside", "AddTodo")
    assert done.returncode == 1, done.stdout + done.stderr
    held = load(str(book / "services" / "api" / "UNDERSPECIFIED.md"))
    assert [e.key for e in held] == ["UpdateTodo body remind_at offset"]
    assert [line.split()[1] for line in done.stdout.partition("Stated and never played")[0].splitlines() if line.startswith("- ")] == ["AddTodo"]


def test_an_entry_the_app_no_longer_splits_fails_the_run_and_names_the_dimension(book, utc_server, todo_server, tmp_path):
    _run(book, utc_server, tmp_path / "first", "--register")
    done = _run(book, todo_server, tmp_path / "second")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "the field no longer splits along offset, remove its register entry" in done.stdout
    assert "AddTodo body remind_at offset" in done.stdout
